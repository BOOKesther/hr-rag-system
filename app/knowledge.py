import hashlib
import re
import unicodedata

SECTIONS = {
    "个人概况": ["个人概述", "个人简介", "核心优势", "PROFILE"],
    "教育经历": ["教育背景", "教育经历", "EDUCATION"],
    "工作经历": ["工作经历", "工作经验", "EXPERIENCE"],
    "项目经历": ["项目经历", "项目经验", "PROJECTS"],
    "技能": ["技能与证书", "掌握技能", "专业技能", "SKILLS"],
    "自我评价": ["自我评价", "ABOUT ME"],
    "荣誉证书": ["荣誉奖励", "证书", "AWARD"],
    "兴趣爱好": ["兴趣爱好"],
    "敏感信息": ["家属关系", "家庭成员", "紧急联系人", "紧急联络人"],
}
CITIES = ["上海", "北京", "杭州", "深圳", "广州", "苏州", "南京", "成都", "武汉", "西安", "天津", "重庆", "长沙", "郑州", "合肥", "厦门", "宁波", "青岛", "济南"]
EMAIL = r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
PHONE = r"(?<!\d)(?:\+?86[- ]*)?1[3-9]\d(?:[ -]?\d){8}(?!\d)"


def normalize(text):
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFKC", text)).strip()


def redact(text):
    text = re.sub(EMAIL, "[邮箱已隐藏]", text)
    return re.sub(PHONE, "[电话已隐藏]", text)


def heading(line):
    flat = re.sub(r"\s+", "", line).upper()
    for section, names in SECTIONS.items():
        for name in names:
            if flat.startswith(re.sub(r"\s+", "", name).upper()) and len(flat) < 36:
                return section
    return None


def clean_line(line):
    line = normalize(line)
    if re.search(r"紧急联系|家属|家庭成员|婚姻|民族|政治面貌|身份证|生日|出生日期", line):
        return ""
    line = re.sub(EMAIL, "", line)
    line = re.sub(PHONE, "", line)
    line = re.sub(r"(?:年龄[:：]?\s*)?\d{1,3}\s*岁", "", line)
    line = re.sub(r"(?:性别[:：]?\s*)?[男女](?=\s|[|｜·]|$)", "", line)
    line = re.sub(r"(?:电话|手机|邮箱|email|tel)\s*[:：]", "", line, flags=re.I)
    line = line.strip(" |·：:")
    return line if re.search(r"[\w\u4e00-\u9fff]{2}", line) else ""


