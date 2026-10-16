"""Native parsers. Evidence is retained independently from searchable knowledge."""
import base64
import hashlib
import io
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

import pymupdf as fitz
from lxml import etree
from PIL import Image
from pptx import Presentation

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}
XML = etree.XMLParser(resolve_entities=False, no_network=True)


def validate_file(path: Path, max_mb: int):
    if path.stat().st_size > max_mb * 1024 * 1024:
        raise ValueError(f"文件超过 {max_mb} MB 限制")
    ext = path.suffix.lower()
    if ext not in {".pdf", ".docx", ".pptx"}:
        raise ValueError("仅支持 DOCX、PPTX、PDF")
    if ext == ".pdf":
        with path.open("rb") as f:
            if not f.read(5) == b"%PDF-":
                raise ValueError("PDF 文件签名不匹配")
        return
    try:
        with zipfile.ZipFile(path) as z:
            total = 0
            for entry in z.infolist():
                name = entry.filename.replace("\\", "/")
                if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or ":" in name:
                    raise ValueError("压缩包包含不安全路径")
                if "vbaproject" in name.lower():
                    raise ValueError("不接受含宏的文档")
                total += entry.file_size
                if total > 150 * 1024 * 1024 or len(z.infolist()) > 5000:
                    raise ValueError("压缩包展开大小或条目数超限")
            expected = "word/document.xml" if ext == ".docx" else "ppt/presentation.xml"
            if expected not in z.namelist() or "[Content_Types].xml" not in z.namelist():
                raise ValueError("扩展名与 Office 文件内容不匹配")
    except zipfile.BadZipFile as e:
        raise ValueError("Office 文件损坏或不是有效的 OOXML 文件") from e


def element(text, page, kind, bbox=None, **extra):
    return dict(text=re.sub(r"[ \t]+", " ", text).strip(), page_no=page,
                element_type=kind, bbox=bbox, strategy="native", confidence=1.0, **extra)


def docx_parse(path):
    elements, tables, images, warnings = [], [], [], []
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"), XML)
        body = root.find("w:body", NS)
        page = 1
        seen = set()

        def paragraph(p, kind="paragraph"):
            # Selecting leaf text nodes reads DrawingML/VML fallback text boxes once.
            for box in p.xpath(".//w:txbxContent", namespaces=NS):
                text = "\n".join("".join(p.xpath('.//w:t/text()', namespaces=NS)) for p in box.xpath('.//w:p', namespaces=NS))
                key = re.sub(r"\s+", "", text)
                if key and key not in seen:
                    seen.add(key)
                    anchor=box.xpath('ancestor::wp:anchor[1]',namespaces=NS)
                    bbox,shape_id=None,None
                    if anchor:
                        a=anchor[0]
                        x=a.find('wp:positionH/wp:posOffset',NS)
                        y=a.find('wp:positionV/wp:posOffset',NS)
                        extent=a.find('wp:extent',NS)
                        prop=a.find('wp:docPr',NS)
                        shape_id=prop.get('id') if prop is not None else None
                        if x is not None and y is not None and extent is not None:
                            left,top=int(x.text),int(y.text)
                            bbox=[left,top,left+int(extent.get('cx')),top+int(extent.get('cy'))]
                    elements.append(element(text, None, "text_box", bbox, shape_id=shape_id, coordinate_unit='EMU',xml_order=len(elements), page_hint=page))
            text = "".join(p.xpath(".//w:t[not(ancestor::w:txbxContent)]/text()", namespaces=NS))
            if text.strip():
                elements.append(element(text, None, kind, xml_order=len(elements), page_hint=page))

        for child in body:
            if child.tag == f"{{{NS['w']}}}tbl":
                cells = []
                rows = child.findall("w:tr", NS)
                for ri, row in enumerate(rows):
                    ci = 0
                    for cell in row.findall("w:tc", NS):
                        text = "\n".join("".join(p.xpath(".//w:t/text()", namespaces=NS)) for p in cell.findall("w:p", NS))
                        span = cell.find("w:tcPr/w:gridSpan", NS)
                        merge = cell.find("w:tcPr/w:vMerge", NS)
                        colspan = int(span.get(f"{{{NS['w']}}}val", 1)) if span is not None else 1
                        cells.append(dict(row_no=ri, col_no=ci, col_span=colspan, row_span=1, text=text,
                                          vertical_merge=merge.get(f"{{{NS['w']}}}val", "continue") if merge is not None else None))
                        ci += colspan
                table = dict(table_id=f"table_{len(tables)+1}", page_no=None, bbox=None, cells=cells,
                             row_count=len(rows), table_type="unknown")
                tables.append(table)
                for ri in range(len(rows)):
                    text = " | ".join(c['text'] for c in cells if c['row_no'] == ri)
                    elements.append(element(text, None, "table_row", table_id=table['table_id'], source_row=ri))
            else:
                for p in ([child] if child.tag == f"{{{NS['w']}}}p" else child.findall(".//w:p", NS)):
                    paragraph(p)
                    page += len(p.xpath('.//w:br[@w:type="page"]', namespaces=NS))
        for name in z.namelist():
            if re.match(r"word/(header|footer)\d+\.xml$", name):
                node = etree.fromstring(z.read(name), XML)
                elements.append(element(" ".join(node.xpath("//w:t/text()", namespaces=NS)), None,
                                        "header" if "header" in name else "footer"))
            if name.startswith("word/media/"):
                images.append(z.read(name))
    if elements and all(e['element_type']=='text_box' and e['bbox'] for e in elements):
        elements.sort(key=lambda e:(e['page_hint'],e['bbox'][1],e['bbox'][0]))
    warnings.append("DOCX 原生 XML 不提供可靠页码和绝对坐标；仅渲染成功后的快照具备真实分页。")
    return elements, tables, images, warnings, None


