import io
import json
import struct
import zipfile
import warnings
import zlib
from pathlib import PurePosixPath

from PIL import Image

from .models import Course

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_ENTRIES = 100
CENTRAL_DIRECTORY_SIGNATURE = b"PK\x01\x02"
CENTRAL_DIRECTORY_HEADER_SIZE = 46
CENTRAL_DIRECTORY_DIGITAL_SIGNATURE = b"PK\x05\x05"


def _preflight_entry_count(data):
    # zipfile's EOCD reader handles ZIP64 and comments without building its eager ZipInfo list.
    endrec = zipfile._EndRecData(io.BytesIO(data))
    if endrec is None:
        return
    declared_count = endrec[zipfile._ECD_ENTRIES_TOTAL]
    if declared_count > MAX_ENTRIES:
        raise ValueError(f"Archive exceeds {MAX_ENTRIES} file entry limit")

    directory_end = endrec[zipfile._ECD_LOCATION]
    directory_start = directory_end - endrec[zipfile._ECD_SIZE]
    if directory_start < 0 or directory_end > len(data):
        raise ValueError("Invalid ZIP central directory")

    offset = directory_start
    counted = 0
    while offset < directory_end:
        signature = data[offset:offset + 4]
        if signature == CENTRAL_DIRECTORY_DIGITAL_SIGNATURE:
            if offset + 6 > directory_end:
                raise ValueError("Invalid ZIP central directory")
            signature_size = struct.unpack_from("<H", data, offset + 4)[0]
            if offset + 6 + signature_size != directory_end:
                raise ValueError("Invalid ZIP central directory")
            offset = directory_end
            break
        if signature != CENTRAL_DIRECTORY_SIGNATURE or offset + CENTRAL_DIRECTORY_HEADER_SIZE > directory_end:
            raise ValueError("Invalid ZIP central directory")

        name_size, extra_size, comment_size = struct.unpack_from("<HHH", data, offset + 28)
        offset += CENTRAL_DIRECTORY_HEADER_SIZE + name_size + extra_size + comment_size
        if offset > directory_end:
            raise ValueError("Invalid ZIP central directory")
        counted += 1
        if counted > MAX_ENTRIES:
            raise ValueError(f"Archive exceeds {MAX_ENTRIES} file entry limit")

    if counted != declared_count:
        raise ValueError("ZIP entry count does not match its central directory")


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
    _preflight_entry_count(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_ARCHIVE:
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
            try:
                files[name] = archive.read(entry)
            except zlib.error as exc:
                raise ValueError("The course ZIP contains corrupt compressed data") from exc
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
