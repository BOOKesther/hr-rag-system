from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree

source = Path("data/resume_10_lin_ruoxi_customer_success_template03.docx")
target = Path("tools/resume_10_lin_ruoxi_customer_success_template03_fixed.docx")
ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

updates = {
    "某某某旗舰    求职意向：医护岗位": "林若溪  客户成功          求职意向：客户成功经理",
    "年龄：25岁": "年龄：30岁",
    "现居：福建厦门": "现居：浙江杭州",
    "+86 180 5252 5252": "+86 185 5712 6408",
    "1213123@QQ.com": "ruoxi.lin.cv@example.com",
    "教育背景      EDUCATION ": "教育背景      EDUCATION",
    "2013.09 – 2017.06                   南京邮电大学通达学院                   护理学专业 / 本科": "2014.09 – 2018.06                   浙江工商大学                   信息管理与信息系统 / 本科",
    "主修课程：人体解剖学、生理学、医伦理学、诊断学、药物治疗学、护理学基础、重症护": "主修课程：客户关系管理、管理信息系统、数据分析、市场营销、项目管理",
    "理学、内科护理学等": "与商务沟通，具备企业服务产品的业务理解基础",
    "本人性格热情开朗，待人友好，为人真诚谦虚。能吃苦耐劳，尽职尽责，有耐心。学习认真，成绩优秀，品学兼优，连续三年获得学院奖学金。为人诚恳、脚踏实地，积极进取挑战。有较强的团队精神，工作积极，勤奋刻苦，态度认真。抗压能力和强烈的责任感。": "6 年 SaaS 客户成功与客户运营经验，擅长客户上线、培训、续约和增购管理。沟通耐心、结果导向，能够把客户反馈转化为产品和服务优化建议。",
    "2012年国家奖学金                                                              2012年任班长一职": "2023 年客户续约率提升专项奖",
    "2012年获三好学生称号                                                    2011年获营销大赛一等奖": "2022 年优秀项目负责人 / 客户满意度 4.8/5",
    "2012年创业杯大赛获得团体比赛铜奖                                      2014年荣获学院优秀班干部": "英语六级 / PMP 项目管理培训证书",
    "2014.08-2015.08                           上海赫尔森康复医院                                                           岗位：医生  ": "2021.06-至今                           杭州知行云科技有限公司                           岗位：客户成功经理",
    "1.负责神经系统疾病的病情诊断、治疗方案策划、病情追踪、病历书写以及治疗方案变更时的方案建议；": "1.负责 40+ 家企业客户的上线、培训、续约和增购，年度续约率 96%；",
    "2.负责特种诊断的诊断确认，例如：心电图分析、CT分析、DR分析；": "2.建立客户健康度看板，推动高风险客户预警，续约预测准确率提升 20%；",
    "3.负责在联合治疗时，科室间的诊断和治疗方案的联系与沟通，以及进度协调。": "3.联合产品与交付团队沉淀行业方案，带动 6 个客户完成增购。",
    "2013.09 – 2017.06                        青岛市华熙医院有限公司                                                     岗位：医生": "2018.07-2021.05                        上海百应信息技术有限公司                        岗位：客户运营专员",
    "1.负责各项仪器操作，按时完成诊断报告；参加 会议和临床病例讨论会；": "1.负责 SaaS 产品上线支持、用户培训和工单协调，服务 120+ 家中小企业；",
    "2.遵守各项规章制度，掌握仪器设备的原理、性能、使用技术，熟悉操作规程，做好防护，防差错工作；": "2.整理客户反馈与需求池，推动 10 余项体验优化上线，降低重复咨询。",
    "2013.09 – 2017.06                        学院青年志愿者协会财务部                                                  岗位：部长             ": "2016.07-2018.06                        杭州云智科技有限公司                        岗位：实施顾问",
    "1.组织业余活动、服务学生生活文案工作；课堂教学、组织业余活动、生活文案工作；": "1.负责项目配置、数据导入和验收支持，协调客户、产品与研发推进交付；",
    "2.熟练掌握并加强了组织活动与教学能力；巩固并检验了自己英语学习的知识水平。": "2.沉淀实施手册与培训材料，缩短新客户上手周期约 30%。",
}

with ZipFile(source, "r") as src:
    root = etree.fromstring(src.read("word/document.xml"))
    for p in root.xpath("//w:p", namespaces=ns):
        current = "".join(p.xpath(".//w:t/text()", namespaces=ns))
        if current in updates:
            nodes = p.xpath(".//w:t", namespaces=ns)
            if nodes:
                nodes[0].text = updates[current]
                for node in nodes[1:]:
                    node.text = ""
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = xml
            dst.writestr(item, data)
print(target)