def pptx_parse(path):
    deck = Presentation(path)
    elements, tables, images = [], [], []

    def shapes(items, page):
        for shape in items:
            bbox = [int(shape.left), int(shape.top), int(shape.left + shape.width), int(shape.top + shape.height)]
            if shape.shape_type == 6:
                shapes(shape.shapes, page)
            elif shape.has_text_frame:
                elements.append(element(shape.text, page, "text_box", bbox, shape_id=shape.shape_id))
            elif shape.has_table:
                cells = []
                for ri, row in enumerate(shape.table.rows):
                    for ci, cell in enumerate(row.cells):
                        if not cell.is_spanned:
                            cells.append(dict(row_no=ri, col_no=ci, text=cell.text,
                                              row_span=cell.span_height, col_span=cell.span_width))
                tid = f"table_{len(tables)+1}"
                tables.append(dict(table_id=tid, page_no=page, bbox=bbox, cells=cells, table_type="unknown"))
                for ri in range(len(shape.table.rows)):
                    elements.append(element(" | ".join(c['text'] for c in cells if c['row_no']==ri), page, "table_row", bbox, table_id=tid))
            if shape.shape_type == 13:
                try:
                    images.append(shape.image.blob)
                except (ValueError, KeyError):
                    pass
    for number, slide in enumerate(deck.slides, 1):
        shapes(slide.shapes, number)
    elements.sort(key=lambda e: (e['page_no'], (e['bbox'] or [0,0])[1], (e['bbox'] or [0,0])[0]))
    return elements, tables, images, [], len(deck.slides)