def build_archive(parsed):
    blocks, current, seen = [], None, set()
    section = "个人概况"
    sensitive_tables = set()
    for table in parsed['tables']:
        text=' '.join(c['text'] for c in table['cells'])
        table['table_type'] = ('emergency_contact' if re.search(r'紧急联系|紧急联络',text) else
                               'family' if re.search(r'家属|家庭成员|父亲|母亲|配偶',text) else
                               'education' if re.search(r'学校|学历|专业',text) else
                               'employment' if re.search(r'公司|任职|工作单位',text) else 'key_value')
        if table['table_type'] in {'family','emergency_contact'}:
            sensitive_tables.add(table['table_id'])
    for e in parsed['elements']:
        if e['element_type'] in {"header", "footer"}:
            continue
        if e.get('table_id') in sensitive_tables:
            # Keep raw table evidence without contaminating candidate identity or knowledge.
            blocks.append(dict(block_id=f'block_{len(blocks)+1}',section='敏感信息',text=e['text'],
                               evidence_ids=[e['evidence_id']],element_ids=[e['element_id']],
                               page_no=e['page_no'],bbox=e['bbox'],relations=[],confidence=1.0))
            continue
        for line in e['text'].splitlines():
            line = normalize(line)
            if not line:
                continue
            h = heading(line)
            if h:
                section, current = h, None
                continue
            # Date-leading entries remain intact with their subsequent descriptions.
            new_entry = bool(re.match(r"(?:19|20)\d{2}[./年-]\d{1,2}.*(?:至今|今|20\d{2})", line))
            if current is None or new_entry:
                current = dict(block_id=f"block_{len(blocks)+1}", section=section, text="", evidence_ids=[],
                               element_ids=[], page_no=e['page_no'], bbox=e['bbox'], relations=[], confidence=.85)
                blocks.append(current)
            key = (section, re.sub(r"\s+", "", line))
            if key in seen:
                continue
            seen.add(key)
            current['text'] += ("\n" if current['text'] else "") + line
            if e['evidence_id'] not in current['evidence_ids']:
                current['evidence_ids'].append(e['evidence_id'])
                current['element_ids'].append(e['element_id'])
    blocks = [b for b in blocks if b['text']]
    for previous, following in zip(blocks, blocks[1:]):
        previous['relations'].append(dict(type="before_after", target=following['block_id']))
    public_blocks = [b for b in blocks if b['section'] != "敏感信息"]
    all_text = "\n".join(b['text'] for b in public_blocks)
    lines = all_text.splitlines()
    # Match evidence, never infer name from filename.
    name = next((re.sub(r"^姓名[:：]\s*", "", x).strip() for x in lines[:18]
                 if re.fullmatch(r"(?:姓名[:：]\s*)?[\u4e00-\u9fff]{2,4}", x)
                 and not heading(x) and x not in CITIES and x not in {"工程师", "程序员", "硕士", "本科"}), None)
    email = re.search(EMAIL, all_text)
    phone = re.search(PHONE, all_text)
    city_line = next((x for x in lines if re.search(r"现居|住址|居住|\d+\s*岁.*[|·]", x)), "")
    city = next((c for c in CITIES if c in city_line), None)
    years = re.search(r"(\d+)\s*年[^\n。]{0,24}(?:经验|工作)", all_text)
    roles = [x for x in lines[:8] if re.search(r"工程师|经理|专员|设计师|负责人|顾问|程序员", x) and len(x)<60]
    if not roles:
        roles = re.findall(r"岗位[:：]\s*([^\n|]+)", all_text)[:1]
    profile = dict(name=name, target_roles=roles[:1], current_city=city,
                   years_experience=int(years[1]) if years else (0 if "应届" in all_text else None),
                   phone=re.sub(r"\D", "", phone[0])[-11:] if phone else None,
                   email=email[0].lower() if email else None,
                   degree=next((d for d in ["博士", "硕士", "本科", "大专"] if d in all_text), None),
                   summary=next((b['text'] for b in blocks if b['section']=="个人概况" and len(b['text'])>80), ""))
    field_evidence = {}
    for field, value in profile.items():
        if value is not None and field not in {"summary", "target_roles"}:
            hits = [e['evidence_id'] for e in parsed['elements'] if str(value) in re.sub(r"[ -]", "", e['text'])]
            field_evidence[field] = dict(value=value, inferred=True, rule="format-and-section-v1", confidence=.8, evidence_ids=hits)
    sections = []
    for b in public_blocks:
        clean = "\n".join(filter(None, (clean_line(x) for x in b['text'].splitlines())))
        if clean and b['section'] != "兴趣爱好":
            sections.append(dict(section=b['section'], text=clean, evidence_ids=b['evidence_ids'], block_id=b['block_id']))
    text = "\n\n".join(s['text'] for s in sections)
    if not name or len(text) < 60:
        raise ValueError("档案质量门禁未通过：未能可靠识别姓名或有效履历过少，请检查原件")
    if re.search(EMAIL, text) or re.search(PHONE, text):
        raise ValueError("知识质量门禁未通过：残留联系方式")
    # Preserve fact ordering. A character bag could mistake changed dates or names
    # for duplicates; formatting-only whitespace/punctuation changes are ignored.
    source_text = ''.join(e['text'] for e in parsed['elements'] if e['element_type'] not in {'header','footer'})
    canonical = re.sub(r"[^\w\u4e00-\u9fff]", "", normalize(source_text).lower())
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    return dict(profile=profile, field_evidence=field_evidence, semantic_blocks=blocks, sections=sections,
                clean_text=text, content_fingerprint=fingerprint,
                education=[b for b in blocks if b['section']=="教育经历"],
                employment=[b for b in blocks if b['section']=="工作经历"],
                projects=[b for b in blocks if b['section']=="项目经历"],
                skills=[b for b in blocks if b['section']=="技能"],
                relationships=[b for b in blocks if b['section']=="敏感信息"])
