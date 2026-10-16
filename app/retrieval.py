import json
import re
import time
from collections import defaultdict
from sqlite_vec import serialize_float32
from app.knowledge import CITIES, redact
from app.models import tokens
from app.service import uid
from app.storage import now, dumps


def search(service, query, city='', min_years=None, degree='', top_k=5, keyword=True, vector=True):
    started = time.monotonic()
    s, store = service.s, service.store
    if not query.strip():
        raise ValueError('请输入岗位、技能或经历条件')
    if not keyword and not vector:
        raise ValueError('请至少启用一种检索策略')
    if re.search(r'男性|女性|男生|女生|男士|女士|年龄|\d+岁|婚育|已婚|未婚|照片|民族|性别',query):
        return dict(answer='不支持按年龄、性别、婚育、照片或民族筛选。请使用岗位、技能和工作经历条件。',results=[],debug={},warnings=[],mode='policy',retrieval_run_id=None)
    city = city or next((c for c in CITIES if c in query), '')
    years = re.search(r'(\d+)\s*年(?:以上|及以上|起)',query)
    if min_years is None and years:
        min_years = int(years[1])
    degree = degree or next((d for d in ['博士','硕士','本科','大专'] if d in query),'')
    eligible = {c['candidate_id']:c for c in service.candidates(city=city,min_years=min_years)}
    if degree:
        ranks = {'大专':1,'本科':2,'硕士':3,'博士':4}
        eligible = {k:v for k,v in eligible.items() if ranks.get(v['degree'],0)>=ranks[degree]}
    if '应届' in query:
        eligible = {k:v for k,v in eligible.items() if v['years_experience']==0}
    # Named technologies are explicit requirements, not optional ranking hints.
    technologies = ['Java','Spring Boot','MySQL','Python','SaaS','Swift','Objective-C','Rust','React','Vue','Docker','Kafka','Redis','pytest','Figma']
    required_skills = [t for t in technologies if re.search(r'(?<![a-z])'+re.escape(t)+r'(?![a-z])',query,re.I)]
    if required_skills:
        knowledge = {r['candidate_id']:r['clean_text'].lower() for r in store.rows('SELECT candidate_id,clean_text FROM knowledge_documents WHERE is_active=1')}
        eligible = {k:v for k,v in eligible.items() if all(t.lower() in knowledge.get(k,'') for t in required_skills)}
    query_terms = list(dict.fromkeys(tokens(query)))[:64]
    bm25, distances, warnings = [], [], []
    with store.connect() as db:
        chunks = {r['chunk_id']:dict(r) for r in db.execute('SELECT * FROM chunks WHERE is_active=1') if r['candidate_id'] in eligible}
        if keyword and query_terms:
            match = ' OR '.join('"'+term.replace('"','""')+'"' for term in query_terms)
            bm25 = [dict(r) for r in db.execute('SELECT rowid,bm25(chunks_fts) score FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY score',(match,)) if r['rowid'] in chunks]
        if vector and chunks:
            try:
                qvec = service.models.embed([query])[0]
                distances = [dict(r) for r in db.execute('SELECT rowid,vec_distance_cosine(embedding,?) distance FROM chunk_vectors ORDER BY distance',(serialize_float32(qvec),)) if r['rowid'] in chunks and 1-r['distance'] >= s.min_vector_similarity]
                if s.embedding_provider=='local-hash':
                    # Hash collisions are not semantic evidence. Require real token overlap.
                    distances = [r for r in distances if set(query_terms) & set(tokens(chunks[r['rowid']]['text']))]
            except Exception:
                warnings.append('向量召回失败，请检查 embedding 服务配置；当前仅使用可用的关键词结果。')
    # Aggregate each channel by candidate BEFORE RRF; many chunks cannot inflate rank.
    channels, best = {}, defaultdict(set)
    for name,rows in [('bm25',bm25),('vector',distances)]:
        ranking = []
        seen = set()
        for r in rows:
            cid = chunks[r['rowid']]['candidate_id']
            if cid not in seen:
                ranking.append({'candidate_id':cid,'chunk_id':r['rowid'],'raw_score':r.get('score',1-r.get('distance',1))})
                seen.add(cid)
            if len(best[cid])<3:
                best[cid].add(r['rowid'])
        channels[name] = ranking
    scores = defaultdict(float)
    details = defaultdict(dict)
    for channel,weight in [('bm25',s.keyword_weight),('vector',s.vector_weight)]:
        for rank,item in enumerate(channels[channel],1):
            cid=item['candidate_id']
            scores[cid] += weight/(s.rrf_k+rank)
            details[cid][channel] = {'rank':rank,'score':item['raw_score']}
    results = []
    for cid in sorted(scores,key=scores.get,reverse=True)[:top_k]:
        candidate = eligible[cid]
        evidence = []
        selected = sorted(best[cid])
        with store.connect() as db:
            for chunk_id in selected:
                provenance = db.execute('SELECT * FROM knowledge_provenance WHERE chunk_id=?',(chunk_id,)).fetchone()
                for eid in json.loads(provenance['evidence_ids']):
                    row = db.execute('SELECT * FROM evidence WHERE document_id=? AND evidence_id=?',(provenance['source_document_id'],eid)).fetchone()
                    if row:
                        e = dict(row)
                        e['text'] = redact(e['text'])
                        e['url'] = f"/api/documents/{e['document_id']}/evidence/{eid}"
                        if not any(x['evidence_id']==eid for x in evidence): evidence.append(e)
        doc = service.document(candidate['latest_document_id'])
        citation = f"[{doc['filename']} · v{doc['version_no']}](/api/documents/{doc['document_id']}/original)"
        results.append(dict(**candidate,rrf_score=round(scores[cid],6),scores=details[cid],
                            context='\n'.join(chunks[k]['text'] for k in selected),
                            matched_terms=[t for t in query_terms if t in '\n'.join(chunks[k]['text'].lower() for k in selected)],
                            citation=citation,evidence=evidence,chunk_ids=selected))
    retrieval_ms = round((time.monotonic()-started)*1000,2)
    answer,mode,generation_warnings = service.models.answer(query,results)
    warnings += generation_warnings
    if s.embedding_provider=='local-hash':
        warnings.append('离线模式使用词项哈希向量，仅验证检索流程；语义理解需配置 embedding 模型。')
    run = uid('run')
    debug = dict(filters={'city':city or None,'min_years':min_years,'degree':degree or None,'required_skills':required_skills},eligible_count=len(eligible),
                 channels=channels,rrf_k=s.rrf_k,weights={'bm25':s.keyword_weight,'vector':s.vector_weight},
                 embedding=service.models.signature,retrieval_ms=retrieval_ms,total_ms=round((time.monotonic()-started)*1000,2),
                 query_terms=query_terms,node_ids=[chunks[k]['node_id'] for h in results for k in h['chunk_ids']])
    result = dict(retrieval_run_id=run,answer=answer,results=results,debug=debug,warnings=warnings,mode=mode)
    with store.connect() as db:
        # Audit metadata only, avoid retaining the user's potentially sensitive query.
        db.execute('INSERT INTO retrieval_runs VALUES (?,?,?)',(run,now(),dumps({'debug':{k:v for k,v in debug.items() if k!='query_terms'},'candidate_ids':[r['candidate_id'] for r in results],'model':mode})))
    return result
