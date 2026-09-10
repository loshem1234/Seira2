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

import contextlib
import datetime as _dt
import fcntl
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


@contextlib.contextmanager
def _conversation_lock(conv_id: str):
    """Exclusive lock spanning an entire read, or an entire
    read-modify-write, on one conversation's file.

    Real, live bug (2026-09-06), reported twice, worsening as a
    conversation grew longer: append() reads the whole file (to
    compute the next sequential id), THEN writes separately — a
    classic read-modify-write race with no protection at all before
    this fix. Reproduced directly: 30 concurrent unlocked appends
    produced 18 duplicate ids. Autonomous mode writes on its own
    background thread roughly once a minute while normal requests can
    write or read the SAME conversation at the same time — a
    concurrency scenario that genuinely did not exist before
    autonomous mode did. A longer conversation makes each read/write
    take longer, widening the collision window — exactly the "gets
    worse as the thread grows" pattern reported.

    A dedicated `.lock` file, not the `.jsonl` file itself, avoids any
    ambiguity around flock() semantics on a file already open in
    append mode. fcntl.flock() correctly serializes across both
    threads AND processes on Linux (locks are per open-file-
    description, not per-process), covering this app's actual
    single-process/multi-thread architecture and remaining correct if
    that ever changes.
    """
    conv_path = _conv_path(conv_id)
    conv_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = conv_path.with_suffix(".lock")
    with open(lock_path, "a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


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


def rename_conversation(conv_id: str, new_title: str) -> Dict[str, Any]:
    if not new_title.strip():
        raise ValueError("Title must not be empty.")
    index = _load_index()
    if conv_id not in index:
        raise ValueError(f"No conversation {conv_id!r}.")
    index[conv_id]["title"] = new_title.strip()[:80]
    # A title someone chose themselves is never overwritten by the
    # background auto-namer — see conversation_summarizer.py.
    index[conv_id]["title_user_set"] = True
    index[conv_id]["updated"] = _now()
    _save_index(index)
    return index[conv_id]


def auto_update_title_and_summary(conv_id: str, title: Optional[str],
                                  bullets: List[str]) -> Optional[Dict[str, Any]]:
    """Used only by conversation_summarizer.py's background pass.
    Updates the title ONLY if the person hasn't explicitly renamed
    this conversation themselves (title_user_set) — the auto-namer
    proposes a name, it never overwrites a real choice. Bullets always
    refresh regardless, since they're a summary of content, not
    something anyone would "rename". Returns None if the conversation
    no longer exists (deleted between listing and processing) rather
    than raising, since this runs unattended in the background."""
    index = _load_index()
    if conv_id not in index:
        return None
    if title and not index[conv_id].get("title_user_set"):
        index[conv_id]["title"] = title.strip()[:80]
    index[conv_id]["summary_bullets"] = bullets[:6]
    index[conv_id]["summary_updated_at"] = _now()
    # Deliberately NOT touching "updated" here — a background summary
    # refresh must never bump a conversation to the top of a
    # most-recently-updated sidebar; only real activity should do that.
    _save_index(index)
    return index[conv_id]


def archive_conversation(conv_id: str) -> Dict[str, Any]:
    """Removes a conversation from the visible list — never deletes its
    transcript. Same principle as message edit/regenerate (Art. 23):
    her Corpus doesn't lose real history because a UI trash icon was
    clicked; it stops being shown, which is what 'delete' actually
    means to the person using the sidebar."""
    index = _load_index()
    if conv_id not in index:
        raise ValueError(f"No conversation {conv_id!r}.")
    index[conv_id]["archived"] = True
    index[conv_id]["archived_at"] = _now()
    _save_index(index)
    return index[conv_id]


def list_conversations(include_archived: bool = False) -> List[Dict[str, Any]]:
    index = _load_index()
    convs = index.values()
    if not include_archived:
        convs = [c for c in convs if not c.get("archived")]
    return sorted(convs, key=lambda c: c["updated"], reverse=True)


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


def _records_unlocked(conv_id: str) -> List[Dict[str, Any]]:
    p = _conv_path(conv_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def records(conv_id: str) -> List[Dict[str, Any]]:
    with _conversation_lock(conv_id):
        return _records_unlocked(conv_id)


def append(conv_id: str, kind: str, **fields) -> Dict[str, Any]:
    # Locked for the FULL read-modify-write, not just the write — the
    # read (to compute the next sequential id) and the write must
    # happen as one atomic operation, or two concurrent callers can
    # both read the same "last id" and both write the next one,
    # producing duplicate ids (reproduced directly: 30 concurrent
    # unlocked appends -> 18 duplicates). Calls _records_unlocked, not
    # records(), specifically to avoid acquiring this same lock twice
    # from within one call — flock() is not reentrant across separate
    # open() calls, even from the same thread, and nesting it here
    # would deadlock.
    with _conversation_lock(conv_id):
        recs = _records_unlocked(conv_id)
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
    """The live thread as model messages (user/assistant text only).

    Past turns that carried an image (image_ref set) are replayed as a
    text marker, never the real image bytes again — an image is
    expensive to repeat into every future turn forever; her
    seira_image_recall tool exists precisely so she can ask for it back
    deliberately when she actually needs to look again."""
    msgs = []
    for r in _live_records(conv_id):
        if r["kind"] not in ("user", "assistant"):
            continue
        has_text = bool(r.get("text", "").strip())
        has_image = bool(r.get("image_ref"))
        if not (has_text or has_image):
            continue  # a genuinely empty record, not an image-only turn
        text = r.get("text", "")
        if r["kind"] == "user" and has_image:
            marker = (f"[Image previously shared: "
                     f"{r.get('image_name', r['image_ref'])} "
                     f"(ref: {r['image_ref']}) — recall it with "
                     f"seira_image_recall if you need to look again]")
            text = f"{marker}\n{text}".strip() if text.strip() else marker
        msgs.append({"role": r["kind"], "content": text})
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
