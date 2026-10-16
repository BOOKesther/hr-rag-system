from zipfile import ZipFile
from pathlib import Path

for path in sorted(Path("data/templates").glob("template0[34].docx")):
    print("===", path.name)
    with ZipFile(path) as z:
        print([n for n in z.namelist() if n.startswith("word/media/")])
