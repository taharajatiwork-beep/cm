"""File storage. Local disk is the default. S3/MinIO is used when FILE_BACKEND=s3."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import get_settings

_ALLOWED = {
    "text/csv",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}


class UploadRejected(ValueError):
    pass


def _check(filename: str, content_type: str | None, data: bytes) -> str:
    settings = get_settings()
    if len(data) > settings.upload_max_bytes:
        raise UploadRejected(f"File exceeds {settings.upload_max_bytes} bytes")
    ct = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    allowed_ext = (filename or "").lower().endswith(
        (".csv", ".xlsx", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp")
    )
    if ct not in _ALLOWED and not allowed_ext:
        raise UploadRejected(f"File type not allowed: {ct}")
    return ct


def save_upload(filename: str, content_type: str | None, data: bytes) -> Path:
    ct = _check(filename, content_type, data)
    settings = get_settings()
    safe = Path(filename or "upload").name.replace("..", "_")
    key = f"{uuid.uuid4().hex}-{safe}"
    if settings.file_backend == "s3" and settings.s3_endpoint:
        _put_s3(key, data, ct)
        return Path(key)
    root = Path(settings.file_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / key
    dest.write_bytes(data)
    return dest


def read_upload(storage_path: str) -> bytes:
    settings = get_settings()
    if settings.file_backend == "s3" and settings.s3_endpoint:
        return _get_s3(storage_path)
    path = Path(storage_path)
    if not path.is_absolute():
        path = Path(settings.file_storage_dir) / path.name
    return path.read_bytes()


def _client():
    import boto3
    from botocore.client import Config

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region or "us-east-1",
        config=Config(signature_version="s3v4"),
    )


def _put_s3(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        client.create_bucket(Bucket=settings.s3_bucket)
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def _get_s3(key: str) -> bytes:
    settings = get_settings()
    obj = _client().get_object(Bucket=settings.s3_bucket, Key=Path(key).name)
    return obj["Body"].read()
