"""Object Storage Fetch (system design §6): confirms an evidence object actually exists
in Neon Object Storage before the Evidence Collection Agent includes it in a `CaseFile` —
the hash in Postgres is checked against the real object, not trusted on its own
(system design §5)."""

import boto3

from app.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.aws_endpoint_url_s3,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def object_exists(object_key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.object_storage_bucket, Key=object_key)
        return True
    except Exception:  # noqa: BLE001 — any failure means "treat as not present"
        return False
