from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image

root = Path(__file__).resolve().parents[1]


def avatar_bytes(source, width, height):
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


jobs = [
    ("data/resume_09_han_zimo_ios_template04.docx", "data/avatars/han_zimo_new.png", (144, 144)),
    ("data/resume_10_lin_ruoxi_customer_success_template03.docx", "data/avatars/lin_ruoxi_new.png", (339, 384)),
]

for doc_name, avatar_name, size in jobs:
    source = root / doc_name
    target = root / "tools" / (source.stem + "_avatar_fixed.docx")
    new_avatar = avatar_bytes(root / avatar_name, *size)
    with ZipFile(source, "r") as src:
        with ZipFile(target, "w", compression=ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "word/media/image1.png":
                    data = new_avatar
                dst.writestr(item, data)
    print(target)
