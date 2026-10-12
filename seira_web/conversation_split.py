"""seira_web.conversation_split — split one conversation into two, after the fact.

"Split here" on one of the Architect's messages moves that message and
everything after it into a NEW conversation. Nothing is deleted:

  - the new conversation gets re-numbered COPIES of the live records from
    that point on (original timestamps preserved);
  - the original keeps everything before it, and the moved part is
    superseded there with the same supersede_from marker that edit and
    regenerate already use (Art. 23: recorded, never removed) — so the
    transcript file still holds every word, and the live thread simply
    ends where he split it.

Split again on the new one to carve out a third topic. The new
conversation inherits the original's project and remembers where it came
from (split_from); the original lists what was split off (split_to).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

_KEEP = ("user", "assistant", "tool", "attachment")


def split_conversation(conv_id: str, target_id: int,
                       title: Optional[str] = None) -> Dict[str, Any]:
    from seira_web import conversations as convs

    live = convs._live_records(conv_id)
    ids = [r["id"] for r in live]
    if target_id not in ids:
        raise ValueError("That message isn't part of the live conversation.")
    target = next(r for r in live if r["id"] == target_id)
    if target["kind"] != "user":
        raise ValueError("Split at one of your own messages.")
    if not any(r["id"] < target_id and r["kind"] in ("user", "assistant") for r in live):
        raise ValueError("Nothing would stay in the original — split further down, "
                         "or just rename this conversation.")
    tail = [r for r in live if r["id"] >= target_id and r["kind"] in _KEEP]

    with convs._index_lock():
        index = convs._load_index()
        if conv_id not in index:
            raise ValueError(f"No conversation {conv_id!r}.")
        original = index[conv_id]
    first_text = (target.get("text") or "").strip().replace("\n", " ")
    default_title = (first_text[:60] or "Split conversation")
    new = convs.create_conversation((title or "").strip() or default_title)
    new_id = new["conv_id"]

    # 1) Write the copies first — if anything fails after this, the worst
    #    case is a duplicate, never a loss.
    with convs._conversation_lock(new_id):
        p = convs._conv_path(new_id)
        with p.open("w", encoding="utf-8") as f:
            for n, r in enumerate(tail, start=1):
                f.write(json.dumps({**r, "id": n}, ensure_ascii=False) + "\n")

    # 2) Hide the moved part in the original (recorded, recoverable).
    convs.supersede_from(conv_id, target_id)

    # 3) Bookkeeping on both index entries.
    with convs._index_lock():
        index = convs._load_index()
        now = convs._now()
        if new_id in index:
            index[new_id]["split_from"] = {"conv_id": conv_id, "at_record": target_id}
            if original.get("project"):
                index[new_id]["project"] = original["project"]
            if (title or "").strip():
                index[new_id]["title_user_set"] = True
            index[new_id]["listed_at"] = now
            index[new_id]["updated"] = now
        if conv_id in index:
            convs._freeze_listed(index[conv_id])
            index[conv_id].setdefault("split_to", []).append(new_id)
            index[conv_id]["updated"] = now   # content changed: re-summarize
        convs._save_index(index)
        return index[new_id]
