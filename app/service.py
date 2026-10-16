import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path

from llama_index.core.schema import TextNode
from sqlite_vec import serialize_float32
from app.knowledge import build_archive, redact, CITIES
from app.models import ModelAdapter, tokens
from app.parsers import validate_file, parse, render
from app.storage import Store, now, dumps
from app.schemas import Archive, Knowledge


def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex


class Service:
    def __init__(self, settings):
        self.s = settings
        settings.prepare()
        self.models = ModelAdapter(settings)
        self.store = Store(settings, self.models.signature)
        self.lock = threading.RLock()

    def register(self, filename, data):
        doc = uid('doc')
        name = Path(filename.replace('\\','/')).name[:200]
        ext = Path(name).suffix.lower()
        if ext not in {'.docx','.pptx','.pdf'}:
            raise ValueError('仅支持 DOCX、PPTX、PDF')
        if not data or len(data) > self.s.max_file_mb*1024*1024:
            raise ValueError('文件为空或超过大小上限')
        folder = self.s.data_dir / 'originals' / doc
        folder.mkdir()
        path = folder / ('source' + ext)
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        with self.store.connect() as db:
            db.execute('INSERT INTO source_documents(document_id,filename,path,sha256,size,uploaded_at,status,stage) VALUES (?,?,?,?,?,?,?,?)',
                       (doc,name,str(path),digest,len(data),now(),'processing','uploaded'))
        return doc

    def document(self, doc):
        rows = self.store.rows('SELECT * FROM source_documents WHERE document_id=?',(doc,))
        if not rows:
            raise KeyError(doc)
        row = rows[0]
        row['warnings'] = json.loads(row.pop('warnings_json'))
        row['metrics'] = json.loads(row.pop('metrics_json'))
        row.pop('path',None)
        return row

    def process(self, doc):
        # Serial ingestion gives deterministic duplicate and version decisions.
        with self.lock:
            started = time.monotonic()
            row = self.store.rows('SELECT * FROM source_documents WHERE document_id=?',(doc,))[0]
            if row['is_active'] or row['status'] in {'succeeded','rejected_duplicate'}:
                return self.document(doc)
            path = Path(row['path'])
            try:
                self.store.stage(doc,'validating')
                validate_file(path, self.s.max_file_mb)
                duplicate = self.store.rows("SELECT document_id,candidate_id FROM source_documents WHERE sha256=? AND document_id<>? AND version_no>0 ORDER BY uploaded_at LIMIT 1",(row['sha256'],doc))
                if duplicate:
                    return self.reject(doc, duplicate[0])
                self.store.stage(doc,'preflighting')
                directory = self.s.data_dir / 'processed' / doc
                directory.mkdir(exist_ok=True)
                self.store.stage(doc,'routing')
                self.store.stage(doc,'parsing')
                parsed = parse(path,directory,self.s)
                self.store.stage(doc,'block_analysis')
                archive = build_archive(parsed)
                self.store.stage(doc,'quality_check')
                self.store.stage(doc,'rendering')
                try:
                    snaps, warnings = render(path,directory,self.s)
                    parsed['assets']['snapshots'] = snaps
                    parsed['warnings'].extend(warnings)
                    if snaps:
                        parsed['page_count'] = len(snaps)
                except Exception:
                    parsed['warnings'].append('真实页面渲染失败；可修正渲染器后重试快照。')
                self.store.stage(doc,'extracting')
                self.store.stage(doc,'cleaning')
                self.store.stage(doc,'knowledge_quality_check')
                # All external embedding work happens before the version transaction.
                nodes = [TextNode(text=s['text'], metadata={'section':s['section']}) for s in archive['sections']]
                self.store.stage(doc,'indexing')
                vectors = self.models.embed([n.text for n in nodes])
                self.store.stage(doc,'deduplicating')
                with self.store.connect() as db:
                    duplicate = db.execute('SELECT document_id,candidate_id FROM source_documents WHERE content_fingerprint=? AND version_no>0 AND document_id<>?',(archive['content_fingerprint'],doc)).fetchone()
                    if duplicate:
                        # Reject outside this transaction to avoid a second writer.
                        duplicate = dict(duplicate)
                if duplicate:
                    return self.reject(doc,duplicate)
                self.accept(doc,row,archive,parsed,nodes,vectors)
                status = 'partial_success' if parsed['warnings'] else 'succeeded'
                self.store.stage(doc,status,elapsed=round(time.monotonic()-started,3),
                                 warnings_json=dumps(parsed['warnings']), metrics_json=dumps({'pages':parsed['page_count'], 'fields':sum(v is not None for v in archive['profile'].values()), 'portraits':len(parsed['assets']['portrait']), 'chunks':len(nodes)}))
            except Exception as e:
                message = str(e) if isinstance(e,ValueError) else f'处理失败（{type(e).__name__}），请检查文件或服务配置后重试'
                self.store.stage(doc,'quality_failed' if '质量门禁' in message else 'failed', error=message,elapsed=round(time.monotonic()-started,3))
            return self.document(doc)

    def reject(self,doc,duplicate):
        with self.store.connect() as db:
            db.execute('UPDATE source_documents SET duplicate_of_document_id=?,candidate_id=? WHERE document_id=?',(duplicate['document_id'],duplicate['candidate_id'],doc))
        self.store.stage(doc,'rejected_duplicate',error='文件或归一化内容与已有来源重复，未创建版本')
        return self.document(doc)

    def accept(self,doc,row,archive,parsed,nodes,vectors):
        p = archive['profile']
        contacts = [(k,hashlib.sha256(p[k].encode()).hexdigest()) for k in ['phone','email'] if p.get(k)]
        with self.store.connect() as db:
            matched = set()
            for kind,value in contacts:
                matched.update(r[0] for r in db.execute('SELECT candidate_id FROM candidate_contacts WHERE type=? AND value_hash=?',(kind,value)))
            if len(matched)>1:
                raise ValueError('电话与邮箱关联不同候选人，需人工核对，未更新任何档案')
            # Without contact information, require same name and identical education entry.
            if not matched and not contacts and archive['education']:
                education = re.sub(r'\s+','',archive['education'][0]['text'])
                for r in db.execute('SELECT c.candidate_id,a.data_json FROM candidates c JOIN archive_records a ON a.document_id=c.latest_document_id WHERE c.name=?',(p['name'],)):
                    old = json.loads(r['data_json'])
                    if any(re.sub(r'\s+','',e['text'])==education for e in old['education']):
                        matched.add(r['candidate_id'])
            candidate = next(iter(matched)) if len(matched)==1 else uid('cand')
            version = db.execute('SELECT coalesce(max(version_no),0)+1 FROM source_documents WHERE candidate_id=?',(candidate,)).fetchone()[0]
            knowledge_id = uid('knowledge')
            source = dict(filename=row['filename'],sha256=row['sha256'],uploaded_at=row['uploaded_at'],
                          page_count=parsed['page_count'],parser=parsed['parser'],parser_version='1.0',version_no=version,
                          content_fingerprint=archive['content_fingerprint'])
            record = dict(schema_version='1.0',document_id=doc,candidate_id=candidate,source=source,
                          profile=p,field_evidence=archive['field_evidence'],
                          parsing={'router':{'type':'deterministic-native-mvp','version':'1.0'},'quality_gate':{'status':'passed'},
                                   'pages':[{'page_no':n,'strategy':'native','reason':'原生文本可读取；MVP 未启用 OCR/视觉','confidence':.85} for n in range(1,(parsed['page_count'] or 1)+1)]},
                          blocks={'layout_blocks':parsed['elements'],'semantic_blocks':archive['semantic_blocks'],
                                  'chunks':[{'node_id':n.node_id,'section':s['section']} for n,s in zip(nodes,archive['sections'])]},
                          tables=parsed['tables'],evidence=parsed['elements'],assets=parsed['assets'],
                          quality={'status':'partial_success' if parsed['warnings'] else 'succeeded','warnings':parsed['warnings']},
                          **{k:archive[k] for k in ['education','employment','projects','skills','relationships']})
            knowledge = dict(knowledge_schema_version='1.0',knowledge_id=knowledge_id,candidate_id=candidate,
                             source_document_id=doc,version_no=version,status='ready',clean_version='1.0',
                             sections=[{'section':s['section'],'text':s['text']} for s in archive['sections']],clean_text=archive['clean_text'])
            kp = self.s.data_dir/'knowledge'/candidate
            kp.mkdir(exist_ok=True)
            artifact = kp/f'knowledge_v{version:03d}.json'
            record['knowledge_projection'] = dict(status='ready',knowledge_id=knowledge_id,artifact_path=str(artifact))
            Archive.model_validate(record)
            Knowledge.model_validate(knowledge)
            (self.s.data_dir/'processed'/f'{doc}.json').write_text(dumps(record),encoding='utf-8')
            artifact.write_text(dumps(knowledge),encoding='utf-8')
            artifact.with_suffix('.txt').write_text(archive['clean_text'],encoding='utf-8')
            old_chunks = [r[0] for r in db.execute('SELECT chunk_id FROM chunks WHERE candidate_id=? AND is_active=1',(candidate,))]
            for cid in old_chunks:
                db.execute('DELETE FROM chunks_fts WHERE rowid=?',(cid,))
                db.execute('DELETE FROM chunk_vectors WHERE rowid=?',(cid,))
            db.execute('UPDATE chunks SET is_active=0 WHERE candidate_id=?',(candidate,))
            db.execute('UPDATE source_documents SET is_active=0 WHERE candidate_id=?',(candidate,))
            db.execute('UPDATE knowledge_documents SET is_active=0 WHERE candidate_id=?',(candidate,))
            db.execute('INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?,?,?,?)', (candidate,p['name'],p['current_city'],p['years_experience'],p['degree'],doc,row['uploaded_at'],dumps(p)))
            db.execute('UPDATE source_documents SET candidate_id=?,content_fingerprint=?,version_no=?,is_active=1 WHERE document_id=?',(candidate,archive['content_fingerprint'],version,doc))
            for kind,value in contacts:
                db.execute('INSERT OR IGNORE INTO candidate_contacts VALUES (?,?,?)',(candidate,kind,value))
            db.execute('INSERT INTO knowledge_documents VALUES (?,?,?,?,?,?,?,?)',(knowledge_id,candidate,doc,version,archive['clean_text'],'ready',1,str(artifact)))
            for node,section,vec in zip(nodes,archive['sections'],vectors):
                cid = db.execute('INSERT INTO chunks(knowledge_id,candidate_id,section,text,is_active,node_id) VALUES (?,?,?,?,1,?)',(knowledge_id,candidate,section['section'],node.text,node.node_id)).lastrowid
                db.execute('INSERT INTO chunks_fts(rowid,text) VALUES (?,?)',(cid,' '.join(tokens(node.text))))
                db.execute('INSERT INTO chunk_vectors(rowid,embedding) VALUES (?,?)',(cid,serialize_float32(vec)))
                db.execute('INSERT INTO knowledge_provenance VALUES (?,?,?)',(cid,doc,dumps(section['evidence_ids'])))
            for e in parsed['elements']:
                db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?)',(e['evidence_id'],doc,e['page_no'],e['element_type'],e['text'],dumps(e['bbox'])))
            for kind,assets in parsed['assets'].items():
                for asset in assets:
                    db.execute('INSERT INTO assets(document_id,type,data_json) VALUES (?,?,?)',(doc,kind,dumps(asset)))
            for kind in ['education','employment','projects','skills','relationships']:
                for entry in archive[kind]:
                    db.execute(f'INSERT INTO {kind} VALUES (?,?,?)',(candidate,doc,dumps(entry)))
            for table in parsed['tables']:
                db.execute('INSERT INTO tables VALUES (?,?,?)',(table['table_id'],doc,dumps(table)))
                for cell in table['cells']:
                    db.execute('INSERT INTO table_cells VALUES (?,?,?,?,?)',(table['table_id'],doc,cell['row_no'],cell['col_no'],dumps(cell)))
            db.execute('INSERT OR REPLACE INTO archive_records VALUES (?,?)',(doc,dumps(record)))
            for stage in ['version_accepted','knowledge_indexing']:
                db.execute('INSERT INTO processing_jobs(document_id,stage,status,created_at) VALUES (?,?,?,?)',(doc,stage,'processing',now()))

    def candidates(self,city='',role='',min_years=None):
        rows = self.store.rows('SELECT c.*,(SELECT count(*) FROM source_documents s WHERE s.candidate_id=c.candidate_id) source_count FROM candidates c ORDER BY latest_uploaded_at DESC')
        result = []
        for row in rows:
            profile = json.loads(row.pop('profile_json'))
            if city and row['city'] != city: continue
            if role and role.lower() not in ' '.join(profile['target_roles']).lower(): continue
            if min_years is not None and (row['years_experience'] is None or row['years_experience']<min_years): continue
            row['target_roles'] = profile['target_roles']
            result.append(row)
        return result

    def archive(self,doc,raw=False):
        rows = self.store.rows('SELECT data_json FROM archive_records WHERE document_id=?',(doc,))
        if not rows: raise KeyError(doc)
        value = json.loads(rows[0]['data_json'])
        def mask(item, key=''):
            if isinstance(item,dict):
                return {k:mask(v,k) for k,v in item.items()}
            if isinstance(item,list):
                return [mask(v,key) for v in item]
            if isinstance(item,str) and key in {'text','summary','phone','email','value','raw_text','description'}:
                return redact(item)
            return item
        return mask(value) if self.s.mask_contacts and not raw else value

    def retry(self,doc):
        row = self.document(doc)
        if row['is_active']:
            return self.retry_render(doc)
        if row['status']=='processing':
            raise ValueError('任务仍在处理中')
        return self.process(doc)

    def retry_render(self,doc):
        with self.lock:
            row = self.store.rows('SELECT * FROM source_documents WHERE document_id=?',(doc,))[0]
            snaps,warnings = render(Path(row['path']),self.s.data_dir/'processed'/doc,self.s)
            record = self.archive(doc,raw=True)
            record['assets']['snapshots'] = snaps
            # Keep parser warnings, replace renderer warnings.
            previous = [w for w in record['quality']['warnings'] if not any(s in w for s in ['LibreOffice','渲染','快照'])]
            warnings = previous + warnings
            record['quality'] = {'status':'partial_success' if warnings else 'succeeded','warnings':warnings}
            with self.store.connect() as db:
                db.execute('UPDATE archive_records SET data_json=? WHERE document_id=?',(dumps(record),doc))
                db.execute("DELETE FROM assets WHERE document_id=? AND type='snapshots'",(doc,))
                for snap in snaps:
                    db.execute('INSERT INTO assets(document_id,type,data_json) VALUES (?,\'snapshots\',?)',(doc,dumps(snap)))
            (self.s.data_dir/'processed'/f'{doc}.json').write_text(dumps(record),encoding='utf-8')
            self.store.stage(doc,record['quality']['status'],warnings_json=dumps(warnings))
            return self.document(doc)
