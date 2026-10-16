"""Reproducible baseline report. Run python -m scripts.verify_demo."""
import json
from app.config import Settings, ROOT
from app.service import Service
from app.retrieval import search

def main():
    s=Service(Settings())
    if not s.candidates():
        for path in sorted((ROOT/'synthetic-data/cv').glob('*')):
            result=s.process(s.register(path.name,path.read_bytes()))
            print(path.name,result['status'],result['error'])
    report={'candidates':s.candidates(),'queries':[]}
    for query in ['熟悉 Java、Spring Boot、MySQL 的后端应届生','上海 5 年以上 SaaS 产品经验，做过客户服务或知识库','带领测试团队并做过接口自动化','量子芯片光刻专家']:
        result=search(s,query)
        names=[r['name'] for r in result['results']]
        report['queries'].append({'query':query,'names':names,'ms':result['debug'].get('retrieval_ms')})
        print(query,names)
    (s.s.data_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
