"""seira_web.references — documents in her Corpus: given, generated,
or kept from the web — saved once, tagged, recallable at will.

Corpus, not Psyche (Art. 13): reference documents are "wholly temporal"
material she can consult, not part of her eternal character. Saved
once, permanently, per tenant, and recallable at will through a
paging tool rather than forced whole into a single turn — a 100MB PDF
does not need to fit in one context window to be useful to her; it
needs to be there when she reaches for a specific part of it.

Three sources feed this same store, all through save_reference():
  - "upload"    — a document the Architect gives her (seira_web/app.py)
  - "generated" — a document she produces herself (seira_create_file)
  - "web"       — something she found and chose to keep (seira_reference_save)
One tagged, recallable Corpus regardless of where a document came
from — tags work exactly like image tags (seira_web/images.py),
deliberately: same design, same guarantees, same reason.

Layout: corpus/references/index.json (manifest) and
corpus/references/<ref_id>.txt (extracted text, plain).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from seira_core.paths import seira_home


def _refs_dir() -> Path:
    return seira_home() / "corpus" / "references"


def _index_path() -> Path:
    return _refs_dir() / "index.json"


def _text_path(ref_id: str) -> Path:
    if not ref_id.replace("-", "").isalnum():
        raise ValueError("Invalid reference id.")
    return _refs_dir() / f"{ref_id}.txt"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60] or "reference"


def _load_index() -> Dict[str, Dict[str, Any]]:
    if not _index_path().exists():
        return {}
    index = json.loads(_index_path().read_text(encoding="utf-8"))
    return _backfill_missing_tags(index)


def _backfill_missing_tags(index: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Records saved before tagging existed have no 'tag' key — same
    real migration gap images.py already hit and fixed once; mirrored
    here rather than re-derived, so both stores converge the same way."""
    changed = False
    used_tags = {r["tag"] for r in index.values() if "tag" in r}
    for ref_id, rec in index.items():
        if "tag" not in rec:
            base = _slugify(Path(rec.get("filename", "")).stem) if rec.get("filename") else ref_id
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
    _refs_dir().mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _index_path())


def save_reference(filename: str, text: str, source: str = "upload",
                   tag: str = "", project: str = "",
                   is_summary: bool = False) -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Cannot save an empty reference.")
    index = _load_index()
    ref_id = f"ref-{secrets.token_hex(6)}"
    _refs_dir().mkdir(parents=True, exist_ok=True)
    _text_path(ref_id).write_text(text, encoding="utf-8")
    default_tag = _slugify(Path(filename).stem) if filename else ref_id
    record = {
        "ref_id": ref_id, "filename": filename[:200], "source": source,
        "length": len(text), "created": _now(),
        "tag": _slugify(tag) if tag.strip() else default_tag,
        "project": project or None,
        # A session checkpoint, not an ordinary document — "where we
        # left off," meant to be the fast path back into a project
        # after time away. See projects.resume().
        "is_summary": is_summary,
    }
    # Same disambiguation discipline as images.py: a colliding tag gets
    # a short suffix rather than silently shadowing an older document
    # under a shared recall name.
    existing_tags = {r["tag"] for r in index.values()}
    if record["tag"] in existing_tags:
        record["tag"] = f"{record['tag']}-{ref_id[4:8]}"
    index[ref_id] = record
    _save_index(index)
    return record


def set_project(ref_id: str, proj_id: Optional[str]) -> Dict[str, Any]:
    """Associate (or clear, with proj_id=None) an existing reference
    with a project — the retroactive path: she notices two documents
    already share a theme and groups them after the fact, not only at
    the moment either was created."""
    index = _load_index()
    rec = index.get(ref_id)
    if rec is None:
        raise ValueError(f"No reference {ref_id!r}.")
    rec["project"] = proj_id
    index[ref_id] = rec
    _save_index(index)
    return rec


def set_tag(ref_id: str, tag: str) -> Dict[str, Any]:
    index = _load_index()
    rec = index.get(ref_id)
    if rec is None:
        raise ValueError(f"No reference {ref_id!r}.")
    if not tag.strip():
        raise ValueError("Tag must not be empty.")
    new_tag = _slugify(tag)
    if any(r["tag"] == new_tag and r["ref_id"] != ref_id for r in index.values()):
        raise ValueError(f"Tag {new_tag!r} is already used by another reference.")
    rec["tag"] = new_tag
    index[ref_id] = rec
    _save_index(index)
    return rec


def list_references() -> List[Dict[str, Any]]:
    return sorted(_load_index().values(), key=lambda r: r["created"], reverse=True)


def find_by_name(name: str) -> Optional[Dict[str, Any]]:
    name = name.strip().lower()
    for r in _load_index().values():
        if r["filename"].lower() == name:
            return r
    return None


def find_by_tag(tag: str) -> Optional[Dict[str, Any]]:
    tag = _slugify(tag)
    for r in _load_index().values():
        if r["tag"] == tag:
            return r
    return None


def resolve_ref(ref: str) -> Optional[Dict[str, Any]]:
    """Resolve a reference by ref_id, tag, or filename — tag checked
    before filename since it's the deliberate, memorable recall name;
    filename lookup stays for documents saved before tagging existed
    or recalled by their original name out of habit."""
    index = _load_index()
    if ref in index:
        return index[ref]
    rec = find_by_tag(ref)
    if rec is not None:
        return rec
    return find_by_name(ref)


def read_slice(ref_id_or_name: str, offset: int = 0, length: int = 8000) -> Dict[str, Any]:
    """Page through a reference's text. Never raises for a not-found
    reference — returns a clear 'found': False so a tool caller can act
    on it, same discipline as the rest of her tool surface."""
    rec = resolve_ref(ref_id_or_name)
    if rec is None:
        return {"found": False, "error": f"No reference matching {ref_id_or_name!r}."}
    text = _text_path(rec["ref_id"]).read_text(encoding="utf-8")
    offset = max(0, int(offset))
    length = max(1, min(int(length), 40_000))
    chunk = text[offset:offset + length]
    return {
        "found": True, "ref_id": rec["ref_id"], "filename": rec["filename"],
        "tag": rec["tag"], "source": rec.get("source", "upload"),
        "offset": offset, "length": len(chunk), "total_length": len(text),
        "text": chunk, "has_more": offset + len(chunk) < len(text),
    }

