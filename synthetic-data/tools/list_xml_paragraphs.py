from zipfile import ZipFile
from lxml import etree
from pathlib import Path

for filename in ["template03.docx", "template04.docx"]:
    path = Path("data/templates") / filename
    print("===", filename)
    with ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    ps = root.xpath("//*[local-name()='p']")
    seen = set()
    for i, p in enumerate(ps):
        text = "".join(p.xpath(".//*[local-name()='t']/text()"))
        if text and text not in seen:
            print(i, repr(text))
            seen.add(text)