def pdf_parse(path):
    elements, tables, images, warnings = [], [], [], []
    with fitz.open(path) as pdf:
        if pdf.needs_pass or len(pdf) > 99:
            raise ValueError("不支持加密 PDF 或超过 99 页的文件")
        for page in pdf:
            blocks = page.get_text("blocks", sort=True)
            for b in blocks:
                if b[6] == 0:
                    kind='footer' if re.search(r'模拟简历|个人资料为虚构示例|头像为\s*AI\s*生成',b[4]) else 'text'
                    elements.append(element(b[4], page.number + 1, kind, list(b[:4])))
            if len(page.get_text().strip()) < 20:
                raise ValueError(f"第 {page.number + 1} 页需要 OCR；当前 MVP 未启用 OCR，请上传有文本层的文件")
            for table in page.find_tables().tables:
                cells = [dict(row_no=r, col_no=c, text=value or "", row_span=1, col_span=1)
                         for r, row in enumerate(table.extract()) for c, value in enumerate(row)]
                tables.append(dict(table_id=f"table_{len(tables)+1}", page_no=page.number+1,
                                   bbox=list(table.bbox), cells=cells, table_type="unknown"))
            for im in page.get_images():
                try:
                    images.append(pdf.extract_image(im[0])["image"])
                except (ValueError, RuntimeError):
                    warnings.append("部分嵌入图片无法提取")
        count = len(pdf)
    return elements, tables, images, warnings, count


def render(path, directory, settings):
    pdf_path = path
    if path.suffix != ".pdf":
        exe = settings.soffice_path or shutil.which("soffice")
        if not exe:
            return [], ["未配置 LibreOffice，Office 原文件可下载，但真实页面快照尚未生成。"]
        profile = (directory / "lo_profile").resolve().as_uri()
        result = subprocess.run([exe, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
                                 "--outdir", str(directory), str(path)], capture_output=True, timeout=60)
        pdf_path = directory / (path.stem + ".pdf")
        if result.returncode or not pdf_path.exists():
            return [], ["LibreOffice 渲染失败；可配置后重试。"]
    snapshots = []
    with fitz.open(pdf_path) as pdf:
        if len(pdf) > 99:
            raise ValueError("渲染后页面超过 99 页限制")
        for i, page in enumerate(pdf, 1):
            file = directory / f"snap{i:02d}.png"
            pix = page.get_pixmap(dpi=settings.snapshot_dpi)
            pix.save(file)
            snapshots.append(dict(page_no=i, path=str(file), width=pix.width, height=pix.height, renderer="pymupdf"))
    return snapshots, []


def parse(path, directory, settings):
    parser = {".docx": docx_parse, ".pptx": pptx_parse, ".pdf": pdf_parse}[path.suffix]
    elements, tables, images, warnings, count = parser(path)
    elements = [e for e in elements if e['text']]
    for i, e in enumerate(elements):
        e['element_id'] = f"el_{i+1}"
        e['evidence_id'] = f"ev_{i+1}"
    assets = {"portrait": [], "embedded_images": [], "snapshots": []}
    hashes = set()
    for blob in images:
        digest = hashlib.sha256(blob).hexdigest()
        if digest in hashes:
            continue
        hashes.add(digest)
        try:
            with Image.open(io.BytesIO(blob)) as im:
                w, h = im.size
                if w*h > 20_000_000:
                    warnings.append("已跳过超大嵌入图片")
                    continue
                # Portrait candidate only; never claim face recognition.
                portrait = min(w,h) >= 128 and .6 <= w/h <= 1.5 and not assets['portrait']
                kind = "portrait" if portrait else "embedded_images"
                file = directory / ("portrait_01.png" if portrait else f"embedded_{len(assets[kind])+1:02d}.png")
                im.convert("RGB").save(file)
                item = dict(path=str(file), width=w, height=h, mime_type="image/png", sha256=hashlib.sha256(file.read_bytes()).hexdigest(), classification="portrait_candidate" if portrait else "embedded")
                if portrait:
                    b64 = directory / "portrait_01.base64.txt"
                    b64.write_text(base64.b64encode(file.read_bytes()).decode(), encoding="ascii")
                    item.update(base64_path=str(b64), encoding="base64")
                assets[kind].append(item)
        except (OSError, ValueError):
            warnings.append("跳过空白、损坏或不支持的嵌入媒体")
    return dict(elements=elements, tables=tables, assets=assets, warnings=warnings, page_count=count,
                parser=path.suffix[1:] + "-native", parser_version="1.0")
