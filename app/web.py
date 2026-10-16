"""Gradio presentation layer: all business operations use the HTTP API."""
import html
import json
from contextlib import ExitStack
from pathlib import Path
import httpx
import gradio as gr
from app.config import Settings

CSS = """
.gradio-container {max-width:1280px!important; margin:auto; background:#f5f8f8!important;}
#hero {background:#103d3b;border-radius:18px;padding:32px 36px;margin:12px 0 20px;color:#fff;}
#hero h1 {color:#fff;font-size:32px;margin:9px 0;font-weight:700;letter-spacing:1px;}
#hero p {color:#b7d4d0;font-size:15px;line-height:1.7;}
.eyebrow {font:12px monospace;letter-spacing:3px;color:#80d3bd;}
#metrics {display:flex;gap:16px;margin:8px 0 20px;}
.stat {background:white;border:1px solid #dce7e5;border-radius:12px;padding:18px 24px;flex:1;}
.stat b {font-size:25px;color:#164f49;display:block;margin-top:6px;}
.stat span {color:#607570;font-size:12px;}
.candidate {border:1px solid #dbe6e3;border-radius:12px;background:white;padding:20px;margin:12px 0;}
.candidate h3 {margin:0 0 8px;color:#174e48;}
.candidate p {line-height:1.7;white-space:pre-wrap;font-size:14px;color:#52645f;}
.tag {background:#edf7f3;color:#246b59;padding:3px 9px;border-radius:6px;font-size:12px;margin:0 6px 0 0;}
.quiet {color:#71817e;font-size:12px;}
footer {display:none!important;}
"""


