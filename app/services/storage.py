import uuid
from pathlib import Path

import boto3
from botocore.client import Config

from app.config import settings


def _local_dir() -> Path:
    p = Path(settings.local_recordings_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket():
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        client.create_bucket(Bucket=settings.s3_bucket)


def upload_recording(data: bytes, content_type: str, family_id: uuid.UUID, submission_id: uuid.UUID) -> str:
    key = f"recordings/{family_id}/{submission_id}.webm"
    if settings.use_local_storage:
        path = _local_dir() / f"{family_id}_{submission_id}.webm"
        path.write_bytes(data)
        return key
    ensure_bucket()
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return key


def local_recording_path(family_id: uuid.UUID, submission_id: uuid.UUID) -> Path:
    return _local_dir() / f"{family_id}_{submission_id}.webm"


def read_recording(family_id: uuid.UUID, submission_id: uuid.UUID) -> bytes | None:
    """Baca audio rekaman (lokal atau S3). None bila tidak ada."""
    path = local_recording_path(family_id, submission_id)
    if path.is_file():
        return path.read_bytes()
    if settings.use_local_storage:
        return None
    try:
        obj = _client().get_object(Bucket=settings.s3_bucket, Key=f"recordings/{family_id}/{submission_id}.webm")
        return obj["Body"].read()
    except Exception:
        return None


def presigned_recording_url(key: str, family_id: uuid.UUID | None = None, submission_id: uuid.UUID | None = None) -> str:
    if settings.use_local_storage and family_id and submission_id:
        return f"{settings.api_public_base.rstrip('/')}/setor/media/{submission_id}"
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=3600,
    )


def delete_recording(family_id: uuid.UUID, submission_id: uuid.UUID) -> None:
    """Hapus berkas audio dari penyimpanan (lokal atau S3). Tidak error bila sudah tidak ada."""
    path = local_recording_path(family_id, submission_id)
    path.unlink(missing_ok=True)
    if not settings.use_local_storage:
        try:
            _client().delete_object(Bucket=settings.s3_bucket, Key=f"recordings/{family_id}/{submission_id}.webm")
        except Exception:
            pass
