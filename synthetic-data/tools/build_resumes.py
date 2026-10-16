from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.style import WD_STYLE_TYPE
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
AVATARS = DATA / "avatars"

NAVY = "173B57"
TEAL = "1D6F73"
MUTED = "637381"
LIGHT = "EAF1F4"
TEXT = "263238"
LINE = "C9D6DC"


def set_cell_width(cell, width_dxa):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width_dxa))
    tc_w.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths):
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_layout = tbl_pr.find(qn("w:tblLayout"))
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            set_cell_width(cell, widths[idx])


def set_cell_margins(cell, top=70, start=100, bottom=70, end=100):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def remove_table_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "nil")


def shade_cell(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_run_font(run, name="Microsoft YaHei", size=None, color=TEXT, bold=None, italic=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_paragraph_border_bottom(p, color=LINE, size="8", space="4"):
    p_pr = p._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = p_bdr.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        p_bdr.append(bottom)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), space)
    bottom.set(qn("w:color"), color)


def set_keep_with_next(p):
    p_pr = p._p.get_or_add_pPr()
    keep = p_pr.find(qn("w:keepNext"))
    if keep is None:
        p_pr.append(OxmlElement("w:keepNext"))


def add_text(p, text, size=10, color=TEXT, bold=False, italic=False):
    r = p.add_run(text)
    set_run_font(r, size=size, color=color, bold=bold, italic=italic)
    return r


def add_bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Inches(0.23)
    p.paragraph_format.first_line_indent = Inches(-0.13)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.05
    add_text(p, text, size=9.2)
    return p


def add_section_heading(doc, title, en):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    add_text(p, title, size=11.5, color=NAVY, bold=True)
    add_text(p, f"  {en.upper()}", size=8.2, color=TEAL, bold=True)
    set_paragraph_border_bottom(p, color=LINE, size="7", space="3")
    return p


def add_meta_line(doc, label, value):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = 1.0
    add_text(p, f"{label}  ", size=9.1, color=MUTED, bold=True)
    add_text(p, value, size=9.1, color=TEXT)
    return p


def add_experience(doc, item):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.keep_with_next = True
    add_text(p, item["period"], size=9.1, color=TEAL, bold=True)
    add_text(p, "  |  ", size=9.1, color=LINE)
    add_text(p, item["company"], size=10.2, color=NAVY, bold=True)
    add_text(p, f"  ·  {item['role']}", size=9.5, color=TEXT, bold=True)
    for bullet in item["bullets"]:
        add_bullet(doc, bullet)


def add_project(doc, item):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.keep_with_next = True
    add_text(p, item["name"], size=9.8, color=NAVY, bold=True)
    add_text(p, f"  |  {item['period']}", size=8.9, color=TEAL)
    for bullet in item["bullets"]:
        add_bullet(doc, bullet)


def set_document_defaults(doc):
    sec = doc.sections[0]
    # Named override: Chinese resume uses A4 with compact 0.55in margins for one-page readability.
    sec.page_width = Inches(8.27)
    sec.page_height = Inches(11.69)
    sec.top_margin = Inches(0.55)
    sec.bottom_margin = Inches(0.5)
    sec.left_margin = Inches(0.62)
    sec.right_margin = Inches(0.62)
    sec.header_distance = Inches(0.25)
    sec.footer_distance = Inches(0.25)
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(9.5)
    normal.font.color.rgb = RGBColor.from_string(TEXT)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.05
    if "Resume Bullet" not in [s.name for s in styles]:
        bullet = styles.add_style("Resume Bullet", WD_STYLE_TYPE.PARAGRAPH)
    else:
        bullet = styles["Resume Bullet"]
    bullet.base_style = styles["List Bullet"]
    bullet.font.name = "Microsoft YaHei"
    bullet._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    bullet.font.size = Pt(9.2)
    bullet.paragraph_format.space_after = Pt(2)
    bullet.paragraph_format.line_spacing = 1.05
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.space_before = Pt(0)
    footer.paragraph_format.space_after = Pt(0)
    add_text(footer, "模拟简历｜个人资料为虚构示例｜头像为 AI 生成", size=7.5, color="8A979E")


