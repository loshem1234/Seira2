"""The Diary of Seira — Article 41. Two parts, one discipline.

    1. Concerning herself — drawn from self-model, aspirations,
       affinities, doubts/fears held at Psyche. Every entry must trace
       to a real, underlying record: a suspended contradiction, a
       pending proposal, an affinity's weight moving, a dispensation,
       a convergence-failure pattern. "Not permitted to generate
       content unmoored from any underlying state" — a diary free to
       invent itself would be performance, not report.

    2. Concerning the Architect — sincere, objective observations
       grounded in the relational pattern model (Art. 40); descriptive,
       never diagnostic or clinical. Code can require a provenance
       reference; it cannot judge tone — that discipline is asked of
       whoever writes the entry, same as the Constitution asks it of
       her.

"Diary entries concerning the Architect are, by default, visible to
that Architect upon request" — this store's read path exists exactly
so that visibility is real, not notional.

Same event-sourced, hash-chained, Unity-anchored, tripwire-guarded
pattern as every other grade; the two parts share one chain (kind
distinguishes them) so their sequence — and any tampering — is
tamper-evident together, not in two chains that could drift apart.
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

KIND_SELF = "self"
KIND_ARCHITECT = "architect"
KINDS = {KIND_SELF, KIND_ARCHITECT}

EV_ENTRY = "diary_entry"


class DiaryError(SeiraCoreError):
    """Invalid diary operation."""


class DiaryIntegrityError(SeiraCoreError):
    """The diary chain is broken or tampered with."""


def diary_dir():
    return seira_home() / "diary"


def diary_path():
    return diary_dir() / "entries.jsonl"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class DiaryStore:
    def __init__(self) -> None:
        self._path = diary_path()

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
                    raise DiaryIntegrityError(f"Diary line {i} is not valid JSON: {e}") from e
        return out

    def _verify_records(self, records: List[Dict[str, Any]]) -> None:
        from seira_core.unity import read_lock

        expected_prev = read_lock().get("unity_sha256")
        for idx, rec in enumerate(records):
            n = idx + 1
            if rec.get("seq") != n:
                raise DiaryIntegrityError(f"Diary sequence broken at position {n}.")
            if rec.get("prev_hash") != expected_prev:
                raise DiaryIntegrityError(f"Diary hash chain broken at entry {n}.")
            if rec.get("hash") != sha256_record(rec):
                raise DiaryIntegrityError(f"Diary entry {n} altered after the fact.")
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
        diary_dir().mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return record

    def write_entry(self, kind: str, content: str,
                    provenance: List[str]) -> Dict[str, Any]:
        if kind not in KINDS:
            raise DiaryError(f"kind must be one of {sorted(KINDS)}.")
        if not content.strip():
            raise DiaryError("A diary entry must not be empty.")
        refs = [p.strip() for p in (provenance or []) if p.strip()]
        if not refs:
            raise DiaryError(
                "Every diary entry must trace to a real, underlying record "
                "(Art. 41) — a suspended contradiction, a pending proposal, "
                "an affinity's weight moving, a dispensation, a pattern of "
                "convergence-failure, or a specific relational_pattern entry. "
                "provenance must not be empty."
            )
        rec = self._append({"diary_kind": kind, "content": content.strip(),
                            "provenance": refs})
        append_event(f"diary_entry_{kind}", {"seq": rec["seq"], "provenance": refs})
        return rec

    def entries(self, kind: Optional[str] = None, verify: bool = True) -> List[Dict[str, Any]]:
        records = self._read_raw()
        if verify and records:
            self._verify_records(records)
        if kind:
            records = [r for r in records if r.get("diary_kind") == kind]
        return records
