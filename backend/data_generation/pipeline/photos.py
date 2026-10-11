"""Property Damage photo assignment (data sources doc §4 step 10).

Real/stock photos per severity tier would be the ideal source (data sources doc §2
decision #3), but sourcing and licensing real images isn't something this pipeline can
do unattended. Per the hackathon handbook's explicit allowance to mock/simulate data
where real sources are unavailable, this uploads a small placeholder image per severity
tier instead — clearly a stand-in, not a real photo, labeled as such in the object key
and never presented as sourced. Swap `_PLACEHOLDER_PNG` for a real asset per tier
whenever real/AI-generated photos are sourced, without touching any caller.
"""

import hashlib

import boto3

from app.config import settings

# A valid 1x1 transparent PNG — minimal placeholder bytes, not a real photo.
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bfabd4000000"
    "0049454e44ae426082"
)

SEVERITY_TIERS = ("minor", "moderate", "severe")


def _client():
    return boto3.client(
        "s3", endpoint_url=settings.aws_endpoint_url_s3,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def upload_placeholder_photo(case_id: str, severity: str) -> tuple[str, str]:
    """Uploads the placeholder image for one Property Damage case and returns
    (object_key, hash)."""
    object_key = f"evidence/{case_id}/placeholder-{severity}.png"
    _client().put_object(
        Bucket=settings.object_storage_bucket, Key=object_key, Body=_PLACEHOLDER_PNG,
        ContentType="image/png",
    )
    digest = hashlib.sha256(_PLACEHOLDER_PNG).hexdigest()
    return object_key, f"sha256:{digest}"