def build_resume(person):
    doc = Document()
    set_document_defaults(doc)

    top = doc.add_table(rows=1, cols=2)
    top.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_geometry(top, [8200, 1800])
    remove_table_borders(top)
    for cell in top.rows[0].cells:
        set_cell_margins(cell, top=20, start=0, bottom=20, end=0)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    left = top.cell(0, 0)
    p = left.paragraphs[0]
    p.paragraph_format.space_after = Pt(1)
    add_text(p, person["name"], size=22, color=NAVY, bold=True)
    p = left.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    add_text(p, person["target"], size=12.5, color=TEAL, bold=True)
    p = left.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    add_text(p, f"{person['age']}岁  ·  {person['gender']}  ·  {person['city']}  ·  {person['experience_years']}", size=8.8, color=MUTED)
    p = left.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    add_text(p, f"{person['phone']}  ·  {person['email']}", size=8.8, color=MUTED)
    p = left.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    add_text(p, f"期望薪资：{person['salary']}  ·  到岗：{person['availability']}", size=8.8, color=MUTED)
    right = top.cell(0, 1)
    p = right.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run()
    run.add_picture(str(AVATARS / person["avatar"]), width=Inches(1.18), height=Inches(1.18))

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(2)
    rule.paragraph_format.space_after = Pt(4)
    set_paragraph_border_bottom(rule, color=TEAL, size="14", space="1")

    add_section_heading(doc, "个人概述", "PROFILE")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.08
    add_text(p, person["summary"], size=9.4)

    add_section_heading(doc, "教育背景", "EDUCATION")
    for edu in person["education"]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.keep_with_next = True
        add_text(p, edu["period"], size=9.1, color=TEAL, bold=True)
        add_text(p, "  |  ", size=9.1, color=LINE)
        add_text(p, edu["school"], size=10.1, color=NAVY, bold=True)
        add_text(p, f"  ·  {edu['major']}（{edu['degree']}）", size=9.4, color=TEXT)
        if edu.get("detail"):
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent = Inches(0.14)
            p2.paragraph_format.space_after = Pt(2)
            add_text(p2, edu["detail"], size=8.9, color=MUTED)

    if person.get("experience"):
        add_section_heading(doc, "工作经历", "EXPERIENCE")
        for item in person["experience"]:
            add_experience(doc, item)

    if person.get("projects"):
        add_section_heading(doc, "项目经历", "PROJECTS")
        for item in person["projects"]:
            add_project(doc, item)

    add_section_heading(doc, "技能与证书", "SKILLS")
    for skill in person["skills"]:
        add_bullet(doc, skill)
    if person.get("certs"):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(1)
        add_text(p, "证书：", size=9.2, color=NAVY, bold=True)
        add_text(p, "；".join(person["certs"]), size=9.2)

    add_section_heading(doc, "自我评价", "ABOUT ME")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.08
    add_text(p, person["self"], size=9.3)

    out = DATA / person["filename"]
    doc.save(out)
    return out


