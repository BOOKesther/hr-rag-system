from zipfile import ZipFile
from lxml import etree
from pathlib import Path

for path in [Path("data/resume_10_lin_ruoxi_customer_success_template03.docx")]:
    with ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(".xml"):
                data = z.read(name)
                if any(marker.encode("utf-8") in data for marker in ["某某某", "医护岗位", "上海赫尔森康复医院"]):
                    print("FOUND IN", name)
                    root = etree.fromstring(data)
                    for i, p in enumerate(root.xpath("//w:p", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})):
                        text = "".join(p.xpath(".//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}))
                        if any(marker in text for marker in ["某某某", "医护岗位", "上海赫尔森康复医院"]):
                            print(i, repr(text))
