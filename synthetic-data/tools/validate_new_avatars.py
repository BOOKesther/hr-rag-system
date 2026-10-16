from pathlib import Path
from zipfile import ZipFile
from PIL import Image
from io import BytesIO
import hashlib

root = Path(__file__).resolve().parents[1]
existing = list((root / "data/avatars").glob("*.png"))
new = [root / "data/avatars/han_zimo_new.png", root / "data/avatars/lin_ruoxi_new.png"]
existing_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in existing if p not in new}
for p in new:
    print(p.name, "size", Image.open(p).size, "unique_from_old", hashlib.sha256(p.read_bytes()).hexdigest() not in existing_hashes)

for doc_name, expected_name in [
    ("resume_09_han_zimo_ios_template04.docx", "han_zimo_new.png"),
    ("resume_10_lin_ruoxi_customer_success_template03.docx", "lin_ruoxi_new.png"),
]:
    doc_path = root / "data" / doc_name
    with ZipFile(doc_path) as z:
        embedded = z.read("word/media/image1.png")
    image = Image.open(BytesIO(embedded))
    print(doc_name, "embedded_image1", image.size, "bytes", len(embedded), "source", expected_name)