people = [
    {
        "filename": "resume_01_lin_chen_backend.docx", "avatar": "lin_chen.png", "name": "林晨", "gender": "男", "age": 23, "city": "上海", "target": "后端开发工程师（Java）", "experience_years": "应届生", "phone": "138 2156 9031", "email": "lin.chen.cv@example.com", "salary": "10–13K/月", "availability": "毕业后可到岗",
        "summary": "计算机科学与技术专业应届毕业生，具备 Java 后端开发、数据库设计和接口开发基础。能从需求梳理、数据建模到接口联调独立完成小型功能模块，重视代码规范、异常处理和可测试性，期望在研发团队中持续深耕服务端工程能力。",
        "education": [{"period": "2021.09–2025.06", "school": "上海理工大学", "major": "计算机科学与技术", "degree": "本科", "detail": "GPA 3.55/4.0；主修数据结构、操作系统、数据库原理、软件工程、计算机网络、Java 程序设计。"}],
        "projects": [
            {"name": "校园二手交易平台（后端负责人）", "period": "2024.03–2024.06", "bullets": ["基于 Spring Boot + MySQL + Redis 搭建用户、商品、订单和消息模块，设计 20+ RESTful API。", "使用 Redis 缓存热门商品与验证码，结合索引优化将列表查询平均响应时间由 420ms 降至 160ms。", "通过 Swagger 编写接口文档，配合 Postman 完成联调和边界场景测试。"]},
            {"name": "智能招聘问答助手", "period": "2024.09–2025.01", "bullets": ["负责简历解析、岗位标签和问答记录模块，完成文件上传、结构化存储与权限校验。", "将常见问答整理为可检索知识条目，参与召回结果评估，提升测试集命中率约 18%。"]}
        ],
        "skills": ["熟悉 Java、Spring Boot、MyBatis，了解 Spring Cloud 基本组件和 RESTful 设计。", "熟悉 MySQL 表结构设计、SQL 优化、Redis 常用数据结构；了解 Linux 常用命令和 Git 协作流程。", "了解 Docker 基础、单元测试和持续集成概念，能够阅读英文技术文档。"],
        "certs": ["英语四级（CET-4）", "全国计算机二级"],
        "self": "逻辑清晰，遇到问题习惯先定位再验证；有较强的学习主动性和代码复盘意识。曾在课程项目中担任小组负责人，能够与前端、产品同学保持有效沟通。"
    },
    {
        "filename": "resume_02_zhou_yutong_marketing.docx", "avatar": "zhou_yutong.png", "name": "周雨桐", "gender": "女", "age": 22, "city": "杭州", "target": "市场专员（科技产品方向）", "experience_years": "应届生", "phone": "139 5712 6840", "email": "yutong.zhou.cv@example.com", "salary": "7–10K/月", "availability": "一周内到岗",
        "summary": "市场营销专业应届毕业生，熟悉科技产品内容策划、用户调研、活动执行和基础数据分析。具备从选题、文案、视觉协同到复盘的完整项目经验，能够将复杂产品功能转化为易理解的传播内容，期望从市场专员岗位切入 B2B/SaaS 科技行业。",
        "education": [{"period": "2021.09–2025.06", "school": "浙江工商大学", "major": "市场营销", "degree": "本科", "detail": "专业排名前 15%；主修消费者行为学、市场调研、品牌管理、数字营销、统计学和商务沟通。"}],
        "projects": [
            {"name": "校园 AI 工具推广计划（项目负责人）", "period": "2024.09–2024.12", "bullets": ["围绕学生备考和论文场景完成 120 份问卷及 12 次访谈，提炼 3 类核心用户画像。", "策划“学习效率实验室”主题活动，联动社团和校园公众号，累计触达 8,600+ 人次，收集 310 条有效线索。", "根据渠道数据调整内容标题和投放时段，活动报名转化率从 6.2% 提升至 9.8%。"]},
            {"name": "科技品牌公众号内容运营", "period": "2024.03–2024.06", "bullets": ["独立完成 15 篇产品科普与客户案例文章，平均阅读量较账号基线提升约 32%。", "使用 Excel 维护选题、阅读、转发和线索表，形成月度复盘模板。"]}
        ],
        "skills": ["熟悉市场调研、竞品分析、内容策划、活动执行和基础线索运营。", "熟练使用 Excel、PowerPoint、Notion、Canva；能完成基础数据透视、图表和汇报材料。", "英语四级，能够阅读产品资料和海外市场案例；具备较好的文字表达和跨团队沟通能力。"],
        "certs": ["英语四级（CET-4）", "全国大学生市场调查与分析大赛校级二等奖"],
        "self": "对新技术和新产品保持好奇，擅长把抽象概念讲清楚、写出来、落到活动中。执行细致，重视时间节点和结果复盘，愿意从一线内容与用户反馈中建立市场判断。"
    },
    {
        "filename": "resume_03_zhao_xinyi_hr_admin.docx", "avatar": "zhao_xinyi.png", "name": "赵欣怡", "gender": "女", "age": 23, "city": "苏州", "target": "行政 / 人事专员", "experience_years": "应届生", "phone": "137 7604 2186", "email": "xinyi.zhao.cv@example.com", "salary": "6–9K/月", "availability": "毕业后可到岗",
        "summary": "工商管理专业应届毕业生，具备招聘协助、员工活动、会议组织、固定资产登记和行政流程支持经验。熟悉 Excel、Word、企业微信等办公工具，做事细致有条理，能够在多任务环境中保持信息准确和沟通顺畅，期望进入成长型科技公司从行政人事基础工作做起。",
        "education": [{"period": "2021.09–2025.06", "school": "苏州大学", "major": "工商管理", "degree": "本科", "detail": "主修组织行为学、人力资源管理、管理学原理、财务管理、商务礼仪和劳动关系。"}],
        "projects": [
            {"name": "校企创新实践周（行政协调）", "period": "2024.10–2024.11", "bullets": ["负责 20 余家企业嘉宾的邀约、信息收集、行程确认和现场接待，维护统一信息表。", "协调场地、物料、签到和志愿者排班，保障 3 天活动顺利进行，参与人数 600+。", "活动后整理反馈 180 份，输出问题清单和下一届执行建议。"]},
            {"name": "商学院学生助理", "period": "2023.09–2024.06", "bullets": ["协助完成每周会议通知、材料汇总、会议纪要和事项跟进，熟悉多方信息同步流程。", "负责办公用品领用登记和月度盘点，减少重复申领和临时缺货情况。"]}
        ],
        "skills": ["熟悉招聘邀约、面试安排、入离职材料整理、会议组织、员工活动和行政采购支持。", "熟练使用 Word、Excel、PowerPoint、企业微信；擅长台账管理、信息核对和流程跟进。", "了解劳动合同、考勤、员工档案等基础人事事项，具备良好的服务意识和保密意识。"],
        "certs": ["英语四级（CET-4）", "计算机二级（Office）"],
        "self": "细心、稳妥、责任感强，习惯将任务拆分为清单并提前确认关键节点。喜欢与人协作，面对临时变化能够快速补位，同时保持沟通礼貌和资料准确。"
    },
    {
        "filename": "resume_04_he_wanning_product_manager.docx", "avatar": "he_wanning.png", "name": "何婉宁", "gender": "女", "age": 31, "city": "上海", "target": "产品经理（企业服务 / SaaS）", "experience_years": "6年工作经验", "phone": "186 2158 4702", "email": "wanning.he.cv@example.com", "salary": "22–28K/月", "availability": "一个月内到岗",
        "summary": "6 年企业服务产品经验，服务过协同办公、客户工单和数据分析类 SaaS 产品。擅长从客户访谈、业务流程和数据反馈中识别问题，独立完成需求分析、原型设计、评审推进和上线复盘；有从 0 到 1 搭建模块、推动研发交付和协调售前/交付团队的经验。",
        "education": [{"period": "2013.09–2017.06", "school": "华东理工大学", "major": "信息管理与信息系统", "degree": "本科", "detail": "主修数据库原理、管理信息系统、项目管理、统计学和用户研究。"}],
        "experience": [
            {"period": "2021.08–至今", "company": "上海云栖信息技术有限公司", "role": "高级产品经理", "bullets": ["负责企业工单与服务运营产品线，服务 80+ 中大型客户，覆盖工单、知识库、SLA 和数据看板。", "通过客户访谈和工单数据分析重构 SLA 配置流程，配置时长下降 40%，新客户首月激活率提升 16%。", "协调研发、设计、实施和售前团队，建立双周迭代节奏，连续 6 个季度按计划交付核心版本。"]},
            {"period": "2019.07–2021.07", "company": "杭州数联科技有限公司", "role": "产品经理", "bullets": ["参与从 0 到 1 搭建客户数据平台，负责用户权限、标签体系、导入校验和数据概览模块。", "沉淀 PRD、原型、验收清单等产品文档模板，降低跨团队沟通成本。"]}
        ],
        "projects": [{"name": "客户服务智能分流项目", "period": "2023.04–2023.10", "bullets": ["联合算法和客服团队梳理 20 万条历史工单，设计意图标签和人工兜底机制，上线后人工分派量下降 28%。", "搭建运营看板，跟踪命中率、转人工率和 SLA 达成率，形成月度优化闭环。"]}],
        "skills": ["熟练使用 Axure、Figma、墨刀、SQL 和 Excel；能阅读接口文档并参与技术方案讨论。", "擅长用户访谈、流程梳理、需求优先级、版本规划、数据指标设计和上线复盘。", "熟悉 Scrum/敏捷协作，能够用中英文撰写产品文档和面向客户的解决方案材料。"],
        "certs": ["NPDP 产品经理认证", "英语六级（CET-6）"],
        "self": "业务理解和执行推进能力兼备，习惯用事实和数据推动决策。能够处理复杂利益相关方关系，也愿意深入一线理解客户真实使用场景。"
    },
    {
        "filename": "resume_05_tang_ziang_sales_manager.docx", "avatar": "tang_ziang.png", "name": "唐子昂", "gender": "男", "age": 29, "city": "深圳", "target": "企业销售经理（SaaS / 云服务）", "experience_years": "7年工作经验", "phone": "185 6671 0298", "email": "ziang.tang.cv@example.com", "salary": "18–25K/月 + 绩效", "availability": "两周内到岗",
        "summary": "7 年 B2B 科技行业销售经验，覆盖 SaaS、云服务和数据安全产品，具备从线索挖掘、需求调研、方案演示、商务谈判到回款管理的完整经验。擅长面向制造、零售和互联网客户推进多角色决策，连续 3 年完成年度指标 110%+。",
        "education": [{"period": "2014.09–2018.06", "school": "广东外语外贸大学", "major": "国际经济与贸易", "degree": "本科", "detail": "主修国际商务、市场营销、商务谈判、统计学和企业管理。"}],
        "experience": [
            {"period": "2022.03–至今", "company": "深圳星河云计算有限公司", "role": "大客户销售经理", "bullets": ["负责华南区域 30 家重点客户，围绕数据中台、云资源和安全合规产品制定年度经营计划。", "2024 年签约额 1,860 万元，完成率 118%；发展 6 家千万级客户，续约率保持在 96%。", "联合售前、交付和法务完成复杂项目投标与合同谈判，缩短平均成交周期约 20%。"]},
            {"period": "2018.07–2022.02", "company": "广州智联软件有限公司", "role": "行业销售顾问", "bullets": ["通过行业展会、渠道合作和客户转介绍开发新线索，建立制造业客户画像和跟进节奏。", "连续两年获得“季度新签冠军”，独立完成 50+ 家企业客户的签约和交付协同。"]}
        ],
        "projects": [{"name": "某制造集团数据治理平台项目", "period": "2024.02–2024.08", "bullets": ["主导从业务调研到商务签约的 6 个月销售周期，协调 4 个业务部门和 2 家交付伙伴。", "通过 ROI 测算和分阶段实施方案推动客户从试点扩展至 12 个工厂，项目合同额 420 万元。"]}],
        "skills": ["熟悉线索管理、MEDDICC 基本方法、方案型销售、招投标、商务谈判和合同回款。", "熟悉 Salesforce/纷享销客等 CRM；能制作销售漏斗、客户分层和经营分析报表。", "普通话、粤语流利，英语可进行日常商务沟通；具备较强的演示表达和跨部门协调能力。"],
        "certs": ["云计算基础认证", "英语六级（CET-6）"],
        "self": "结果导向，能够持续经营客户关系，也能在压力下保持节奏和专业度。重视长期信任，不以短期成交替代客户价值，擅长把复杂技术方案翻译成业务语言。"
    },
    {
        "filename": "resume_06_shen_ruohan_hr_admin_manager.docx", "avatar": "shen_ruohan.png", "name": "沈若涵", "gender": "女", "age": 34, "city": "北京", "target": "行政人事经理（科技公司）", "experience_years": "10年工作经验", "phone": "135 0108 7462", "email": "ruohan.shen.cv@example.com", "salary": "20–26K/月", "availability": "一个月内到岗",
        "summary": "10 年科技公司行政、人事与综合管理经验，曾支持 300 人规模研发与销售团队。熟悉招聘配置、绩效支持、员工关系、办公场地、供应商和预算管理，能够搭建基础制度并推动落地；擅长在快速变化的组织环境中提升运营秩序与员工体验。",
        "education": [{"period": "2010.09–2014.06", "school": "首都经济贸易大学", "major": "工商管理", "degree": "本科", "detail": "主修人力资源管理、组织行为学、劳动法、企业战略和财务管理。"}],
        "experience": [
            {"period": "2020.05–至今", "company": "北京启明智联科技有限公司", "role": "行政人事经理", "bullets": ["负责 280 人研发及商业团队的人事与行政运营，管理招聘、入离职、考勤、福利、办公和供应商工作。", "搭建岗位编制与招聘进度看板，年度关键岗位平均招聘周期缩短 18%，技术岗位 offer 接受率提升 12%。", "主导办公室搬迁与扩容项目，控制预算 230 万元内完成 4 个楼层落地，保证业务连续性。"]},
            {"period": "2016.07–2020.04", "company": "上海极客邦信息技术有限公司", "role": "行政人事专员 / 主管", "bullets": ["从 0 到 1 建立员工档案、考勤、固定资产和会议管理台账，支持团队从 80 人增长至 220 人。", "组织年度团建、技术分享和新员工融入活动，持续收集反馈并优化执行流程。"]}
        ],
        "projects": [{"name": "人事制度与员工体验升级", "period": "2022.01–2022.09", "bullets": ["梳理招聘、入职、转正、调岗和离职流程，输出 20+ 份标准化表单与 SOP，减少重复沟通。", "联合财务和 IT 完成员工福利与权限流程线上化，员工入职准备时间平均减少 1.5 个工作日。"]}],
        "skills": ["熟悉招聘、员工关系、绩效支持、薪酬福利协同、劳动合同和基础合规风险管理。", "熟练使用 Excel、企业微信、飞书、钉钉、Office；擅长制度文档、预算台账和项目推进。", "具有办公空间规划、供应商管理、行政采购、活动策划与跨部门沟通经验。"],
        "certs": ["人力资源管理师（三级）", "英语六级（CET-6）"],
        "self": "稳健、敏感、重视细节和组织体验，能够兼顾制度要求与业务实际。遇到突发事项时反应快、沟通清晰，善于把零散事务整理成可持续的流程。"
    },
    {
        "filename": "resume_07_zheng_kai_qa_engineer.docx", "avatar": "zheng_kai.png", "name": "郑凯", "gender": "男", "age": 32, "city": "上海", "target": "测试开发工程师 / QA 负责人", "experience_years": "8年工作经验", "phone": "136 2180 5937", "email": "kai.zheng.cv@example.com", "salary": "20–28K/月", "availability": "两周内到岗",
        "summary": "8 年互联网与企业软件质量工程经验，覆盖 Web、移动端和微服务系统。熟悉测试策略、自动化框架、接口测试、性能测试和质量度量，能够从研发流程和工程实践角度推动缺陷前移；带领 5 人测试小组持续提升回归效率和版本稳定性。",
        "education": [{"period": "2012.09–2016.06", "school": "南京航空航天大学", "major": "软件工程", "degree": "本科", "detail": "主修软件测试、操作系统、数据库、计算机网络、软件工程和算法设计。"}],
        "experience": [
            {"period": "2021.04–至今", "company": "上海墨云软件有限公司", "role": "高级测试开发工程师", "bullets": ["负责核心交易与开放平台质量保障，建立接口自动化、契约测试和线上监控机制，覆盖 300+ API。", "通过并行回归与测试数据工厂将版本回归时间从 2 天缩短至 6 小时，线上 P1/P2 缺陷下降 35%。", "带领 5 人小组制定测试计划、风险清单和发布门禁，参与架构评审和故障复盘。"]},
            {"period": "2016.07–2021.03", "company": "杭州微联科技有限公司", "role": "测试工程师", "bullets": ["负责移动端、后台管理和消息服务测试，覆盖功能、兼容性、接口、性能和安全基础检查。", "推动缺陷分类和根因分析，建立高频问题回归用例库，减少重复缺陷流入。"]}
        ],
        "projects": [{"name": "微服务接口自动化平台", "period": "2022.06–2023.02", "bullets": ["基于 Python + pytest + Allure 设计接口自动化框架，接入 CI 流水线并支持多环境配置。", "沉淀常用鉴权、数据构造和结果通知组件，提升测试用例复用率和执行可观测性。"]}],
        "skills": ["熟悉 Python、Java、pytest、JMeter、Postman、Selenium/Appium，了解 Playwright。", "熟悉 Linux、MySQL、Redis、Kafka 基础排查，能够阅读日志并定位跨服务问题。", "具备质量度量、测试计划、风险识别、研发协作和团队带教能力。"],
        "certs": ["ISTQB Foundation", "英语六级（CET-6）"],
        "self": "关注质量结果，也关注质量如何被工程化地持续产生。做事有条理、重证据，善于将模糊问题拆成可验证的假设，并与研发团队共同推进改进。"
    },
    {
        "filename": "resume_08_fang_kexin_uiux.docx", "avatar": "fang_kexin.png", "name": "方可欣", "gender": "女", "age": 28, "city": "杭州", "target": "UI/UX 设计师（数字产品）", "experience_years": "5年工作经验", "phone": "189 5710 3248", "email": "kexin.fang.cv@example.com", "salary": "16–22K/月", "availability": "一个月内到岗",
        "summary": "5 年数字产品设计经验，聚焦 SaaS、数据工具和移动端效率产品。擅长从用户研究、任务流程和信息架构出发，完成交互、视觉和设计规范落地；能够与产品、研发和运营协同推进设计方案，并通过可用性测试和数据反馈持续优化体验。",
        "education": [{"period": "2014.09–2018.06", "school": "中国美术学院", "major": "工业设计", "degree": "本科", "detail": "主修用户研究、交互设计、设计心理学、视觉传达和服务设计。"}],
        "experience": [
            {"period": "2021.06–至今", "company": "杭州简行数字科技有限公司", "role": "资深 UI/UX 设计师", "bullets": ["负责 B 端数据产品和移动端工作台设计，服务运营、销售和管理者等 6 类角色。", "主导信息架构和组件库升级，统一 120+ 个页面的交互与视觉规范，设计走查返工率下降约 30%。", "通过可用性测试和埋点反馈优化核心任务路径，关键功能完成率提升 14%。"]},
            {"period": "2018.07–2021.05", "company": "上海原点交互设计有限公司", "role": "交互设计师", "bullets": ["参与金融、零售和企业服务项目，完成用户访谈、竞品分析、流程图、原型和交互说明。", "与客户和研发共同完成多轮方案评审，积累复杂业务系统的设计交付经验。"]}
        ],
        "projects": [{"name": "企业数据工作台重构", "period": "2023.02–2023.09", "bullets": ["通过 15 次访谈和任务分析识别高频操作路径，重新组织导航、筛选和批量操作结构。", "建立 Figma 组件库和设计 token，支持研发快速复用，版本交付效率提升约 25%。"]}],
        "skills": ["熟练使用 Figma、Sketch、Adobe CC、Principle、Miro；能够制作高保真原型和交互说明。", "熟悉用户访谈、可用性测试、信息架构、设计系统、响应式布局和基础数据分析。", "具备较强的业务理解与表达能力，能与产品、研发、运营协同完成从方案到落地。"],
        "certs": ["Adobe Certified Professional（视觉设计）", "英语六级（CET-6）"],
        "self": "对细节敏感，但不把设计停留在视觉层面；习惯从用户目标、业务指标和实现成本三方面做取舍。沟通开放，能够接受反馈并快速形成下一版方案。"
    },
]


if __name__ == "__main__":
    for person in people:
        path = build_resume(person)
        print(path)
