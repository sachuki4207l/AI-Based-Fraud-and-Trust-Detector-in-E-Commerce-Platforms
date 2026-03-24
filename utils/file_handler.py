import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def validate_extension(filename: str):
    ext = filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Invalid file type")
    return ext


async def read_file_safe(file: UploadFile) -> bytes:
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large")

    return content


def generate_filename(ext: str) -> str:
    return f"{uuid.uuid4()}.{ext}"


def save_file(content: bytes, directory: Path, filename: str):
    directory.mkdir(parents=True, exist_ok=True)

    filepath = directory / filename

    with open(filepath, "wb") as f:
        f.write(content)

    return filepath