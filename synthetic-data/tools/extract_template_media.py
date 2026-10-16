from zipfile import ZipFile
from pathlib import Path

out = Path(".qa/template_media")
out.mkdir(parents=True, exist_ok=True)
for path in sorted(Path("data/templates").glob("template0[34].docx")):
    with ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("word/media/") and name.lower().endswith((".png", ".jpg", ".jpeg")):
                target = out / f"{path.stem}_{Path(name).name}"
                target.write_bytes(z.read(name))
                print(target)
