import io
import json
import struct
import zipfile
import warnings
from pathlib import PurePosixPath

from PIL import Image

from .models import Course

MAX_ARCHIVE = 20 * 1024 * 1024


def read_markdown(data):
    if len(data) > 100_000:
        raise ValueError("Source Markdown exceeds 100 KB")
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip() or "\x00" in text:
        raise ValueError("Source Markdown must contain readable UTF-8 text")
    return text


def validate_image(name, blob):
    ext = name.rsplit(".", 1)[-1].lower()
    valid = (ext == "png" and blob.startswith(b"\x89PNG\r\n\x1a\n")) or (ext in ("jpg", "jpeg") and blob.startswith(b"\xff\xd8\xff")) or (ext == "webp" and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP")
    if not valid or len(blob) > 4 * 1024 * 1024:
        raise ValueError("Asset is not a supported image or exceeds 4 MB: " + name)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(blob)) as image:
                if image.width*image.height>16_000_000:
                    raise ValueError("Image exceeds 16 megapixels")
                image.verify()
    except Exception as exc:
        raise ValueError("Image cannot be decoded safely: "+name) from exc


def unpack(data):
    if len(data) > MAX_ARCHIVE:
        raise ValueError("Course ZIP exceeds 20 MB")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 100 or sum(e.file_size for e in entries) > MAX_ARCHIVE:
            raise ValueError("Archive exceeds file or uncompressed size limit")
        files = {}
        for entry in entries:
            name = entry.filename
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unsafe ZIP path or symbolic link")
            if entry.is_dir():
                continue
            if name in files or str(p) != name:
                raise ValueError("Duplicate or non-canonical ZIP entry")
            if entry.flag_bits & 1:
                raise ValueError("Encrypted archives are unsupported")
            allowed = name in {"course.json", "source.md", "course.html", "handout.html", "changes.json", "changes.html"} or name.startswith("assets/")
            if not allowed:
                raise ValueError("Unsupported package entry: " + name)
            files[name] = archive.read(entry)
        if not {"course.json", "source.md"}.issubset(files):
            raise ValueError("The ZIP must contain course.json and source.md")
        course = Course.model_validate(json.loads(files["course.json"])).model_dump()
        source = read_markdown(files["source.md"])
        assets = {k:v for k,v in files.items() if k.startswith("assets/")}
        for name, blob in assets.items():
            validate_image(name, blob)
        for chapter in course["chapters"]:
            for block in chapter["blocks"]:
                if block.get("image") and block["image"] not in assets:
                    raise ValueError("Missing image: " + block["image"])
        return course, source, assets