def build_ui(settings):
    def api(method,path,**kwargs):
        try:
            with httpx.Client(base_url=settings.api_url,timeout=180,trust_env=False) as client:
                r=client.request(method,path,**kwargs)
            if r.is_error:
                raise gr.Error(r.json().get('detail','服务请求失败'))
            return r.json()
        except httpx.HTTPError:
            raise gr.Error('无法连接后端，请检查服务状态和 HR_API_URL。')

    def stats():
        h=api('GET','/api/health')
        mode='语义模型' if not h['embedding'].startswith('local-hash') else '离线演示'
        return '<div id="metrics">'+''.join(f'<div class="stat"><span>{k}</span><b>{v}</b></div>' for k,v in [('候选人档案',h['candidates']),('来源文档',h['documents']),('检索模式',mode),('证据溯源','已启用')])+'</div>'

    def jobs():
        rows=api('GET','/api/documents')
        data=[[r['filename'],r['stage'],r['elapsed'],r['metrics'].get('pages'),r['metrics'].get('chunks'),r['error'] or '；'.join(r['warnings']),r['document_id']] for r in rows]
        choices=[(r['filename']+' · '+r['status'],r['document_id']) for r in rows if r['status']!='processing']
        return data,gr.Dropdown(choices=choices)

    def upload(files):
        if not files: raise gr.Error('请先选择简历文件')
        with ExitStack() as stack:
            parts=[('files',(Path(p).name,stack.enter_context(open(p,'rb')))) for p in files]
            data=api('POST','/api/documents',files=parts)
        rejected=[x for x in data['documents'] if x.get('status')=='failed']
        return f"已提交 {len(data['documents'])-len(rejected)} 个处理任务。" + ('\n'+json.dumps(rejected,ensure_ascii=False) if rejected else '')

    def library(city,role):
        rows=api('GET','/api/candidates',params={'city':city.strip(),'role':role.strip()})
        values=[[r['name'],' / '.join(r['target_roles']),r['city'] or '未提供',r['years_experience'] if r['years_experience'] is not None else '未提供',r['degree'] or '未提供',r['source_count'],r['candidate_id']] for r in rows]
        return values,gr.Dropdown(choices=[(r['name']+' · '+' / '.join(r['target_roles']),r['candidate_id']) for r in rows])

    def detail(candidate):
        if not candidate: return '',{},'', '',{}
        r=api('GET',f'/api/candidates/{candidate}')
        doc=r['document_id']
        links='\n'.join(f"- [{d['filename']} · v{d['version_no']} · {d['status']}]({settings.api_url}/api/documents/{d['document_id']}/original)" for d in r['documents'])
        snaps=''.join(f'<a href="/api/documents/{doc}/snapshots/{s["page_no"]}" target="_blank"><img style="max-width:380px;border:1px solid #ddd;margin:8px" src="/api/documents/{doc}/snapshots/{s["page_no"]}" alt="第 {s["page_no"]} 页原始快照"></a>' for s in r['assets']['snapshots'])
        if not snaps: snaps='<p class="quiet">真实页面快照尚未生成。请查看处理警告，配置 LibreOffice 后重试。</p>'
        return r['knowledge'],r['profile'],links,snaps.replace('"/api/',f'"{settings.api_url}/api/'),r

    def query(text,city,years,degree,count,kw,vec):
        data=api('POST','/api/search',json={'query':text,'city':city.strip(),'min_years':years if years is not None and years>0 else None,'degree':degree or '', 'top_k':int(count),'keyword':kw,'vector':vec})
        cards=[]
        for i,r in enumerate(data['results'],1):
            tags=''.join(f'<span class="tag">{html.escape(str(v))}</span>' for v in [r['city'] or '城市未提供',str(r['years_experience'])+' 年' if r['years_experience'] is not None else '年限未提供',' / '.join(r['target_roles'])])
            evidence=' · '.join(f'<a target="_blank" href="{e["url"]}">证据 {j+1}'+(f' / 第 {e["page_no"]} 页' if e['page_no'] else ' / 原始元素')+'</a>' for j,e in enumerate(r['evidence'][:5]))
            cards.append(f'<article class="candidate"><h3>{i:02d}　{html.escape(r["name"])}</h3>{tags}<p>{html.escape(r["context"][:650])}</p><div class="quiet">RRF {r["rrf_score"]:.4f} · {evidence}</div></article>')
        explanation='\n\n'.join(data['warnings'])
        return data['answer'].replace('](/api/',f']({settings.api_url}/api/'),('\n'.join(cards) or '<p>暂无匹配候选人</p>').replace('"/api/',f'"{settings.api_url}/api/'),data['debug'],explanation

    with gr.Blocks(title='人才知库 · 招聘档案 RAG',analytics_enabled=False) as ui:
        gr.HTML('<section id="hero"><div class="eyebrow">TALENT ATLAS / 人才知库</div><h1>让每一份经历，都被看见。</h1><p>将简历沉淀为可检索的人才档案，用自然语言发现匹配经历，回到原始证据验证。</p></section>')
        metrics=gr.HTML()
        with gr.Tabs():
            with gr.Tab('人才检索'):
                with gr.Row():
                    with gr.Column(scale=3):
                        gr.Markdown('### 描述你需要的人才\n从岗位、技能或真实业务经历开始。')
                        q=gr.Textbox(label='检索条件',placeholder='例如：熟悉 Java、Spring Boot、MySQL 的后端应届生',lines=3)
                        gr.Examples(examples=[['熟悉 Java、Spring Boot、MySQL 的后端应届生'],['上海 5 年以上 SaaS 产品经验，做过客户服务或知识库'],['带领测试团队并做过接口自动化']],inputs=q)
                        submit=gr.Button('检索人才 →',variant='primary')
                    with gr.Column(scale=1):
                        gr.Markdown('### 检索设置')
                        qcity=gr.Textbox(label='城市（可选）',placeholder='留空时从查询识别')
                        years=gr.Number(label='最低工作年限（0 表示不限）',value=0,minimum=0,maximum=60)
                        degree=gr.Dropdown(['','大专','本科','硕士','博士'],value='',label='最低学历')
                        count=gr.Slider(1,10,value=5,step=1,label='返回人数')
                        kw=gr.Checkbox(value=True,label='关键词 · BM25')
                        vec=gr.Checkbox(value=True,label='向量召回')
                notice=gr.Markdown('无密钥时使用离线词项哈希向量与证据摘录。匹配结果供招聘人员复核。')
                answer=gr.Markdown()
                cards=gr.HTML()
                with gr.Accordion('检索调试 · 过滤、召回与融合',open=False):
                    debug=gr.JSON()
                submit.click(query,[q,qcity,years,degree,count,kw,vec],[answer,cards,debug,notice])
            with gr.Tab('上传与处理'):
                gr.Markdown('### 建立你的招聘档案库\n支持 DOCX、PPTX、PDF；同一候选人自动归并，完全重复文档拒收。')
                with gr.Row():
                    with gr.Column():
                        files=gr.File(label=f'选择简历 · 每份最多 {settings.max_file_mb} MB',file_count='multiple',file_types=['.docx','.pptx','.pdf'],type='filepath')
                        send=gr.Button('上传并建立档案',variant='primary')
                    with gr.Column():
                        gr.Markdown('#### 先试试合成样本\n仓库包含 12 份来源文件、10 位虚构候选人。导入后即可体验自然语言检索。\n\n扫描件需要 OCR，当前 MVP 会提示失败；Office 快照需要 LibreOffice。')
                        demo=gr.Button('导入 12 份演示简历')
                upload_status=gr.Markdown()
                jobs_table=gr.Dataframe(headers=['文件','当前阶段','耗时 / 秒','页数','知识块','警告或失败原因','任务 ID'],interactive=False,wrap=True)
                refresh=gr.Button('刷新处理状态')
                with gr.Row():
                    retry_doc=gr.Dropdown(label='选择需要重试的任务',choices=[])
                    retry=gr.Button('重试处理 / 补齐快照')
                send.click(upload,files,upload_status).then(jobs,outputs=[jobs_table,retry_doc])
                demo.click(lambda: '已提交 '+str(len(api('POST','/api/demo/import')['documents']))+' 份演示简历，后台处理中。',outputs=upload_status).then(jobs,outputs=[jobs_table,retry_doc])
                refresh.click(jobs,outputs=[jobs_table,retry_doc]).then(stats,outputs=metrics)
                retry.click(lambda d: ('已提交重试：'+api('POST',f'/api/documents/{d}/retry')['document_id']) if d else '请先选择任务',retry_doc,upload_status)
                gr.Timer(4).tick(lambda: jobs()[0],outputs=jobs_table,show_progress='hidden')
            with gr.Tab('档案库与证据'):
                with gr.Row():
                    city=gr.Textbox(label='城市',placeholder='全部城市')
                    role=gr.Textbox(label='岗位包含',placeholder='全部岗位')
                    refresh_library=gr.Button('查询档案库',variant='primary')
                candidates=gr.Dataframe(headers=['姓名','求职方向','城市','工作年限','学历','来源数','候选人 ID'],interactive=False,wrap=True)
                selected=gr.Dropdown(label='查看候选人详情',choices=[])
                with gr.Tabs():
                    with gr.Tab('干净知识档案'):
                        knowledge=gr.Markdown()
                    with gr.Tab('结构化字段'):
                        profile=gr.JSON()
                    with gr.Tab('来源与页面快照'):
                        gr.Markdown('原文件下载包含完整个人信息，仅供本地演示复核。')
                        sources=gr.Markdown()
                        snapshots=gr.HTML()
                    with gr.Tab('解析 JSON 与表格'):
                        raw=gr.JSON()
                refresh_library.click(library,[city,role],[candidates,selected]).then(stats,outputs=metrics)
                selected.change(detail,selected,[knowledge,profile,sources,snapshots,raw])
        gr.Markdown('人才知库 · 本地招聘 RAG 演示　｜　原件与知识分离 · 最新版本检索 · 可追溯证据')
        ui.load(stats,outputs=metrics)
        ui.load(lambda: library('',''),outputs=[candidates,selected])
        ui.load(jobs,outputs=[jobs_table,retry_doc])
    return ui


if __name__=='__main__':
    settings=Settings()
    build_ui(settings).launch(server_name=settings.host,server_port=settings.ui_port,
                              theme=gr.themes.Soft(primary_hue='teal'),css=CSS,share=False)
