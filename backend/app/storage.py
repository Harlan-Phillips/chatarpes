"""Tigris (S3-compatible) storage for data logs and user uploads.

Provisioned via `fly storage create`, which sets these env vars on the
app: BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
AWS_ENDPOINT_URL_S3, AWS_REGION.

If env vars are missing (e.g. local dev without Tigris configured), the
client property raises a 503-compatible RuntimeError so callers can
return a clean error instead of crashing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

DATALOGS_PREFIX = "datalogs/"
UPLOADS_PREFIX = "uploads/"


class StorageNotConfigured(RuntimeError):
    """Raised when Tigris env vars are missing."""


@dataclass(frozen=True)
class StoredObject:
    name: str           # logical filename (no prefix)
    size: int           # bytes
    last_modified: str  # ISO8601


def _bucket() -> str:
    name = os.getenv("BUCKET_NAME")
    if not name:
        raise StorageNotConfigured(
            "Tigris storage is not configured. Run `fly storage create` to provision."
        )
    return name


@lru_cache(maxsize=1)
def _client() -> BaseClient:
    endpoint = os.getenv("AWS_ENDPOINT_URL_S3")
    if not endpoint:
        raise StorageNotConfigured(
            "AWS_ENDPOINT_URL_S3 not set. Provision Tigris with `fly storage create`."
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.getenv("AWS_REGION", "auto"),
    )


def _full_key(prefix: str, name: str) -> str:
    # Disallow path traversal — names are flat under their prefix.
    if "/" in name or ".." in name:
        raise ValueError(f"Invalid object name: {name!r}")
    return prefix + name


def put(prefix: str, name: str, data: bytes, content_type: Optional[str] = None) -> StoredObject:
    """Upload bytes under prefix/name. Overwrites silently."""
    extra = {"ContentType": content_type} if content_type else {}
    _client().put_object(Bucket=_bucket(), Key=_full_key(prefix, name), Body=data, **extra)
    return StoredObject(
        name=name,
        size=len(data),
        last_modified=datetime.now(timezone.utc).isoformat(),
    )


def get(prefix: str, name: str) -> bytes:
    """Read full object bytes. Raises FileNotFoundError if absent."""
    try:
        resp = _client().get_object(Bucket=_bucket(), Key=_full_key(prefix, name))
        return resp["Body"].read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise FileNotFoundError(name) from e
        raise


def list_objects(prefix: str) -> list[StoredObject]:
    """List all objects under prefix. Empty list if storage unconfigured."""
    try:
        bucket = _bucket()
        client = _client()
    except StorageNotConfigured:
        return []

    out: list[StoredObject] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            key: str = obj["Key"]
            if not key.startswith(prefix):
                continue
            short_name = key[len(prefix):]
            if not short_name:
                continue  # the prefix "directory" placeholder, if any
            out.append(StoredObject(
                name=short_name,
                size=int(obj["Size"]),
                last_modified=obj["LastModified"].isoformat() if obj.get("LastModified") else "",
            ))
    out.sort(key=lambda o: o.name.lower())
    return out


def delete(prefix: str, name: str) -> None:
    """Remove an object. Idempotent — silently succeeds if absent."""
    _client().delete_object(Bucket=_bucket(), Key=_full_key(prefix, name))
