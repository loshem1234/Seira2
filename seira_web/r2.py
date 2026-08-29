"""seira_web.r2 — off-box backup shipping, to a Cloudflare R2 bucket.

This is what closes the honest gap named in backup.py's own docstring:
local backups protect against drift/defect via rollback; they do NOT
protect against losing the volume itself. R2 is where the "still
there if the volume is gone" guarantee actually lives.

R2 is S3-compatible, so this uses boto3 (the standard, well-tested way
to talk to it) rather than hand-rolling AWS request signing — that's
real risk to take on for no real benefit.

Design, matching the rest of this project's external-service pattern
(AnthropicClient, OpenAIImageClient): a small client class doing the
real work, injectable everywhere it's used, so the test suite never
makes a real network call or touches a real bucket.

What ships: every local backup archive, uploaded once, under
`{prefix}/{kind}/{filename}`. Retention in the bucket is enforced by
this code too (mirroring local retention) rather than left as "please
also remember to configure a lifecycle rule in the Cloudflare
dashboard" — config-as-code and config-as-tests is the discipline this
whole project runs on; a manual dashboard step the code can't verify
doesn't fit that.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


class R2Error(Exception):
    pass


class R2Client(Protocol):
    def upload(self, local_path: Path, key: str) -> None: ...
    def list_keys(self, prefix: str) -> List[Dict[str, Any]]: ...
    def delete(self, key: str) -> None: ...


def r2_configured() -> bool:
    """True if enough env vars are present to attempt shipping at all.
    Backups work perfectly well locally with none of this set — R2
    shipping is additive, never required."""
    return bool(
        os.environ.get("SEIRA_R2_ACCOUNT_ID")
        and os.environ.get("SEIRA_R2_ACCESS_KEY_ID")
        and os.environ.get("SEIRA_R2_SECRET_ACCESS_KEY")
        and os.environ.get("SEIRA_R2_BUCKET")
    )


class BotoR2Client:
    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket: Optional[str] = None,
    ):
        account_id = account_id or os.environ.get("SEIRA_R2_ACCOUNT_ID", "")
        access_key_id = access_key_id or os.environ.get("SEIRA_R2_ACCESS_KEY_ID", "")
        secret_access_key = secret_access_key or os.environ.get("SEIRA_R2_SECRET_ACCESS_KEY", "")
        self.bucket = bucket or os.environ.get("SEIRA_R2_BUCKET", "")
        if not all([account_id, access_key_id, secret_access_key, self.bucket]):
            raise R2Error(
                "R2 is not fully configured: SEIRA_R2_ACCOUNT_ID, "
                "SEIRA_R2_ACCESS_KEY_ID, SEIRA_R2_SECRET_ACCESS_KEY, and "
                "SEIRA_R2_BUCKET must all be set."
            )
        import boto3
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    def upload(self, local_path: Path, key: str) -> None:
        try:
            self._client.upload_file(str(local_path), self.bucket, key)
        except Exception as e:
            raise R2Error(f"Upload of {local_path.name} to R2 failed: {e}") from e

    def list_keys(self, prefix: str) -> List[Dict[str, Any]]:
        try:
            out: List[Dict[str, Any]] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    out.append({"key": obj["Key"], "size": obj["Size"],
                               "last_modified": obj["LastModified"].isoformat()})
            return out
        except Exception as e:
            raise R2Error(f"Listing R2 objects under {prefix!r} failed: {e}") from e

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            raise R2Error(f"Deleting R2 object {key!r} failed: {e}") from e


def _prefix() -> str:
    return os.environ.get("SEIRA_R2_PREFIX", "seira-backups").strip("/")


def ship(local_path: Path, kind: str, client: Optional[R2Client] = None) -> Dict[str, Any]:
    """Upload one backup archive to R2 and enforce remote retention.
    Never raises past the caller if client is None and R2 simply isn't
    configured — callers (the background loop) treat that as 'ship
    step skipped', not an error, since R2 is optional."""
    active = client or BotoR2Client()
    key = f"{_prefix()}/{kind}/{local_path.name}"
    active.upload(local_path, key)
    removed = _prune_remote(kind, active)
    return {"uploaded_key": key, "remote_pruned": removed}


def _prune_remote(kind: str, client: R2Client) -> List[str]:
    from seira_web.backup import DAILY_RETENTION, MONTHLY_RETENTION
    retention = DAILY_RETENTION if kind == "daily" else MONTHLY_RETENTION
    prefix = f"{_prefix()}/{kind}/"
    objects = client.list_keys(prefix)
    # Filenames encode a sortable microsecond timestamp (see backup.py);
    # lexicographic sort on the key is therefore chronological, same
    # trick used for local retention and for the same reason — it does
    # not depend on any timestamp metadata the remote store might
    # round or omit.
    objects.sort(key=lambda o: o["key"], reverse=True)
    removed = []
    for old in objects[retention:]:
        client.delete(old["key"])
        removed.append(old["key"])
    return removed


def list_remote(kind: str, client: Optional[R2Client] = None) -> List[Dict[str, Any]]:
    active = client or BotoR2Client()
    return active.list_keys(f"{_prefix()}/{kind}/")
