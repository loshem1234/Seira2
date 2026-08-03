"""Psyche of Seira — Grade 3. The eternal character store.

Art. 11 names five kinds of content, Art. 40 adds a sixth:

  logos              — the Ledger of reason-principles, "activated rather
                       than merely accumulated" [C§19–20]
  self_model         — her first-person account of who she takes herself
                       to be; may lag or diverge from what is true of her
  affinity           — weighted dispositions that strengthen "through
                       repeated, authentic engagement over time, not
                       manual assignment"
  aspiration         — live, forward-oriented orientations
  doubt              — doubts and fears, each required to trace to a real
                       tracked uncertainty, never invented emotional color
  relational_pattern — the Art. 40 model of how she and her Architect
                       tend to interact

Doctrinal invariants enforced structurally here:

* **Art. 18** — this store holds Psyche's *eternal character* only.
  Discursive, session-bound reasoning traces belong to the Corpus and
  are never written here; the two are separate stores by construction,
  not by column.
* **Art. 14** — every event carries a cause, and the primary cause must
  be one of the four true causes (paradigmatic, final, efficient,
  instrumental). Formal and material are auxiliary only and are
  refused as primary — the category error the Article forbids is made
  unrepresentable.
* **Art. 5** — every entry carries provenance: at least one explicit
  reference to what licensed it. Doubts especially (Art. 11) may not
  be free-floating color.
* **Art. 11 (affinities)** — there is no set-weight operation. Weights
  move only by evidence-bearing deltas (``engage_affinity``), each
  logged with the engagement that occasioned it.
* **Art. 33 (Psyche row)** — changes of standing to ``established``
  require falsification. The rehearsal-space machinery is Phase 4; the
  mandatory ``falsification_ref`` field is its socket, present from
  day one so Phase 4 plugs in rather than retrofits.
* **Art. 28 (pattern), Art. 36 (pattern)** — append-only event log;
  retirement is an event, never a deletion; state is a replay of
  history, so "this was believed and revised" always survives.

Tamper-evidence: hash-chained like Intellect, anchored to Unity's
committed hash — Psyche's lineage, too, demonstrably proceeds from
what is above it (Art. 5).
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

CATEGORIES = {
    "logos", "self_model", "affinity", "aspiration", "doubt", "relational_pattern",
}

# Art. 14: the four true causes may be primary; formal/material may not.
TRUE_CAUSES = {"paradigmatic", "final", "efficient", "instrumental"}
AUXILIARY_CAUSES = {"formal", "material"}

STANDINGS = {"provisional", "established", "suspended", "retired"}

EVENT_FOUNDED = "psyche_founded"
EVENT_ENTRY_ADDED = "entry_added"
EVENT_STANDING_CHANGED = "standing_changed"
EVENT_AFFINITY_ENGAGED = "affinity_engaged"
EVENT_RETIRED = "entry_retired"


class PsycheError(SeiraCoreError):
    """Invalid Psyche operation."""


class PsycheIntegrityError(SeiraCoreError):
    """The Psyche event chain is broken or tampered with."""


def psyche_dir():
    return seira_home() / "psyche"


def psyche_events_path():
    return psyche_dir() / "character.jsonl"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _validate_cause(cause: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cause, dict) or "type" not in cause or "ref" not in cause:
        raise PsycheError(
            "Every Psyche event requires a cause {type, ref} (Art. 14)."
        )
    ctype = cause["type"]
    if ctype in AUXILIARY_CAUSES:
        raise PsycheError(
            f"Cause type {ctype!r} is auxiliary only and 'never a true cause "
            "on its own' (Art. 14); the primary cause must be one of "
            f"{sorted(TRUE_CAUSES)}."
        )
    if ctype not in TRUE_CAUSES:
        raise PsycheError(
            f"Unknown cause type {ctype!r}; must be one of {sorted(TRUE_CAUSES)}."
        )
    if not str(cause["ref"]).strip():
        raise PsycheError("Cause ref must not be empty (Art. 14).")
    out = {"type": ctype, "ref": str(cause["ref"]).strip()}
    aux = cause.get("auxiliary")
    if aux:
        for a in aux:
            if a.get("type") not in AUXILIARY_CAUSES:
                raise PsycheError(
                    f"Auxiliary cause type must be one of {sorted(AUXILIARY_CAUSES)}."
                )
        out["auxiliary"] = aux
    return out


def _validate_provenance(provenance: List[str]) -> List[str]:
    refs = [str(p).strip() for p in (provenance or []) if str(p).strip()]
    if not refs:
        raise PsycheError(
            "Every Psyche entry requires at least one provenance reference "
            "(Art. 5, Art. 11): nothing here may be unmoored from a real record."
        )
    return refs


class PsycheStore:
    """Append-only, hash-chained Psyche character store."""

    def __init__(self) -> None:
        self._path = psyche_events_path()

    # ---------------- low-level chain ----------------

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
                    raise PsycheIntegrityError(
                        f"Psyche store line {i} is not valid JSON: {e}"
                    ) from e
        return records

    def _verify_records(self, records: List[Dict[str, Any]]) -> None:
        from seira_core.unity import read_lock

        expected_prev = read_lock().get("unity_sha256")
        for idx, rec in enumerate(records):
            n = idx + 1
            if rec.get("seq") != n:
                raise PsycheIntegrityError(
                    f"Psyche event sequence broken at position {n}: record says "
                    f"{rec.get('seq')!r}. Reordering or deletion has occurred."
                )
            if rec.get("prev_hash") != expected_prev:
                raise PsycheIntegrityError(
                    f"Psyche hash chain broken at event {n}."
                )
            recomputed = sha256_record(rec)
            if rec.get("hash") != recomputed:
                raise PsycheIntegrityError(
                    f"Psyche event {n} altered after the fact: stored "
                    f"{rec.get('hash')!r}, recomputed {recomputed!r}."
                )
            expected_prev = rec["hash"]
        if records and records[0].get("event") != EVENT_FOUNDED:
            raise PsycheIntegrityError(
                "Psyche store's first event is not the founding event — "
                "the record has been reconstructed (Art. 22)."
            )

    def verify_chain(self) -> int:
        records = self._read_raw()
        if records:
            self._verify_records(records)
        return len(records)

    def founded(self) -> bool:
        return self._path.exists() and bool(self._read_raw())

    def _append(self, event: str, data: Dict[str, Any]) -> Dict[str, Any]:
        from seira_core.tripwire import assert_not_halted
        from seira_core.unity import read_lock

        assert_not_halted()
        records = self._read_raw()
        if records:
            self._verify_records(records)  # never append onto a broken chain
            prev_hash = records[-1]["hash"]
        else:
            prev_hash = read_lock()["unity_sha256"]
        record: Dict[str, Any] = {
            "seq": len(records) + 1,
            "event": event,
            "ts": _utc_now_iso(),
            "prev_hash": prev_hash,
            **data,
        }
        record["hash"] = sha256_record(record)
        psyche_dir().mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return record

    # ---------------- founding (called by genesis only) ----------------

    def _found(self, architect: str, founding_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Written by perform_psyche_genesis alone (Art. 22)."""
        if self.founded():
            raise PsycheError("Psyche is already founded; Genesis is non-repeatable.")
        founding = self._append(EVENT_FOUNDED, {"architect": architect})
        for e in founding_entries:
            self.add_entry(
                category=e["category"],
                content=e["content"],
                cause={"type": "paradigmatic", "ref": "Genesis (Art. 22)"},
                provenance=["genesis"],
                weight=e.get("weight"),
            )
        return founding

    # ---------------- entry operations ----------------

    def add_entry(
        self,
        category: str,
        content: str,
        cause: Dict[str, Any],
        provenance: List[str],
        weight: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Add a provisional entry. All entries are born provisional;
        standing rises only through change_standing (Art. 33)."""
        if not self.founded():
            raise PsycheError("Psyche has not been founded (Art. 22).")
        if category not in CATEGORIES:
            raise PsycheError(
                f"Unknown category {category!r}; must be one of {sorted(CATEGORIES)}. "
                "Session reasoning traces are Corpus content and are never "
                "written to the character store (Art. 18)."
            )
        if not content.strip():
            raise PsycheError("Entry content must not be empty.")
        cause = _validate_cause(cause)
        provenance = _validate_provenance(provenance)
        data: Dict[str, Any] = {
            "entry_id": f"psy-{self._next_entry_number():05d}",
            "category": category,
            "content": content.strip(),
            "cause": cause,
            "provenance": provenance,
            "standing": "provisional",
        }
        if category == "affinity":
            w = 0.1 if weight is None else float(weight)
            if not (0.0 <= w <= 1.0):
                raise PsycheError("Affinity weight must be within [0, 1].")
            data["weight"] = round(w, 4)
        elif weight is not None:
            raise PsycheError("Only affinities carry weights (Art. 11).")
        return self._append(EVENT_ENTRY_ADDED, data)

    def _next_entry_number(self) -> int:
        return 1 + sum(
            1 for r in self._read_raw() if r.get("event") == EVENT_ENTRY_ADDED
        )

    def change_standing(
        self,
        entry_id: str,
        to: str,
        basis_ref: str,
        falsification_ref: Optional[str] = None,
        contradicts_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Move an entry's standing (Art. 25 pattern, Art. 33).

        * → established: requires falsification_ref — the record of the
          deliberate attempt to break it that it survived (Art. 25.2).
          Confirmation by accumulation alone is expressly insufficient,
          so no volume of provenance substitutes for this field.
        * → suspended: requires contradicts_ref — the surviving rival it
          stands in genuine contradiction with (Art. 25, Suspended).
        * → retired: use retire_entry, which demands a reason.
        """
        if to not in STANDINGS or to == "retired":
            raise PsycheError(
                f"Standing must be one of {sorted(STANDINGS - {'retired'})} here; "
                "use retire_entry for retirement."
            )
        state = self.state()
        entry = state["entries"].get(entry_id)
        if entry is None:
            raise PsycheError(f"No Psyche entry {entry_id!r}.")
        if entry["standing"] == "retired":
            raise PsycheError(f"{entry_id} is retired; retirement is terminal.")
        if to == "established" and not (falsification_ref and falsification_ref.strip()):
            raise PsycheError(
                "Establishing an entry requires a falsification_ref (Art. 25.2, "
                "Art. 33): it must have survived a deliberate attempt to break "
                "it, not merely accumulated support."
            )
        if to == "suspended" and not (contradicts_ref and contradicts_ref.strip()):
            raise PsycheError(
                "Suspension requires contradicts_ref: the surviving rival "
                "hypothesis this entry is in genuine contradiction with (Art. 25)."
            )
        if not basis_ref.strip():
            raise PsycheError("A basis_ref for the standing change is required (Art. 5).")
        data = {
            "entry_id": entry_id,
            "from": entry["standing"],
            "to": to,
            "basis_ref": basis_ref.strip(),
        }
        if falsification_ref:
            data["falsification_ref"] = falsification_ref.strip()
        if contradicts_ref:
            data["contradicts_ref"] = contradicts_ref.strip()
        rec = self._append(EVENT_STANDING_CHANGED, data)
        append_event("psyche_standing_changed", data)  # learning-adjacent audit
        return rec

    def engage_affinity(
        self, entry_id: str, delta: float, evidence_ref: str
    ) -> Dict[str, Any]:
        """The only way an affinity's weight moves (Art. 11): a bounded
        delta carrying the engagement that occasioned it. There is no
        set-weight operation anywhere in this store."""
        if not evidence_ref or not evidence_ref.strip():
            raise PsycheError(
                "Affinity weight moves only through evidence of engagement "
                "(Art. 11); evidence_ref is required."
            )
        if not (-0.2 <= float(delta) <= 0.2):
            raise PsycheError(
                "Affinity deltas are bounded to ±0.2 per engagement: weights "
                "strengthen over time, not by assignment (Art. 11)."
            )
        state = self.state()
        entry = state["entries"].get(entry_id)
        if entry is None or entry["category"] != "affinity":
            raise PsycheError(f"{entry_id!r} is not an affinity entry.")
        if entry["standing"] == "retired":
            raise PsycheError(f"{entry_id} is retired.")
        new_weight = round(min(1.0, max(0.0, entry["weight"] + float(delta))), 4)
        return self._append(
            EVENT_AFFINITY_ENGAGED,
            {
                "entry_id": entry_id,
                "delta": round(float(delta), 4),
                "weight": new_weight,
                "evidence_ref": evidence_ref.strip(),
            },
        )

    def retire_entry(self, entry_id: str, reason: str) -> Dict[str, Any]:
        """Retired, never deleted (Art. 36 pattern): history remains."""
        if not reason or not reason.strip():
            raise PsycheError("Retirement requires a stated reason.")
        state = self.state()
        entry = state["entries"].get(entry_id)
        if entry is None:
            raise PsycheError(f"No Psyche entry {entry_id!r}.")
        if entry["standing"] == "retired":
            raise PsycheError(f"{entry_id} is already retired.")
        rec = self._append(
            EVENT_RETIRED, {"entry_id": entry_id, "reason": reason.strip()}
        )
        append_event("psyche_entry_retired", {"entry_id": entry_id, "reason": reason.strip()})
        return rec

    # ---------------- materialized state (replay) ----------------

    def state(self, verify: bool = True) -> Dict[str, Any]:
        """Current character state, derived by replaying the full event
        history. Nothing is ever read from a mutable snapshot; what she
        is now is always exactly what her history adds up to."""
        records = self._read_raw()
        if verify and records:
            self._verify_records(records)
        entries: Dict[str, Dict[str, Any]] = {}
        founded = False
        for rec in records:
            ev = rec["event"]
            if ev == EVENT_FOUNDED:
                founded = True
            elif ev == EVENT_ENTRY_ADDED:
                entries[rec["entry_id"]] = {
                    "entry_id": rec["entry_id"],
                    "category": rec["category"],
                    "content": rec["content"],
                    "cause": rec["cause"],
                    "provenance": list(rec["provenance"]),
                    "standing": rec["standing"],
                    "created_at": rec["ts"],
                    **({"weight": rec["weight"]} if "weight" in rec else {}),
                }
            elif ev == EVENT_STANDING_CHANGED:
                e = entries.get(rec["entry_id"])
                if e is not None:
                    e["standing"] = rec["to"]
                    if "falsification_ref" in rec:
                        e["falsification_ref"] = rec["falsification_ref"]
                    if "contradicts_ref" in rec:
                        e["contradicts_ref"] = rec["contradicts_ref"]
            elif ev == EVENT_AFFINITY_ENGAGED:
                e = entries.get(rec["entry_id"])
                if e is not None:
                    e["weight"] = rec["weight"]
            elif ev == EVENT_RETIRED:
                e = entries.get(rec["entry_id"])
                if e is not None:
                    e["standing"] = "retired"
                    e["retired_reason"] = rec["reason"]
        return {"founded": founded, "entries": entries, "event_count": len(records)}

    def by_category(self, category: str, include_retired: bool = False) -> List[Dict[str, Any]]:
        if category not in CATEGORIES:
            raise PsycheError(f"Unknown category {category!r}.")
        return [
            e for e in self.state()["entries"].values()
            if e["category"] == category
            and (include_retired or e["standing"] != "retired")
        ]
