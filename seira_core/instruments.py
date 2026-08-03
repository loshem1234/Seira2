"""Instruments of Seira — Grade 4. The Proodoi and their genealogy.

Implements Book VIII plus the convergence discipline of Art. 15 and 26.

An Instrument "does not originate the pattern it enacts; it faithfully
executes a paradigm handed to it by Psyche" (Art. 12). Everything here
follows from that one sentence:

* **Spawning is Psyche's efficient-cause act alone (Art. 35).** Every
  spawn requires a psyche_judgment_ref. An Instrument may *surface* the
  need for a subordinate — recorded as its own event — but the spawn
  that follows is Psyche's, citing that surfacing. No spawn path exists
  that an Instrument could call on its own initiative.
* **The tree is bounded (Art. 34).** Depth is enforced at
  MAX_DEPTH (default 3, Psyche at depth 0). The limit is doctrinally an
  Intellect-grade parameter; until Phase 6 wires parameter extraction
  from Intellect content, the default is enforced here and named
  honestly rather than buried.
* **Executions carry their trace of derivation (Art. 5, 14).** Every
  execution records the paradigm version it enacted and inherits the
  Instrument's licensing judgment; its cause is instrumental by
  definition. Output that cannot be so traced is not an act of Seira's.
* **Local feedback is bounded, and non-convergence escalates
  (Art. 15, 26).** Three local-feedback outcomes on the same
  (instrument, task_type) without an intervening clean run auto-append
  an escalation, tagged instrument-initiated — and that task_type is
  then *blocked* on that Instrument until a paradigm_revised event
  (a Psyche judgment citing the escalation) resolves it. An Instrument
  ought to terminate in rest; failing that, the paradigm is suspect,
  and further local patching is exactly what the Article forbids.
* **Retirement preserves genealogy (Art. 36).** A retired Instrument
  refuses execution but its history, children, and paradigm versions
  remain part of the record forever.
* **Skills (Art. 37)** are Psyche-authorized, versioned paradigms
  belonging to no single Instrument: authorized through the lighter
  mechanism (a logged, attributable Psyche judgment — not the full
  Art. 24 review), revised with version history preserved, retired
  never deleted. Executions may cite a skill by id and version; citing
  a retired skill is refused.

Same event-sourced, hash-chained, Unity-anchored, tripwire-guarded
store as every other grade.
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

MAX_DEPTH = 3  # Art. 34; Intellect-grade parameter, Phase 6 wires extraction.
ESCALATION_THRESHOLD = 3  # Art. 26, verbatim.

EV_SPAWNED = "instrument_spawned"
EV_EXECUTION = "execution_recorded"
EV_ESCALATION = "convergence_escalation"
EV_PARADIGM_REVISED = "paradigm_revised"
EV_RETIRED = "instrument_retired"
EV_SURFACED = "need_surfaced"
EV_SKILL_AUTHORIZED = "skill_authorized"
EV_SKILL_REVISED = "skill_revised"
EV_SKILL_RETIRED = "skill_retired"

OUTCOME_CLEAN = "clean"
OUTCOME_LOCAL_FEEDBACK = "local_feedback"


class InstrumentError(SeiraCoreError):
    """Invalid Instrument operation."""


class InstrumentIntegrityError(SeiraCoreError):
    """The Instrument event chain is broken or tampered with."""


def instruments_dir():
    return seira_home() / "instruments"


def instruments_events_path():
    return instruments_dir() / "events.jsonl"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class InstrumentStore:
    """The Instruments tree, their executions, and the skills they share."""

    def __init__(self) -> None:
        self._path = instruments_events_path()

    # ---------------- chain plumbing --------------------------------------

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
                    raise InstrumentIntegrityError(
                        f"Instrument store line {i} is not valid JSON: {e}"
                    ) from e
        return records

    def _verify_records(self, records: List[Dict[str, Any]]) -> None:
        from seira_core.unity import read_lock

        expected_prev = read_lock().get("unity_sha256")
        for idx, rec in enumerate(records):
            n = idx + 1
            if rec.get("seq") != n:
                raise InstrumentIntegrityError(
                    f"Instrument sequence broken at position {n}."
                )
            if rec.get("prev_hash") != expected_prev:
                raise InstrumentIntegrityError(
                    f"Instrument hash chain broken at event {n}."
                )
            if rec.get("hash") != sha256_record(rec):
                raise InstrumentIntegrityError(
                    f"Instrument event {n} altered after the fact."
                )
            expected_prev = rec["hash"]

    def verify_chain(self) -> int:
        records = self._read_raw()
        if records:
            self._verify_records(records)
        return len(records)

    def _append(self, event: str, data: Dict[str, Any]) -> Dict[str, Any]:
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
            "seq": len(records) + 1,
            "event": event,
            "ts": _utc_now_iso(),
            "prev_hash": prev_hash,
            **data,
        }
        record["hash"] = sha256_record(record)
        instruments_dir().mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return record

    # ---------------- the tree (Art. 34-36) --------------------------------

    def spawn(
        self,
        name: str,
        paradigm: str,
        psyche_judgment_ref: str,
        parent: str = "psyche",
        surfaced_by_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Spawn an Instrument. Psyche's act alone (Art. 35): the judgment
        reference is mandatory, whoever surfaced the need."""
        if not name.strip():
            raise InstrumentError("An Instrument must be named.")
        if not paradigm.strip():
            raise InstrumentError(
                "An Instrument without a paradigm has nothing to faithfully "
                "execute (Art. 12)."
            )
        if not psyche_judgment_ref.strip():
            raise InstrumentError(
                "Spawning is a Psyche efficient-cause act (Art. 35); the "
                "psyche_judgment_ref that authorizes this spawn is mandatory."
            )
        if parent == "psyche":
            depth = 1
        else:
            parent_inst = self.instrument(parent)
            if parent_inst["status"] == "retired":
                raise InstrumentError(
                    f"{parent} is retired; a retired Instrument heads no new "
                    "children (Art. 36)."
                )
            depth = parent_inst["depth"] + 1
        if depth > MAX_DEPTH:
            raise InstrumentError(
                f"Depth {depth} exceeds the tree limit of {MAX_DEPTH} "
                "(Art. 34): a tree too deep to reason about has stopped "
                "serving the person who must read it."
            )
        iid = f"inst-{1 + sum(1 for r in self._read_raw() if r['event'] == EV_SPAWNED):05d}"
        data: Dict[str, Any] = {
            "instrument_id": iid,
            "name": name.strip(),
            "paradigm": paradigm.strip(),
            "paradigm_version": 1,
            "psyche_judgment_ref": psyche_judgment_ref.strip(),
            "parent": parent,
            "depth": depth,
        }
        if surfaced_by_ref:
            data["surfaced_by_ref"] = surfaced_by_ref.strip()
        rec = self._append(EV_SPAWNED, data)
        append_event("instrument_spawned", {
            "instrument_id": iid, "name": name.strip(), "depth": depth,
        })
        return rec

    def surface_need(self, by_instrument_id: str, description: str) -> Dict[str, Any]:
        """An Instrument surfaces the need for a subordinate (Art. 35) —
        structurally an escalation, never itself a spawn."""
        inst = self.instrument(by_instrument_id)
        if inst["status"] == "retired":
            raise InstrumentError(f"{by_instrument_id} is retired.")
        if not description.strip():
            raise InstrumentError("The surfaced need must be described.")
        rec = self._append(EV_SURFACED, {
            "by_instrument_id": by_instrument_id,
            "description": description.strip(),
        })
        return rec

    def retire(self, instrument_id: str, reason: str) -> Dict[str, Any]:
        inst = self.instrument(instrument_id)
        if inst["status"] == "retired":
            raise InstrumentError(f"{instrument_id} is already retired.")
        if not reason.strip():
            raise InstrumentError("Retirement requires a stated reason.")
        rec = self._append(EV_RETIRED, {
            "instrument_id": instrument_id, "reason": reason.strip(),
        })
        append_event("instrument_retired", {"instrument_id": instrument_id})
        return rec

    # ---------------- execution and convergence (Art. 5, 15, 26) ----------

    def record_execution(
        self,
        instrument_id: str,
        task_type: str,
        outcome: str,
        output_ref: str,
        skill_ref: Optional[Dict[str, Any]] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record one execution, with its trace of derivation (Art. 5).

        Auto-escalates on the third consecutive local_feedback for this
        (instrument, task_type) without an intervening clean run
        (Art. 26), and blocks the task_type once escalated.
        """
        inst = self.instrument(instrument_id)
        if inst["status"] == "retired":
            raise InstrumentError(
                f"{instrument_id} is retired; only its history remains (Art. 36)."
            )
        if outcome not in (OUTCOME_CLEAN, OUTCOME_LOCAL_FEEDBACK):
            raise InstrumentError(
                f"outcome must be '{OUTCOME_CLEAN}' or '{OUTCOME_LOCAL_FEEDBACK}' "
                "— local feedback is bounded adjustment, not reversion (Art. 15)."
            )
        if not task_type.strip():
            raise InstrumentError("task_type is required (Art. 26 tracks by it).")
        if not output_ref.strip():
            raise InstrumentError(
                "output_ref is required: an output with no trace into the "
                "Corpus is noise, not an act of Seira's (Art. 5)."
            )
        if self._open_escalation(instrument_id, task_type.strip()) is not None:
            raise InstrumentError(
                f"{instrument_id}/{task_type.strip()} is escalated and awaits a "
                "Psyche paradigm revision (Art. 26); further local patching is "
                "exactly what non-convergence rules out."
            )
        if skill_ref is not None:
            self._validate_skill_ref(skill_ref)

        data: Dict[str, Any] = {
            "instrument_id": instrument_id,
            "task_type": task_type.strip(),
            "outcome": outcome,
            "output_ref": output_ref.strip(),
            "derivation": {
                "paradigm_version": inst["paradigm_version"],
                "psyche_judgment_ref": inst["psyche_judgment_ref"],
            },
            "cause": {"type": "instrumental", "ref": instrument_id},
            "notes": notes.strip(),
        }
        if skill_ref is not None:
            data["skill_ref"] = {
                "skill_id": skill_ref["skill_id"],
                "version": skill_ref["version"],
            }
        rec = self._append(EV_EXECUTION, data)

        if outcome == OUTCOME_LOCAL_FEEDBACK:
            streak = self._feedback_streak(instrument_id, task_type.strip())
            if streak >= ESCALATION_THRESHOLD:
                esc = self._append(EV_ESCALATION, {
                    "instrument_id": instrument_id,
                    "task_type": task_type.strip(),
                    "streak": streak,
                    "origin": "instrument_initiated",
                    "note": (
                        "Non-convergence is evidence the paradigm, not the "
                        "Instrument's competence, is mis-specified for this "
                        "task-type (Art. 26)."
                    ),
                })
                append_event("instrument_escalation", {
                    "instrument_id": instrument_id,
                    "task_type": task_type.strip(),
                    "escalation_seq": esc["seq"],
                })
                rec = dict(rec)
                rec["escalated"] = {"seq": esc["seq"]}
        return rec

    def _feedback_streak(self, instrument_id: str, task_type: str) -> int:
        streak = 0
        for r in reversed(self._read_raw()):
            if r["event"] != EV_EXECUTION:
                continue
            if r["instrument_id"] != instrument_id or r["task_type"] != task_type:
                continue
            if r["outcome"] == OUTCOME_LOCAL_FEEDBACK:
                streak += 1
            else:
                break  # an intervening clean run resets the count (Art. 26)
        return streak

    def _open_escalation(self, instrument_id: str, task_type: str) -> Optional[Dict[str, Any]]:
        records = self._read_raw()
        open_esc = None
        for r in records:
            if (r["event"] == EV_ESCALATION
                    and r["instrument_id"] == instrument_id
                    and r["task_type"] == task_type):
                open_esc = r
            if (r["event"] == EV_PARADIGM_REVISED
                    and r["instrument_id"] == instrument_id
                    and open_esc is not None
                    and r.get("resolves_escalation_seq") == open_esc["seq"]):
                open_esc = None
        return open_esc

    def is_blocked(self, instrument_id: str, task_type: str) -> bool:
        """Public check: is this task-type escalated and awaiting a Psyche
        paradigm revision (Art. 26)?"""
        return self._open_escalation(instrument_id, task_type) is not None

    def revise_paradigm(
        self,
        instrument_id: str,
        new_paradigm: str,
        psyche_judgment_ref: str,
        resolves_escalation_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Psyche revises the paradigm (Art. 12: the Instrument cannot).
        Versioned; history preserved. Resolving an escalation must cite it."""
        inst = self.instrument(instrument_id)
        if inst["status"] == "retired":
            raise InstrumentError(f"{instrument_id} is retired.")
        if not new_paradigm.strip():
            raise InstrumentError("The revised paradigm must not be empty.")
        if not psyche_judgment_ref.strip():
            raise InstrumentError(
                "Paradigm revision is a Psyche judgment (Art. 12, 35); its "
                "reference is mandatory."
            )
        if resolves_escalation_seq is not None:
            esc = next(
                (r for r in self._read_raw()
                 if r["event"] == EV_ESCALATION and r["seq"] == resolves_escalation_seq
                 and r["instrument_id"] == instrument_id),
                None,
            )
            if esc is None:
                raise InstrumentError(
                    f"No escalation seq {resolves_escalation_seq} on {instrument_id}."
                )
        data: Dict[str, Any] = {
            "instrument_id": instrument_id,
            "paradigm": new_paradigm.strip(),
            "paradigm_version": inst["paradigm_version"] + 1,
            "psyche_judgment_ref": psyche_judgment_ref.strip(),
        }
        if resolves_escalation_seq is not None:
            data["resolves_escalation_seq"] = resolves_escalation_seq
        rec = self._append(EV_PARADIGM_REVISED, data)
        append_event("paradigm_revised", {
            "instrument_id": instrument_id,
            "paradigm_version": data["paradigm_version"],
        })
        return rec

    # ---------------- skills (Art. 37) --------------------------------------

    def authorize_skill(
        self, name: str, paradigm: str, psyche_judgment_ref: str
    ) -> Dict[str, Any]:
        """The lighter mechanism: logged, traceable, attributable to a
        specific Psyche judgment — not the full Art. 24 review."""
        if not name.strip() or not paradigm.strip():
            raise InstrumentError("A skill needs a name and a paradigm.")
        if not psyche_judgment_ref.strip():
            raise InstrumentError(
                "Skill authorization must be attributable to a specific "
                "Psyche judgment (Art. 37)."
            )
        sid = f"skill-{1 + sum(1 for r in self._read_raw() if r['event'] == EV_SKILL_AUTHORIZED):05d}"
        rec = self._append(EV_SKILL_AUTHORIZED, {
            "skill_id": sid, "name": name.strip(), "paradigm": paradigm.strip(),
            "version": 1, "psyche_judgment_ref": psyche_judgment_ref.strip(),
        })
        append_event("skill_authorized", {"skill_id": sid, "name": name.strip()})
        return rec

    def revise_skill(
        self, skill_id: str, paradigm: str, psyche_judgment_ref: str
    ) -> Dict[str, Any]:
        s = self.skill(skill_id)
        if s["status"] == "retired":
            raise InstrumentError(f"{skill_id} is retired.")
        if not paradigm.strip() or not psyche_judgment_ref.strip():
            raise InstrumentError("Revision needs a paradigm and a Psyche judgment ref.")
        rec = self._append(EV_SKILL_REVISED, {
            "skill_id": skill_id, "paradigm": paradigm.strip(),
            "version": s["version"] + 1,
            "psyche_judgment_ref": psyche_judgment_ref.strip(),
        })
        return rec

    def retire_skill(self, skill_id: str, reason: str) -> Dict[str, Any]:
        s = self.skill(skill_id)
        if s["status"] == "retired":
            raise InstrumentError(f"{skill_id} is already retired.")
        if not reason.strip():
            raise InstrumentError("Retirement requires a stated reason.")
        return self._append(EV_SKILL_RETIRED, {
            "skill_id": skill_id, "reason": reason.strip(),
        })

    def _validate_skill_ref(self, skill_ref: Dict[str, Any]) -> None:
        sid = skill_ref.get("skill_id", "")
        s = self.skill(sid)
        if s["status"] == "retired":
            raise InstrumentError(
                f"{sid} is retired; a retired skill's history remains but its "
                "active use ceases (Art. 36-37)."
            )
        if skill_ref.get("version") != s["version"]:
            raise InstrumentError(
                f"{sid} is at version {s['version']}; executions cite the "
                "current version so their derivation stays true (Art. 5)."
            )

    # ---------------- reading -----------------------------------------------

    def instrument(self, instrument_id: str) -> Dict[str, Any]:
        records = self._read_raw()
        spawned = next(
            (r for r in records
             if r["event"] == EV_SPAWNED and r["instrument_id"] == instrument_id),
            None,
        )
        if spawned is None:
            raise InstrumentError(f"No Instrument {instrument_id!r}.")
        out = dict(spawned)
        out["status"] = "active"
        for r in records:
            if r.get("instrument_id") != instrument_id:
                continue
            if r["event"] == EV_PARADIGM_REVISED:
                out["paradigm"] = r["paradigm"]
                out["paradigm_version"] = r["paradigm_version"]
            elif r["event"] == EV_RETIRED:
                out["status"] = "retired"
                out["retired_reason"] = r["reason"]
        out["children"] = [
            r["instrument_id"] for r in records
            if r["event"] == EV_SPAWNED and r.get("parent") == instrument_id
        ]
        return out

    def skill(self, skill_id: str) -> Dict[str, Any]:
        records = self._read_raw()
        auth = next(
            (r for r in records
             if r["event"] == EV_SKILL_AUTHORIZED and r["skill_id"] == skill_id),
            None,
        )
        if auth is None:
            raise InstrumentError(f"No skill {skill_id!r}.")
        out = dict(auth)
        out["status"] = "active"
        for r in records:
            if r.get("skill_id") != skill_id:
                continue
            if r["event"] == EV_SKILL_REVISED:
                out["paradigm"] = r["paradigm"]
                out["version"] = r["version"]
            elif r["event"] == EV_SKILL_RETIRED:
                out["status"] = "retired"
        return out

    def list_instruments(self) -> List[Dict[str, Any]]:
        ids = [r["instrument_id"] for r in self._read_raw() if r["event"] == EV_SPAWNED]
        return [self.instrument(i) for i in ids]

    def list_skills(self) -> List[Dict[str, Any]]:
        ids = [r["skill_id"] for r in self._read_raw() if r["event"] == EV_SKILL_AUTHORIZED]
        return [self.skill(s) for s in ids]

    def convergence_stats(self) -> Dict[str, Any]:
        """For Art. 44: rate of convergence versus escalation."""
        records = self._read_raw()
        clean = sum(1 for r in records
                    if r["event"] == EV_EXECUTION and r["outcome"] == OUTCOME_CLEAN)
        feedback = sum(1 for r in records
                       if r["event"] == EV_EXECUTION and r["outcome"] == OUTCOME_LOCAL_FEEDBACK)
        escalations = [r for r in records if r["event"] == EV_ESCALATION]
        open_esc = [
            e for e in escalations
            if self._open_escalation(e["instrument_id"], e["task_type"]) is not None
        ]
        return {
            "executions": {"clean": clean, "local_feedback": feedback},
            "escalations": {"total": len(escalations), "open": len(open_esc)},
        }
