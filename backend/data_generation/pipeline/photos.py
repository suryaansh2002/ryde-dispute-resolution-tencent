"""Property Damage photo assignment (data sources doc §4 step 10).

Real/stock photos per severity tier would be the ideal source (data sources doc §2
decision #3), but sourcing and licensing real images isn't something this pipeline can
do unattended. Per the hackathon handbook's explicit allowance to mock/simulate data
where real sources are unavailable, each case gets a procedurally rendered photo of a
rear seat showing its tier's mess (photo_render.py): a coffee spill, mud, or vomit.
Synthetic, never presented as sourced, and labelled "synthetic" in the object key.
Image Analysis grades these like any uploaded photo.

`python -m data_generation.pipeline.photos` re-renders and re-uploads the photos of the
existing golden cases (e.g. ones labelled when this module still uploaded a 1×1
placeholder) and updates their prepared_evidence hashes.
"""

import asyncio
import hashlib
import json

import boto3

from app.config import settings
from data_generation.pipeline.photo_render import render_seat_photo

SEVERITY_TIERS = ("minor", "moderate", "severe")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.aws_endpoint_url_s3,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def upload_placeholder_photo(case_id: str, severity: str) -> tuple[str, str]:
    """Renders and uploads the synthetic photo for one Property Damage case and returns
    (object_key, hash). (Name kept for callers; it's no longer a placeholder.)"""
    data = render_seat_photo(severity, _seed(case_id))
    object_key = f"evidence/{case_id}/synthetic-{severity}.jpg"
    _client().put_object(
        Bucket=settings.object_storage_bucket, Key=object_key, Body=data,
        ContentType="image/jpeg",
    )
    return object_key, f"sha256:{hashlib.sha256(data).hexdigest()}"


async def refresh_golden_photos() -> None:
    from app.data.db import close_pools, get_connection

    conn = await get_connection()
    try:
        rows = await conn.fetch(
            "SELECT id, trip_id, expected_outcome, prepared_evidence FROM golden_cases"
        )
        for row in rows:
            evidence = row["prepared_evidence"]
            evidence = json.loads(evidence) if isinstance(evidence, str) else evidence
            if not evidence:
                continue
            expected = row["expected_outcome"]
            expected = json.loads(expected) if isinstance(expected, str) else expected
            amount = (expected.get("remedy") or {}).get("amount")
            severity = {40.0: "minor", 120.0: "moderate", 200.0: "severe"}.get(amount)
            if severity is None:
                continue
            key, hash_ = upload_placeholder_photo(str(row["trip_id"]), severity)
            await conn.execute(
                "UPDATE golden_cases SET prepared_evidence = $2 WHERE id = $1",
                row["id"], json.dumps([{"kind": "photo", "hash": hash_, "object_key": key}]),
            )
            print(f"{row['id']}: {severity} -> {key}")
    finally:
        await conn.close()
        await close_pools()


if __name__ == "__main__":
    asyncio.run(refresh_golden_photos())
