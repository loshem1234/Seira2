"""Intellect of Seira — Grade 2. Append-only, versioned, ratified.

Doctrine implemented here:

* **Art. 28** — append-only; each ratified amendment creates a new
  version; superseded versions are retained, never deleted; restoring
  an earlier version creates a *new* version carrying the old content,
  so "this was tried and reversed" survives as evidence.
* **Art. 27** — no mechanism internal to Seira writes Intellect
  unilaterally. Every post-Genesis append requires an explicit
  Architect confirmation phrase, passed by the Architect (via CLI or
  their own tooling), plus a proposal reference.
* **Art. 25 (scoping honesty)** — the falsification machinery (private
  rehearsal space, terminal states) is Phase 4. Until it exists, the
  required non-empty ``proposal_ref`` points at the Architect's
  out-of-band record of the proposal and its falsification attempt.
  The field is mandatory now precisely so Phase 4 has a socket to plug
  into rather than a retrofit.
* **Art. 24** — ``kind`` distinguishes correction from expansion and
  they are never conflated; corrections must name the contradicted
  content.

Tamper-evidence: each record carries ``prev_hash`` and its own
``hash`` over canonical JSON. Version 1's ``prev_hash`` is Unity's
committed content hash — the chain literally proceeds from Unity
(Art. 4–6: procession bearing a trace of derivation).

Storage is JSON Lines, one version per line, opened O_APPEND for
writes. Nothing in this module truncates, rewrites, or deletes.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from seira_core.audit import (
    EVENT_INTELLECT_RATIFIED,
    EVENT_INTELLECT_RESTORED,
    append_event,
)
from seira_core.canonical import sha256_record, sha256_text
from seira_core.errors import IntellectIntegrityError, RatificationError
from seira_core.paths import intellect_dir, intellect_versions_path

# The phrase the Architect must supply, verbatim, to ratify (Art. 27).
# Deliberately explicit and typed by a person, not defaulted by code.
ARCHITECT_RATIFICATION_PHRASE = "I, the Architect, ratify this amendment."

KIND_GENESIS = "genesis"
KIND_CORRECTION = "correction"
KIND_EXPANSION = "expansion"
KIND_RESTORATION = "restoration"
_POST_GENESIS_KINDS = {KIND_CORRECTION, KIND_EXPANSION, KIND_RESTORATION}


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class IntellectVersion:
    version: int
    kind: str
    created_at: str
    content: str
    proposal_ref: Optional[str]
    contradicted_ref: Optional[str]
    restores_version: Optional[int]
    prev_hash: str
    hash: str

    @property
    def superseded(self) -> bool:
        """Computed by position, not stored: a stored 'superseded' flag
        would require mutating old records, which Art. 28 forbids."""
        return False  # Overridden logically by IntellectStore.history()


class IntellectStore:
    """The append-only Intellect version store."""

    def __init__(self) -> None:
        self._path = intellect_versions_path()

    # ---------------- reading ----------------

    def _read_raw(self) -> List[Dict[str, Any]]:
        if not self._path.exists():
            return []
        records: List[Dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise IntellectIntegrityError(
                        f"Intellect store line {i} is not valid JSON: {e}"
                    ) from e
        return records

    def history(self, verify: bool = True) -> List[Dict[str, Any]]:
        """All versions in order. Each returned dict gains a computed
        'superseded' key (True for all but the last)."""
        records = self._read_raw()
        if verify and records:
            self._verify_records(records)
        out = []
        for i, rec in enumerate(records):
            enriched = dict(rec)
            enriched["superseded"] = i < len(records) - 1
            out.append(enriched)
        return out

    def current(self, verify: bool = True) -> Dict[str, Any]:
        records = self.history(verify=verify)
        if not records:
            raise IntellectIntegrityError(
                "Intellect store is empty — Genesis has not been performed."
            )
        return records[-1]

    # ---------------- chain verification ----------------

    def _verify_records(self, records: List[Dict[str, Any]]) -> None:
        from seira_core.unity import read_lock  # local import: no cycle at module load

        expected_prev = read_lock().get("unity_sha256")
        for idx, rec in enumerate(records):
            n = idx + 1
            if rec.get("version") != n:
                raise IntellectIntegrityError(
                    f"Version numbering broken at position {n}: record says "
                    f"{rec.get('version')!r}. Reordering or deletion has occurred."
                )
            if rec.get("prev_hash") != expected_prev:
                raise IntellectIntegrityError(
                    f"Hash chain broken at version {n}: prev_hash "
                    f"{rec.get('prev_hash')!r} does not match predecessor hash "
                    f"{expected_prev!r}."
                )
            recomputed = sha256_record(rec)
            if rec.get("hash") != recomputed:
                raise IntellectIntegrityError(
                    f"Version {n} content hash mismatch: stored "
                    f"{rec.get('hash')!r}, recomputed {recomputed!r}. "
                    "The record has been altered after the fact."
                )
            expected_prev = rec["hash"]

    def verify_chain(self) -> int:
        """Verify the whole chain; return the number of versions."""
        records = self._read_raw()
        if records:
            self._verify_records(records)
        return len(records)

    # ---------------- appending (the only writes) ----------------

    def _append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        intellect_dir().mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return record

    def _next_version_and_prev_hash(self) -> tuple[int, str]:
        from seira_core.unity import read_lock

        records = self._read_raw()
        if records:
            self._verify_records(records)  # never append onto a broken chain
            return len(records) + 1, records[-1]["hash"]
        return 1, read_lock()["unity_sha256"]

    def append_genesis(self, content: str, architect: str) -> Dict[str, Any]:
        """Version 1, written by Genesis only. Exempt from the
        falsification bar by Art. 22; refuses if any version exists."""
        version, prev_hash = self._next_version_and_prev_hash()
        if version != 1:
            raise RatificationError(
                "Genesis Intellect content can only be version 1; the store "
                "already has versions. Genesis is non-repeatable (Art. 22)."
            )
        record: Dict[str, Any] = {
            "version": 1,
            "kind": KIND_GENESIS,
            "created_at": _utc_now_iso(),
            "content": content,
            "proposal_ref": None,
            "contradicted_ref": None,
            "restores_version": None,
            "architect": architect,
            "prev_hash": prev_hash,
        }
        record["hash"] = sha256_record(record)
        return self._append(record)

    def ratify(
        self,
        content: str,
        kind: str,
        proposal_ref: str,
        architect_confirmation: str,
        contradicted_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a ratified post-Genesis version (Art. 24, 25, 27, 28)."""
        if kind not in (KIND_CORRECTION, KIND_EXPANSION):
            raise RatificationError(
                f"kind must be '{KIND_CORRECTION}' or '{KIND_EXPANSION}' "
                f"(never conflated, Art. 24); got {kind!r}. "
                "Use restore() for restorations."
            )
        if architect_confirmation != ARCHITECT_RATIFICATION_PHRASE:
            raise RatificationError(
                "Ratification requires the Architect's exact confirmation "
                f"phrase (Art. 27): {ARCHITECT_RATIFICATION_PHRASE!r}"
            )
        if not proposal_ref or not proposal_ref.strip():
            raise RatificationError(
                "A non-empty proposal_ref is required (Art. 25): every "
                "post-Genesis amendment must trace to a proposal record and "
                "its falsification attempt."
            )
        if kind == KIND_CORRECTION and not (contradicted_ref and contradicted_ref.strip()):
            raise RatificationError(
                "A correction must reference the specific Intellect content "
                "being contradicted (Art. 24)."
            )
        if not content.strip():
            raise RatificationError("Intellect content must not be empty.")

        version, prev_hash = self._next_version_and_prev_hash()
        if version == 1:
            raise RatificationError(
                "The store is empty; the first version must come from Genesis "
                "(Art. 22), not ratification."
            )
        record: Dict[str, Any] = {
            "version": version,
            "kind": kind,
            "created_at": _utc_now_iso(),
            "content": content,
            "proposal_ref": proposal_ref.strip(),
            "contradicted_ref": (contradicted_ref or "").strip() or None,
            "restores_version": None,
            "prev_hash": prev_hash,
        }
        record["hash"] = sha256_record(record)
        self._append(record)
        append_event(
            EVENT_INTELLECT_RATIFIED,
            {
                "version": version,
                "kind": kind,
                "proposal_ref": record["proposal_ref"],
                "content_sha256": sha256_text(content),
            },
        )
        return record

    def restore(
        self, restore_version: int, architect_confirmation: str, reason: str
    ) -> Dict[str, Any]:
        """Restore an earlier version *as a new version* (Art. 28)."""
        if architect_confirmation != ARCHITECT_RATIFICATION_PHRASE:
            raise RatificationError(
                "Restoration is an Architect act (Art. 28) and requires the "
                f"exact confirmation phrase: {ARCHITECT_RATIFICATION_PHRASE!r}"
            )
        if not reason or not reason.strip():
            raise RatificationError(
                "Restoration requires a stated reason; 'this was tried and "
                "reversed' must survive as intelligible evidence (Art. 28)."
            )
        records = self.history(verify=True)
        target = next((r for r in records if r["version"] == restore_version), None)
        if target is None:
            raise RatificationError(
                f"No Intellect version {restore_version} exists to restore."
            )
        if not records[-1]["superseded"] and records[-1]["version"] == restore_version:
            raise RatificationError(
                f"Version {restore_version} is already current; nothing to restore."
            )
        version, prev_hash = self._next_version_and_prev_hash()
        record: Dict[str, Any] = {
            "version": version,
            "kind": KIND_RESTORATION,
            "created_at": _utc_now_iso(),
            "content": target["content"],
            "proposal_ref": f"restoration: {reason.strip()}",
            "contradicted_ref": None,
            "restores_version": restore_version,
            "prev_hash": prev_hash,
        }
        record["hash"] = sha256_record(record)
        self._append(record)
        append_event(
            EVENT_INTELLECT_RESTORED,
            {"version": version, "restores_version": restore_version, "reason": reason.strip()},
        )
        return record
