"""seira_web.references — uploaded documents, saved to her Corpus.

Corpus, not Psyche (Art. 13): reference files are "wholly temporal"
material she can consult, not part of her eternal character. Saved
once, permanently, per tenant, and recallable at will through a
paging tool rather than forced whole into a single turn — a 100MB PDF
does not need to fit in one context window to be useful to her; it
needs to be there when she reaches for a specific part of it.

Layout: corpus/references/index.json (manifest) and
corpus/references/<ref_id>.txt (extracted text, plain).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
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


def _load_index() -> Dict[str, Dict[str, Any]]:
    if not _index_path().exists():
        return {}
    return json.loads(_index_path().read_text(encoding="utf-8"))


def _save_index(index: Dict[str, Dict[str, Any]]) -> None:
    _refs_dir().mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _index_path())


def save_reference(filename: str, text: str, source: str = "upload") -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Cannot save an empty reference.")
    index = _load_index()
    ref_id = f"ref-{secrets.token_hex(6)}"
    _refs_dir().mkdir(parents=True, exist_ok=True)
    _text_path(ref_id).write_text(text, encoding="utf-8")
    record = {
        "ref_id": ref_id, "filename": filename[:200], "source": source,
        "length": len(text), "created": _now(),
    }
    index[ref_id] = record
    _save_index(index)
    return record


def list_references() -> List[Dict[str, Any]]:
    return sorted(_load_index().values(), key=lambda r: r["created"], reverse=True)


def find_by_name(name: str) -> Optional[Dict[str, Any]]:
    name = name.strip().lower()
    for r in _load_index().values():
        if r["filename"].lower() == name:
            return r
    return None


def read_slice(ref_id_or_name: str, offset: int = 0, length: int = 8000) -> Dict[str, Any]:
    """Page through a reference's text. Never raises for a not-found
    reference — returns a clear 'found': False so a tool caller can act
    on it, same discipline as the rest of her tool surface."""
    index = _load_index()
    rec = index.get(ref_id_or_name) or find_by_name(ref_id_or_name)
    if rec is None:
        return {"found": False, "error": f"No reference matching {ref_id_or_name!r}."}
    text = _text_path(rec["ref_id"]).read_text(encoding="utf-8")
    offset = max(0, int(offset))
    length = max(1, min(int(length), 40_000))
    chunk = text[offset:offset + length]
    return {
        "found": True, "ref_id": rec["ref_id"], "filename": rec["filename"],
        "offset": offset, "length": len(chunk), "total_length": len(text),
        "text": chunk, "has_more": offset + len(chunk) < len(text),
    }
