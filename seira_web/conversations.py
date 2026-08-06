"""seira_web.conversations — the Corpus, organized as conversations.

Per-tenant layout:
    corpus/conversations/index.json      — id, title, created, updated
    corpus/conversations/<conv_id>.jsonl — the records, in order

Corpus doctrine (Art. 13, 23) shapes two choices here:

* Plain append-only JSONL, deliberately un-chained — the Corpus is the
  one grade whose amendment is continuous and unreviewed by design.
* **Nothing is ever deleted.** "Edit" and "regenerate" are recorded as
  supersession events: a `supersede_from` record marks an id and
  everything after it as no longer part of the live thread, and the new
  content is appended after. The model's view (`model_history`) skips
  superseded records; the full record — including every abandoned
  branch — remains readable forever. What was said and unsaid is part
  of what happened.

Records: {"id": int, "ts": iso, "kind": "user"|"assistant"|"tool"|
"attachment"|"supersede_from", ...}
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from seira_core.paths import seira_home


def _conv_dir() -> Path:
    return seira_home() / "corpus" / "conversations"


def _index_path() -> Path:
    return _conv_dir() / "index.json"


def _conv_path(conv_id: str) -> Path:
    if not conv_id.replace("-", "").isalnum():
        raise ValueError("Invalid conversation id.")
    return _conv_dir() / f"{conv_id}.jsonl"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _load_index() -> Dict[str, Dict[str, Any]]:
    if not _index_path().exists():
        return {}
    return json.loads(_index_path().read_text(encoding="utf-8"))


def _save_index(index: Dict[str, Dict[str, Any]]) -> None:
    _conv_dir().mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _index_path())


def list_conversations() -> List[Dict[str, Any]]:
    index = _load_index()
    return sorted(index.values(), key=lambda c: c["updated"], reverse=True)


def create_conversation(title: str = "New conversation") -> Dict[str, Any]:
    index = _load_index()
    conv_id = f"c-{secrets.token_hex(6)}"
    index[conv_id] = {
        "conv_id": conv_id,
        "title": (title or "New conversation")[:80],
        "created": _now(),
        "updated": _now(),
    }
    _save_index(index)
    _conv_path(conv_id).touch()
    return index[conv_id]


def touch(conv_id: str, maybe_title_from: Optional[str] = None) -> None:
    index = _load_index()
    if conv_id in index:
        index[conv_id]["updated"] = _now()
        if maybe_title_from and index[conv_id]["title"] == "New conversation":
            index[conv_id]["title"] = maybe_title_from.strip()[:80]
        _save_index(index)


def records(conv_id: str) -> List[Dict[str, Any]]:
    p = _conv_path(conv_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def append(conv_id: str, kind: str, **fields) -> Dict[str, Any]:
    recs = records(conv_id)
    rec = {"id": (recs[-1]["id"] + 1) if recs else 1,
           "ts": _now(), "kind": kind, **fields}
    p = _conv_path(conv_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def supersede_from(conv_id: str, target_id: int) -> Dict[str, Any]:
    """Mark target_id and everything after it as superseded (recorded,
    never removed). Used by edit and regenerate."""
    if not any(r["id"] == target_id for r in records(conv_id)):
        raise ValueError(f"No record {target_id} in {conv_id}.")
    return append(conv_id, "supersede_from", target=target_id)


def _live_records(conv_id: str) -> List[Dict[str, Any]]:
    recs = records(conv_id)
    cut = None
    for r in recs:
        if r["kind"] == "supersede_from":
            cut = r["target"]
    # Apply every supersession in order: a record is live iff no later
    # supersede_from targets an id <= its id at the time it applied.
    live: List[Dict[str, Any]] = []
    for r in recs:
        if r["kind"] == "supersede_from":
            live = [x for x in live if x["id"] < r["target"]]
            continue
        live.append(r)
    return live


def model_history(conv_id: str, limit_turns: int = 30) -> List[Dict[str, str]]:
    """The live thread as model messages (user/assistant text only)."""
    msgs = []
    for r in _live_records(conv_id):
        if r["kind"] in ("user", "assistant") and r.get("text", "").strip():
            msgs.append({"role": r["kind"], "content": r["text"]})
    return msgs[-limit_turns * 2:]


def display_records(conv_id: str) -> List[Dict[str, Any]]:
    """Live records for the UI: user/assistant text plus tool notes."""
    return [r for r in _live_records(conv_id)
            if r["kind"] in ("user", "assistant", "tool", "attachment")]


def last_live_user(conv_id: str) -> Optional[Dict[str, Any]]:
    for r in reversed(_live_records(conv_id)):
        if r["kind"] == "user":
            return r
    return None


def last_live_assistant(conv_id: str) -> Optional[Dict[str, Any]]:
    for r in reversed(_live_records(conv_id)):
        if r["kind"] == "assistant":
            return r
    return None
