from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "data" / "templates"
AVATAR_DIR = ROOT / "data" / "avatars"
OUTPUT_DIR = ROOT / "data"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def paragraph_text(p):
    return "".join(p.xpath(".//w:t/text()", namespaces=NS))


def set_paragraph_text(p, value):
    nodes = p.xpath(".//w:t", namespaces=NS)
    if not nodes:
        return
    nodes[0].text = value
    for node in nodes[1:]:
        node.text = ""
    if value and value[0].isspace():
        nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def resized_avatar_bytes(source, width, height):
    image = Image.open(source).convert("RGB")
    target_ratio = width / height
    ratio = image.width / image.height
    if ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        left = (image.width - new_width) // 2
        image = image.crop((left, 0, left + new_width, image.height))
    else:
        new_height = int(image.width / target_ratio)
        top = (image.height - new_height) // 2
        image = image.crop((0, top, image.width, top + new_height))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    buf = BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build_from_template(template_name, output_name, paragraph_updates, avatar_name, avatar_size):
    template_path = TEMPLATE_DIR / template_name
    output_path = OUTPUT_DIR / output_name
    avatar_path = AVATAR_DIR / avatar_name

    with ZipFile(template_path, "r") as src:
        document_root = etree.fromstring(src.read("word/document.xml"))
        paragraphs = document_root.xpath("//w:p", namespaces=NS)
        for index, value in paragraph_updates.items():
            if index >= len(paragraphs):
                raise IndexError(f"{template_name}: paragraph index {index} is out of range")
            set_paragraph_text(paragraphs[index], value)
        document_xml = etree.tostring(document_root, xml_declaration=True, encoding="UTF-8", standalone="yes")
        avatar_bytes = resized_avatar_bytes(avatar_path, *avatar_size)
        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "word/document.xml":
                    data = document_xml
                elif item.filename == "word/media/image1.png":
                    data = avatar_bytes
                dst.writestr(item, data)
    print(output_path)


build_from_template(
    "template04.docx",
    "resume_09_han_zimo_ios_template04.docx",
    {
        5: "韩子墨",
        6: "求职目标：iOS 开发工程师",
        7: "年龄：30岁",
        8: "地址：上海市闵行区  手机：186 2187 4621",
        9: "邮箱：zimo.han.cv@example.com",
        14: "自我评价  ABOUT ME          掌握技能  SKILL",
        17: "5 年 iOS 开发经验，能够独立负责企业移动端功能从需求评审到上架发布；",
        18: "重视代码质量和用户体验，擅长在复杂业务中拆解问题并推动落地。",
        19: "Swift · Objective-C · UIKit · SwiftUI · Xcode",
        21: "项目经历",
        22: "门店运营工作台",
        23: "门店运营工作台",
        25: "PROJECT EXPERIENCE",
        26: "Swift · UIKit · SwiftUI · Combine",
        28: "商户工作台 App",
        29: "2022.03-2022.08  负责开发",
        31: "面向连锁门店的订单与库存工作台，负责登录、订单列表、库存同步和消息提醒等核心模块。",
        32: "通过组件化和缓存优化，核心页面首屏时间降低 35%，配合产品与测试完成多轮版本验收。",
        33: "英语",
        35: "教育背景",
        37: "EDUCATION",
        39: "工作经历  WORK  EXPERIENCE",
        40: "上海大学",
        42: "上海矩阵云信息技术有限公司",
        43: "iOS 高级开发工程师",
        44: "负责企业移动端工作台和客户 App 迭代，参与架构拆分、组件封装、线上问题排查与版本发布。",
        45: "客户 App 会员体系",
        47: "负责会员权益、支付结果页和推送消息模块，结合埋点与崩溃监控优化用户路径。",
        49: "2021.04至今",
        54: "2019.07-2021.03",
        55: "2012.09-2016.06",
        56: "软件工程（本科）",
        57: "主修计算机网络、数据结构、移动应用开发、数据库原理、软件工程。",
        58: "熟悉敏捷开发流程，能够阅读接口文档并参与技术方案评审。",
        59: "",
        61: "负责组件化改造、网络层封装及多设备适配，协同产品和测试完成版本验收。",
        62: "门店运营助手",
        64: "核心优势",
        66: "SPECIALTY",
        69: "5 年 iOS 开发经验，熟悉从需求评审到上架发布的完整流程。",
        70: "2020.06-2020.12",
        72: "熟悉 Swift、Objective-C、UIKit、SwiftUI、Combine 等开发工具和框架；",
        74: "能够独立完成复杂页面、网络请求、数据持久化与性能优化。",
        76: "职业标签  HOBBY",
        77: "Swift / iOS 架构 / 性能优化",
        78: "熟悉 Git、Jira、CI/CD，重视代码规范与可测试性；",
        79: "具备良好的跨团队沟通、文档归纳和问题定位能力。",
        85: "跑步  摄影  城市漫游",
        110: "阅读  咖啡",
        111: "持续关注移动端新技术与产品体验。",
    },
    "tang_ziang.png",
    (144, 144),
)


build_from_template(
    "template03.docx",
    "resume_10_lin_ruoxi_customer_success_template03.docx",
    {
        1: "林若溪  客户成功          求职意向：客户成功经理",
        3: "年龄：30岁",
        4: "现居：浙江杭州",
        7: "+86 185 5712 6408",
        8: "ruoxi.lin.cv@example.com",
        11: "教育背景      EDUCATION",
        12: "2014.09 – 2018.06                   浙江工商大学                   信息管理与信息系统 / 本科",
        13: "主修课程：客户关系管理、管理信息系统、数据分析、市场营销、项目管理",
        14: "与商务沟通，具备企业服务产品的业务理解基础",
        22: "自我评价       ABOUT ME",
        23: "6 年 SaaS 客户成功与客户运营经验，擅长客户上线、培训、续约和增购管理。沟通耐心、结果导向，能够把客户反馈转化为产品和服务优化建议。",
        27: "荣誉奖励       AWARD",
        28: "2023 年客户续约率提升专项奖",
        29: "2022 年优秀项目负责人 / 客户满意度 4.8/5",
        30: "英语六级 / PMP 项目管理培训证书",
        39: "工作经历       EXPERIENCE",
        40: "2021.06-至今                           杭州知行云科技有限公司                           岗位：客户成功经理",
        41: "1.负责 40+ 家企业客户的上线、培训、续约和增购，年度续约率 96%；",
        42: "2.建立客户健康度看板，推动高风险客户预警，续约预测准确率提升 20%；",
        43: "3.联合产品与交付团队沉淀行业方案，带动 6 个客户完成增购。",
        44: "2018.07-2021.05                        上海百应信息技术有限公司                        岗位：客户运营专员",
        45: "1.负责 SaaS 产品上线支持、用户培训和工单协调，服务 120+ 家中小企业；",
        46: "2.整理客户反馈与需求池，推动 10 余项体验优化上线，降低重复咨询。",
        47: "2016.07-2018.06                        杭州云智科技有限公司                        岗位：实施顾问",
        48: "1.负责项目配置、数据导入和验收支持，协调客户、产品与研发推进交付；",
        49: "2.沉淀实施手册与培训材料，缩短新客户上手周期约 30%。",
    },
    "fang_kexin.png",
    (339, 384),
)
