"""Canonical serialization and hashing.

One canonical form, used everywhere, so a hash computed at Genesis and a
hash recomputed by the tripwire years later can never disagree for
formatting reasons. Text content is hashed as UTF-8 bytes of the exact
string; records are hashed over canonical JSON (sorted keys, no
whitespace, non-ASCII preserved).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(record: Dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_record(record: Dict[str, Any]) -> str:
    """Hash a record over its canonical JSON, excluding any existing
    'hash' field (the field being computed must not feed itself)."""
    body = {k: v for k, v in record.items() if k != "hash"}
    return sha256_text(canonical_json(body))
