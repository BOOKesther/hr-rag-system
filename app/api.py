import json
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.config import Settings, ROOT
from app.service import Service
from app.retrieval import search


class SearchRequest(BaseModel):
    query: str = Field(min_length=1,max_length=2000)
    city: str = ''
    min_years: float | None = Field(None,ge=0,le=60)
    degree: str = ''
    top_k: int = Field(5,ge=1,le=20)
    keyword: bool = True
    vector: bool = True


def create_app(settings=None, mount_ui=True):
    settings = settings or Settings()
    service = Service(settings)
    executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='ingestion')
    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=True)
    app = FastAPI(title='人才知库 · HR RAG',version='0.1.0',lifespan=lifespan)
    app.state.service = service

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404,content={'detail':'未找到对应档案或任务'})

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400,content={'detail':str(exc)})

    @app.get('/api/health')
    def health():
        return {'status':'ok','embedding':service.models.signature,'generation':settings.chat_model or 'extractive',
                'candidates':len(service.candidates()),'documents':service.store.rows('SELECT count(*) n FROM source_documents')[0]['n']}

    @app.post('/api/documents',status_code=202)
    async def upload(files: list[UploadFile] = File(...)):
        if not 1 <= len(files) <= settings.max_batch:
            raise HTTPException(400,f'一次最多上传 {settings.max_batch} 个文件')
        docs = []
        for file in files:
            data = await file.read(settings.max_file_mb*1024*1024+1)
            try:
                doc = service.register(file.filename or '',data)
                executor.submit(service.process,doc)
                docs.append({'document_id':doc,'filename':file.filename,'status':'uploaded'})
            except ValueError as e:
                docs.append({'filename':file.filename,'status':'failed','error':str(e)})
            finally:
                await file.close()
        return {'documents':docs}

    @app.post('/api/demo/import',status_code=202)
    def import_demo():
        docs=[]
        for path in sorted((ROOT/'synthetic-data'/'cv').glob('*')):
            if path.suffix.lower() in {'.docx','.pptx','.pdf'}:
                doc=service.register(path.name,path.read_bytes())
                executor.submit(service.process,doc)
                docs.append({'document_id':doc,'filename':path.name})
        return {'documents':docs}

    @app.get('/api/documents')
    def documents():
        return [service.document(r['document_id']) for r in service.store.rows('SELECT document_id FROM source_documents ORDER BY uploaded_at DESC')]

    @app.get('/api/documents/{doc}')
    def document(doc:str):
        data=service.document(doc)
        data['events']=service.store.rows('SELECT * FROM processing_jobs WHERE document_id=? ORDER BY job_id',(doc,))
        return data

    @app.post('/api/documents/{doc}/retry',status_code=202)
    def retry(doc:str):
        row=service.document(doc)
        if row['status']=='processing': raise HTTPException(409,'任务仍在处理中')
        executor.submit(service.retry,doc)
        return {'document_id':doc,'status':'queued'}

    @app.get('/api/candidates')
    def candidates(city:str='',role:str='',min_years:float|None=None):
        return service.candidates(city,role,min_years)

    @app.get('/api/candidates/{candidate}')
    def candidate(candidate:str):
        rows=service.store.rows('SELECT latest_document_id FROM candidates WHERE candidate_id=?',(candidate,))
        if not rows: raise KeyError(candidate)
        doc=rows[0]['latest_document_id']
        record=service.archive(doc)
        record['documents']=[service.document(d['document_id']) for d in service.store.rows('SELECT document_id FROM source_documents WHERE candidate_id=? ORDER BY uploaded_at DESC',(candidate,))]
        record['knowledge']=service.store.rows('SELECT clean_text FROM knowledge_documents WHERE candidate_id=? AND is_active=1',(candidate,))[0]['clean_text']
        return record

    @app.get('/api/documents/{doc}/archive')
    def archive(doc:str):
        return service.archive(doc)

    @app.get('/api/documents/{doc}/original')
    def original(doc:str):
        rows=service.store.rows('SELECT path,filename FROM source_documents WHERE document_id=?',(doc,))
        if not rows: raise KeyError(doc)
        return FileResponse(rows[0]['path'],filename=rows[0]['filename'])

    @app.get('/api/documents/{doc}/snapshots/{page}')
    def snapshot(doc:str,page:int):
        archive=service.archive(doc)
        item=next((a for a in archive['assets']['snapshots'] if a['page_no']==page),None)
        if not item: raise HTTPException(404,'此页真实快照尚未生成')
        return FileResponse(item['path'],media_type='image/png')

    @app.get('/api/documents/{doc}/portrait')
    def portrait(doc:str):
        if not settings.show_portraits: raise HTTPException(403,'默认隐藏头像，可通过环境配置启用')
        items=service.archive(doc)['assets']['portrait']
        if not items: raise HTTPException(404,'未提取头像')
        return FileResponse(items[0]['path'],media_type='image/png')

    @app.get('/api/documents/{doc}/evidence/{eid}')
    def evidence(doc:str,eid:str):
        record=service.archive(doc)
        item=next((e for e in record['evidence'] if e['evidence_id']==eid),None)
        if not item: raise KeyError(eid)
        return item

    @app.post('/api/search')
    def query(request:SearchRequest):
        return search(service,**request.model_dump())

    if mount_ui and settings.ui_mode=='mounted':
        import gradio as gr
        from app.web import build_ui, CSS
        ui=build_ui(settings)
        app=gr.mount_gradio_app(app,ui,path='/',theme=gr.themes.Soft(primary_hue='teal',neutral_hue='slate'),css=CSS,
                               blocked_paths=[str(settings.data_dir/'originals'),str(settings.data_dir/'sqlite')])
    return app
