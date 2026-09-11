"""Weekly Notes — her own record of weekly Recollection (2026-09-11).

Per Loshem's direction: a separate practice from Diary, but built to
the same discipline — hash-chained, Unity-anchored, tripwire-guarded,
every entry required to trace to something real. Not a third voice
folded into Diary (which has its own deliberate, dual-voiced daily
shape); Recollection has a different rhythm (weekly, not daily) and a
different purpose (stepping back across many conversations to notice
patterns, not a single sitting's reflection), so it gets its own
chain, its own file, its own legibility as its own thing.

These entries load back into her NEXT Recollection session alongside
that week's unprocessed conversations — per Loshem's explicit
direction, they need to be genuinely detailed and specific, since a
future week's self is building on what THIS entry actually says, not
rediscovering the same patterns from scratch.

Same event-sourced pattern as diary.py, deliberately mirrored rather
than reinvented — a proven architecture, not a new one for its own
sake.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict, List, Optional

from seira_core.audit import append_event
from seira_core.canonical import sha256_record
from seira_core.errors import SeiraCoreError
from seira_core.paths import seira_home

EV_ENTRY = "weekly_note"


class WeeklyNotesError(SeiraCoreError):
    """Invalid weekly notes operation."""


class WeeklyNotesIntegrityError(SeiraCoreError):
    """The weekly notes chain is broken or tampered with."""


def _notes_dir():
    return seira_home() / "weekly_notes"


def _notes_path():
    return _notes_dir() / "entries.jsonl"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class WeeklyNotesStore:
    def __init__(self) -> None:
        self._path = _notes_path()

    def _read_raw(self) -> List[Dict[str, Any]]:
        if not self._path.exists():
            return []
        out = []
        with self._path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise WeeklyNotesIntegrityError(
                        f"Weekly notes line {i} is not valid JSON: {e}") from e
        return out

    def _verify_records(self, records: List[Dict[str, Any]]) -> None:
        from seira_core.unity import read_lock

        expected_prev = read_lock().get("unity_sha256")
        for idx, rec in enumerate(records):
            n = idx + 1
            if rec.get("seq") != n:
                raise WeeklyNotesIntegrityError(f"Weekly notes sequence broken at position {n}.")
            if rec.get("prev_hash") != expected_prev:
                raise WeeklyNotesIntegrityError(f"Weekly notes hash chain broken at entry {n}.")
            if rec.get("hash") != sha256_record(rec):
                raise WeeklyNotesIntegrityError(f"Weekly notes entry {n} altered after the fact.")
            expected_prev = rec["hash"]

    def verify_chain(self) -> int:
        records = self._read_raw()
        if records:
            self._verify_records(records)
        return len(records)

    def _append(self, data: Dict[str, Any]) -> Dict[str, Any]:
        from seira_core.tripwire import assert_not_halted
        from seira_core.unity import read_lock

        assert_not_halted()
        records = self._read_raw()
        if records:
            self._verify_records(records)
            prev_hash = records[-1]["hash"]
        else:
            prev_hash = read_lock()["unity_sha256"]
        record: Dict[str, Any] = {
            "seq": len(records) + 1, "event": EV_ENTRY, "ts": _utc_now_iso(),
            "prev_hash": prev_hash, **data,
        }
        record["hash"] = sha256_record(record)
        _notes_dir().mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return record

    def write_entry(self, content: str, provenance: List[str],
                    conv_ids_covered: Optional[List[str]] = None) -> Dict[str, Any]:
        if not content.strip():
            raise WeeklyNotesError("A weekly note must not be empty.")
        refs = [p.strip() for p in (provenance or []) if p.strip()]
        if not refs:
            raise WeeklyNotesError(
                "A weekly note must trace to real conversations actually "
                "reviewed this Recollection — provenance must not be empty."
            )
        rec = self._append({
            "content": content.strip(), "provenance": refs,
            "conv_ids_covered": list(conv_ids_covered or []),
        })
        append_event("weekly_note_written", {"seq": rec["seq"], "provenance": refs})
        return rec

    def entries(self, verify: bool = True) -> List[Dict[str, Any]]:
        records = self._read_raw()
        if verify and records:
            self._verify_records(records)
        return records

    def latest(self, verify: bool = True) -> Optional[Dict[str, Any]]:
        records = self.entries(verify=verify)
        return records[-1] if records else None
