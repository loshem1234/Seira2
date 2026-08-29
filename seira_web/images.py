"""seira_web.images — vision: what she's shown, and how she remembers it.

Design mirrors references.py on purpose, for the same reason: an image
is Corpus content, saved once, permanently — but unlike a document,
replaying full image bytes into every future turn would silently
reintroduce the exact unbounded-context growth problem just discussed
for Psyche/Intellect. An image easily costs ~1000+ tokens; replaying
every past image on every future turn forever is not sustainable.

So: the CURRENT turn gets the real image content block. Past turns
that included an image are replayed as a text marker only
(conversations.py handles this). If she needs to look again, she asks
for it explicitly via seira_image_recall, which returns the real image
bytes as a tool_result image block — the same "paged/on-demand" shape
already used for large text references, applied to vision.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from seira_core.paths import seira_home

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # Anthropic's practical per-image ceiling
SUPPORTED_MEDIA_TYPES = {
    "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif",
}


def _images_dir() -> Path:
    return seira_home() / "corpus" / "images"


def _index_path() -> Path:
    return _images_dir() / "index.json"


def _load_index() -> Dict[str, Dict[str, Any]]:
    if not _index_path().exists():
        return {}
    index = json.loads(_index_path().read_text(encoding="utf-8"))
    return _backfill_missing_tags(index)


def _backfill_missing_tags(index: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Records saved before tagging existed have no 'tag' key at all —
    a real migration gap, not hypothetical: it crashed in production the
    first time a NEW save tried to check for collisions against an OLD,
    tag-less record. Backfilled here, once, and persisted, so every
    record converges to having a tag and every downstream access
    (existing_tags checks, find_by_tag, set_tag) can rely on it being
    present rather than needing its own defensive .get() everywhere."""
    changed = False
    used_tags = {r["tag"] for r in index.values() if "tag" in r}
    for img_id, rec in index.items():
        if "tag" not in rec:
            base = _slugify(Path(rec.get("filename", "")).stem) if rec.get("filename") else img_id
            candidate = base
            n = 2
            while candidate in used_tags:
                candidate = f"{base}-{n}"
                n += 1
            rec["tag"] = candidate
            used_tags.add(candidate)
            changed = True
    if changed:
        _save_index(index)
    return index


def _save_index(index: Dict[str, Dict[str, Any]]) -> None:
    _images_dir().mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _index_path())


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


import re


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60] or "image"


def save_image(filename: str, media_type: str, raw: bytes, tag: str = "") -> Dict[str, Any]:
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ValueError(
            f"Unsupported image type {media_type!r}; supported: "
            f"{sorted(SUPPORTED_MEDIA_TYPES)}."
        )
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image too large ({len(raw)//1024}KB; limit "
            f"{MAX_IMAGE_BYTES//1024}KB)."
        )
    img_id = f"img-{secrets.token_hex(6)}"
    ext = SUPPORTED_MEDIA_TYPES[media_type]
    disk_name = f"{img_id}.{ext}"
    _images_dir().mkdir(parents=True, exist_ok=True)
    (_images_dir() / disk_name).write_bytes(raw)
    default_tag = _slugify(Path(filename).stem) if filename else img_id
    record = {
        "img_id": img_id, "filename": filename[:200], "media_type": media_type,
        "disk_name": disk_name, "size": len(raw), "created": _now(),
        "tag": _slugify(tag) if tag.strip() else default_tag,
    }
    index = _load_index()
    # Tags are meant to be memorable and unique-ish; if the default/given
    # tag collides, disambiguate rather than silently shadowing an older
    # image under a shared recall name.
    existing_tags = {r["tag"] for r in index.values()}
    if record["tag"] in existing_tags:
        record["tag"] = f"{record['tag']}-{img_id[4:8]}"
    index[img_id] = record
    _save_index(index)
    return record


def set_tag(img_id: str, tag: str) -> Dict[str, Any]:
    index = _load_index()
    rec = index.get(img_id)
    if rec is None:
        raise ValueError(f"No image {img_id!r}.")
    if not tag.strip():
        raise ValueError("Tag must not be empty.")
    new_tag = _slugify(tag)
    if any(r["tag"] == new_tag and r["img_id"] != img_id for r in index.values()):
        raise ValueError(f"Tag {new_tag!r} is already used by another image.")
    rec["tag"] = new_tag
    index[img_id] = rec
    _save_index(index)
    return rec


def find_by_tag(tag: str) -> Optional[Dict[str, Any]]:
    tag = _slugify(tag)
    for r in _load_index().values():
        if r["tag"] == tag:
            return r
    return None


def resolve_ref(ref: str) -> Optional[Dict[str, Any]]:
    """Resolve an image by img_id or by tag — same ref-or-name pattern
    already used for document references."""
    index = _load_index()
    if ref in index:
        return index[ref]
    return find_by_tag(ref)


def get_image_block(ref: str) -> Optional[Dict[str, Any]]:
    """Return an Anthropic-shaped image content block, or None if missing.
    Accepts an img_id or a tag ('my-portrait-ref')."""
    rec = resolve_ref(ref)
    if rec is None:
        return None
    raw = (_images_dir() / rec["disk_name"]).read_bytes()
    return {
        "type": "image",
        "source": {
            "type": "base64", "media_type": rec["media_type"],
            "data": base64.b64encode(raw).decode("ascii"),
        },
    }


def list_images() -> List[Dict[str, Any]]:
    return sorted(_load_index().values(), key=lambda r: r["created"], reverse=True)


def get_image_bytes(ref: str) -> Optional[Dict[str, Any]]:
    """Raw bytes + media_type + filename for a resolved ref (id or tag) —
    what an external API's multipart upload needs, as opposed to
    get_image_block's Anthropic-shaped base64 content block."""
    rec = resolve_ref(ref)
    if rec is None:
        return None
    raw = (_images_dir() / rec["disk_name"]).read_bytes()
    return {"raw": raw, "media_type": rec["media_type"], "filename": rec["filename"],
           "tag": rec["tag"]}


def image_record(ref: str) -> Optional[Dict[str, Any]]:
    return resolve_ref(ref)
