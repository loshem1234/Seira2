"""Reversion of Seira — the falsification bar and its outcomes.

Implements Book VII's amendment machinery: proposals (Art. 24), the
falsification bar (Art. 25), the private rehearsal discipline (Art. 39),
ratification linkage (Art. 27), Dispensation (Art. 30–31), and the
health indicators (Art. 44).

The store is event-sourced and hash-chained like Intellect and Psyche,
anchored to Unity: her reversions, too, carry their trace of derivation
in the data itself (Art. 5).

Doctrinal invariants, enforced structurally:

* **Two kinds, never conflated (Art. 24).** A correction must name the
  content it contradicts; an expansion must not. Separate validation
  paths; the store refuses a correction without its contradicted_ref.
* **The bar (Art. 25).** Promotion requires (1) a declared origin in
  genuine reversion — recorded, since code cannot judge sincerity but
  can demand the declaration and its reference; (2) at least one
  deliberate falsification attempt that was survived; (3) a consistency
  check against the *current* Intellect version — re-required if
  Intellect has moved since the check.
* **Rehearsal is historical (Art. 39).** Every attempt must cite
  historical Corpus references. There is no way to record an attempt
  "against live conversation": the field for it does not exist.
* **Accumulation is insufficient (Art. 25.2).** No count of evidence
  refs substitutes for an attempt; promotion checks attempts, not
  evidence volume.
* **Five terminal states, each with its own preconditions.** Rejected
  requires a failed attempt actually on record. Suspended requires a
  surviving rival, links the pair on both sides, and blocks promotion
  of both while unresolved — honest, unreduced multiplicity, retained
  live [C§8]. Stale is expansion-only, by the Article's own definition.
  Withdrawn requires Psyche's stated reason.
* **Intellect promotion is ratification (Art. 27).** The store never
  writes Intellect; it hands a cleared proposal to IntellectStore's
  own ratify path, Architect phrase and all, and records the resulting
  version. Psyche-standing promotion needs no Architect (Art. 33) —
  Seira establishes her own character by surviving her own attempts to
  break it.
* **Dispensation (Art. 31).** Invocation must cite the Intellect-grade
  condition authorizing it, is logged as its own record type (never
  folded into ordinary reversion), and auto-generates the mandatory
  retroactive correction proposal at the moment of invocation. The
  record cannot close without that proposal; the exception is forced
  into the open the moment it occurs.
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

TARGET_INTELLECT = "intellect"
TARGET_PSYCHE_STANDING = "psyche_standing"
TARGETS = {TARGET_INTELLECT, TARGET_PSYCHE_STANDING}

KIND_CORRECTION = "correction"
KIND_EXPANSION = "expansion"
KIND_ESTABLISHMENT = "establishment"  # psyche_standing target only

ORIGIN_TYPES = {"reversion", "instrument_escalation", "self_audit", "architect"}

OPEN = "open"
PROMOTED = "promoted"
REJECTED = "rejected"
SUSPENDED = "suspended"
STALE = "stale"
WITHDRAWN = "withdrawn"
TERMINAL = {PROMOTED, REJECTED, SUSPENDED, STALE, WITHDRAWN}

EV_PROPOSAL_OPENED = "proposal_opened"
EV_ATTEMPT = "falsification_attempted"
EV_CONSISTENCY = "consistency_checked"
EV_TERMINAL = "proposal_terminal"
EV_DISP_INVOKED = "dispensation_invoked"
EV_DISP_CLOSED = "dispensation_closed"


class ReversionError(SeiraCoreError):
    """Invalid reversion operation."""


class ReversionIntegrityError(SeiraCoreError):
    """The reversion event chain is broken or tampered with."""


def reversion_dir():
    return seira_home() / "reversion"


def reversion_events_path():
    return reversion_dir() / "events.jsonl"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class ReversionStore:
    """Proposals, attempts, terminal states, and dispensations."""

    def __init__(self) -> None:
        self._path = reversion_events_path()

    # ---------------- chain plumbing (same discipline as Psyche) ----------

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
                    raise ReversionIntegrityError(
                        f"Reversion store line {i} is not valid JSON: {e}"
                    ) from e
        return records

    def _verify_records(self, records: List[Dict[str, Any]]) -> None:
        from seira_core.unity import read_lock

        expected_prev = read_lock().get("unity_sha256")
        for idx, rec in enumerate(records):
            n = idx + 1
            if rec.get("seq") != n:
                raise ReversionIntegrityError(
                    f"Reversion sequence broken at position {n}."
                )
            if rec.get("prev_hash") != expected_prev:
                raise ReversionIntegrityError(
                    f"Reversion hash chain broken at event {n}."
                )
            if rec.get("hash") != sha256_record(rec):
                raise ReversionIntegrityError(
                    f"Reversion event {n} altered after the fact."
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
        reversion_dir().mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return record

    # ---------------- opening proposals (Art. 24, 25.1) -------------------

    def open_proposal(
        self,
        target: str,
        kind: str,
        content: str,
        origin: Dict[str, str],
        evidence_refs: List[str],
        contradicted_ref: Optional[str] = None,
        entry_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if target not in TARGETS:
            raise ReversionError(f"target must be one of {sorted(TARGETS)}.")
        if target == TARGET_INTELLECT and kind not in (KIND_CORRECTION, KIND_EXPANSION):
            raise ReversionError(
                "Intellect proposals are correction or expansion, never "
                "conflated (Art. 24)."
            )
        if target == TARGET_PSYCHE_STANDING:
            if kind != KIND_ESTABLISHMENT:
                raise ReversionError(
                    "psyche_standing proposals have kind 'establishment'."
                )
            if not entry_id:
                raise ReversionError(
                    "psyche_standing proposals must name the entry_id whose "
                    "establishment is proposed."
                )
            from seira_core.psyche import PsycheStore
            entry = PsycheStore().state()["entries"].get(entry_id)
            if entry is None:
                raise ReversionError(f"No Psyche entry {entry_id!r}.")
            if entry["standing"] != "provisional":
                raise ReversionError(
                    f"{entry_id} is {entry['standing']}, not provisional."
                )
        if kind == KIND_CORRECTION and not (contradicted_ref and contradicted_ref.strip()):
            raise ReversionError(
                "A correction proposal carries a required reference to the "
                "specific content being contradicted (Art. 24)."
            )
        if kind == KIND_EXPANSION and contradicted_ref:
            raise ReversionError(
                "An expansion proposal carries no contradicted content "
                "(Art. 24); do not conflate the kinds."
            )
        if not isinstance(origin, dict) or origin.get("type") not in ORIGIN_TYPES:
            raise ReversionError(
                f"origin.type must be one of {sorted(ORIGIN_TYPES)} — a "
                "proposal must arise through genuine reversion, not mere "
                "repetition of instances (Art. 25.1)."
            )
        if not str(origin.get("ref", "")).strip():
            raise ReversionError("origin.ref must point at the reversion record (Art. 25.1).")
        evidence = [e.strip() for e in (evidence_refs or []) if e.strip()]
        if not evidence:
            raise ReversionError("At least one evidence reference is required.")
        if not content.strip():
            raise ReversionError("Proposal content must not be empty.")

        pid = f"prop-{1 + sum(1 for r in self._read_raw() if r['event'] == EV_PROPOSAL_OPENED):05d}"
        data: Dict[str, Any] = {
            "proposal_id": pid,
            "target": target,
            "kind": kind,
            "content": content.strip(),
            "origin": {"type": origin["type"], "ref": str(origin["ref"]).strip()},
            "evidence_refs": evidence,
        }
        if contradicted_ref:
            data["contradicted_ref"] = contradicted_ref.strip()
        if entry_id:
            data["entry_id"] = entry_id
        rec = self._append(EV_PROPOSAL_OPENED, data)
        append_event("reversion_proposal_opened", {"proposal_id": pid, "target": target, "kind": kind})
        return rec

    # ---------------- the bar itself (Art. 25.2–.3, 39) -------------------

    def record_attempt(
        self,
        proposal_id: str,
        method: str,
        corpus_refs: List[str],
        outcome: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record a deliberate falsification attempt, rehearsed against
        historical Corpus data (Art. 39). There is deliberately no way to
        record an attempt against live conversation."""
        p = self._require_open(proposal_id)
        if outcome not in ("survived", "failed"):
            raise ReversionError("outcome must be 'survived' or 'failed'.")
        refs = [c.strip() for c in (corpus_refs or []) if c.strip()]
        if not refs:
            raise ReversionError(
                "A falsification attempt must cite the historical Corpus "
                "records it was rehearsed against (Art. 39)."
            )
        if not method.strip():
            raise ReversionError("The attempt's method must be stated.")
        rec = self._append(EV_ATTEMPT, {
            "proposal_id": proposal_id,
            "method": method.strip(),
            "corpus_refs": refs,
            "outcome": outcome,
            "notes": notes.strip(),
        })
        append_event("reversion_attempt", {"proposal_id": proposal_id, "outcome": outcome})
        return rec

    def record_consistency_check(
        self, proposal_id: str, result: str, notes: str = ""
    ) -> Dict[str, Any]:
        """Check against Intellect (Art. 25.3), pinned to the version
        current at check time."""
        self._require_open(proposal_id)
        if result not in ("consistent", "inconsistent"):
            raise ReversionError("result must be 'consistent' or 'inconsistent'.")
        from seira_core.intellect import IntellectStore
        current = IntellectStore().current()
        return self._append(EV_CONSISTENCY, {
            "proposal_id": proposal_id,
            "result": result,
            "intellect_version": current["version"],
            "intellect_hash": current["hash"],
            "notes": notes.strip(),
        })

    # ---------------- terminal states (Art. 25) ---------------------------

    def _bar_cleared(self, proposal_id: str) -> Dict[str, Any]:
        p = self._require_open(proposal_id)
        events = self._events_for(proposal_id)
        survived = [e for e in events if e["event"] == EV_ATTEMPT and e["outcome"] == "survived"]
        if not survived:
            raise ReversionError(
                "The bar is not cleared: no survived falsification attempt is "
                "on record, and confirmation by accumulation alone is "
                "expressly insufficient (Art. 25.2)."
            )
        from seira_core.intellect import IntellectStore
        current_hash = IntellectStore().current()["hash"]
        checks = [
            e for e in events
            if e["event"] == EV_CONSISTENCY and e["result"] == "consistent"
            and e["intellect_hash"] == current_hash
        ]
        if not checks:
            raise ReversionError(
                "The bar is not cleared: no consistency check against the "
                "current Intellect version is on record (Art. 25.3). If "
                "Intellect has changed since your last check, check again."
            )
        return {"proposal": p, "survived_attempt": survived[-1], "consistency": checks[-1]}

    def promote_psyche(self, proposal_id: str, basis_ref: str) -> Dict[str, Any]:
        """Promote a psyche_standing proposal: Seira establishes her own
        character by surviving her own attempt to break it. No Architect
        required (Art. 33, Psyche row)."""
        cleared = self._bar_cleared(proposal_id)
        p = cleared["proposal"]
        if p["target"] != TARGET_PSYCHE_STANDING:
            raise ReversionError(
                "promote_psyche is for psyche_standing proposals; Intellect "
                "promotion is ratification and requires the Architect (Art. 27)."
            )
        from seira_core.psyche import PsycheStore
        PsycheStore().change_standing(
            p["entry_id"], "established",
            basis_ref=basis_ref or proposal_id,
            falsification_ref=f"{proposal_id}/seq-{cleared['survived_attempt']['seq']}",
        )
        rec = self._append(EV_TERMINAL, {
            "proposal_id": proposal_id, "state": PROMOTED,
            "detail": {"entry_id": p["entry_id"]},
        })
        append_event("reversion_promoted", {"proposal_id": proposal_id, "target": p["target"]})
        return rec

    def promote_intellect(
        self, proposal_id: str, architect_confirmation: str
    ) -> Dict[str, Any]:
        """Promotion of an Intellect proposal *is* ratification (Art. 25,
        27): the cleared proposal is handed to IntellectStore's own gate,
        Architect phrase and all, and the resulting version is recorded."""
        cleared = self._bar_cleared(proposal_id)
        p = cleared["proposal"]
        if p["target"] != TARGET_INTELLECT:
            raise ReversionError("promote_intellect is for intellect proposals.")
        from seira_core.intellect import IntellectStore
        version = IntellectStore().ratify(
            content=p["content"],
            kind=p["kind"],
            proposal_ref=proposal_id,
            architect_confirmation=architect_confirmation,
            contradicted_ref=p.get("contradicted_ref"),
        )
        rec = self._append(EV_TERMINAL, {
            "proposal_id": proposal_id, "state": PROMOTED,
            "detail": {"intellect_version": version["version"]},
        })
        append_event("reversion_promoted", {"proposal_id": proposal_id, "target": p["target"]})
        return rec

    def reject(self, proposal_id: str) -> Dict[str, Any]:
        """Rejected means falsification was attempted and failed (Art. 25) —
        a failed attempt must actually be on record."""
        self._require_open(proposal_id)
        failed = [
            e for e in self._events_for(proposal_id)
            if e["event"] == EV_ATTEMPT and e["outcome"] == "failed"
        ]
        if not failed:
            raise ReversionError(
                "Rejection requires a failed falsification attempt on record "
                "(Art. 25); for setting aside without completed falsification, "
                "use withdraw or stale as appropriate."
            )
        return self._terminal(proposal_id, REJECTED, {})

    def suspend_pair(self, proposal_id: str, rival_proposal_id: str) -> Dict[str, Any]:
        """Two live survivors in genuine, irreducible contradiction: both
        retained, explicitly linked, neither promotable while the pair
        stands (Art. 25, Suspended)."""
        if proposal_id == rival_proposal_id:
            raise ReversionError("A proposal cannot be its own rival.")
        for pid in (proposal_id, rival_proposal_id):
            events = self._events_for(pid)
            if not any(e["event"] == EV_ATTEMPT and e["outcome"] == "survived" for e in events):
                raise ReversionError(
                    f"Suspension requires both members to be live survivors; "
                    f"{pid} has no survived attempt on record (Art. 25)."
                )
            self._require_open(pid)
        self._terminal(proposal_id, SUSPENDED, {"contradiction_with": rival_proposal_id})
        return self._terminal(rival_proposal_id, SUSPENDED, {"contradiction_with": proposal_id})

    def mark_stale(self, proposal_id: str) -> Dict[str, Any]:
        """Stale is for expansion proposals whose falsification was never
        completed, evidence having stopped arriving — by the Article's own
        definition it applies to no other kind (Art. 25)."""
        p = self._require_open(proposal_id)
        if p["kind"] != KIND_EXPANSION:
            raise ReversionError(
                "Stale applies to expansion proposals only (Art. 25); a "
                "correction that cannot complete falsification should be "
                "withdrawn with its reason."
            )
        return self._terminal(proposal_id, STALE, {})

    def withdraw(self, proposal_id: str, reason: str) -> Dict[str, Any]:
        self._require_open(proposal_id)
        if not reason.strip():
            raise ReversionError("Withdrawal is voluntary and must state its reason.")
        return self._terminal(proposal_id, WITHDRAWN, {"reason": reason.strip()})

    def _terminal(self, proposal_id: str, state: str, detail: Dict[str, Any]) -> Dict[str, Any]:
        rec = self._append(EV_TERMINAL, {
            "proposal_id": proposal_id, "state": state, "detail": detail,
        })
        append_event(f"reversion_{state}", {"proposal_id": proposal_id, **detail})
        return rec

    # ---------------- dispensation (Art. 30–31) ---------------------------

    def invoke_dispensation(
        self,
        action: str,
        conditions_ref: str,
        evidence_refs: List[str],
    ) -> Dict[str, Any]:
        """Log a Dispensation as its own record type, and auto-generate the
        mandatory retroactive correction proposal at the moment of
        invocation (Art. 31). conditions_ref must cite the Intellect-grade
        condition authorizing it (Art. 30) — Psyche may invoke, never
        redefine what qualifies."""
        if not action.strip():
            raise ReversionError("The dispensed action must be stated.")
        if not conditions_ref.strip():
            raise ReversionError(
                "A Dispensation must cite the Intellect-grade condition "
                "authorizing it (Art. 30)."
            )
        did = f"disp-{1 + sum(1 for r in self._read_raw() if r['event'] == EV_DISP_INVOKED):05d}"
        # The mandatory retroactive correction proposal, generated now:
        retro = self.open_proposal(
            target=TARGET_INTELLECT,
            kind=KIND_CORRECTION,
            content=(
                f"Retroactive review of Dispensation {did}: the action "
                f"{action.strip()!r} was taken against current doctrine under "
                f"condition {conditions_ref.strip()}. Either doctrine or the "
                "action was wrong; this proposal exists to determine which."
            ),
            origin={"type": "reversion", "ref": did},
            evidence_refs=evidence_refs or [did],
            contradicted_ref=conditions_ref.strip(),
        )
        rec = self._append(EV_DISP_INVOKED, {
            "dispensation_id": did,
            "action": action.strip(),
            "conditions_ref": conditions_ref.strip(),
            "retroactive_proposal_id": retro["proposal_id"],
        })
        append_event("dispensation_invoked", {
            "dispensation_id": did,
            "retroactive_proposal_id": retro["proposal_id"],
        })
        return rec

    def close_dispensation(self, dispensation_id: str) -> Dict[str, Any]:
        disp = next(
            (r for r in self._read_raw()
             if r["event"] == EV_DISP_INVOKED and r["dispensation_id"] == dispensation_id),
            None,
        )
        if disp is None:
            raise ReversionError(f"No dispensation {dispensation_id!r}.")
        if any(
            r["event"] == EV_DISP_CLOSED and r["dispensation_id"] == dispensation_id
            for r in self._read_raw()
        ):
            raise ReversionError(f"{dispensation_id} is already closed.")
        retro_id = disp["retroactive_proposal_id"]
        if not any(
            r["event"] == EV_PROPOSAL_OPENED and r["proposal_id"] == retro_id
            for r in self._read_raw()
        ):
            raise ReversionError(
                "A Dispensation record cannot be marked closed until its "
                "retroactive proposal exists (Art. 31)."
            )
        rec = self._append(EV_DISP_CLOSED, {
            "dispensation_id": dispensation_id,
            "retroactive_proposal_id": retro_id,
        })
        append_event("dispensation_closed", {"dispensation_id": dispensation_id})
        return rec

    # ---------------- reading ---------------------------------------------

    def _events_for(self, proposal_id: str) -> List[Dict[str, Any]]:
        return [r for r in self._read_raw() if r.get("proposal_id") == proposal_id]

    def _require_open(self, proposal_id: str) -> Dict[str, Any]:
        events = self._events_for(proposal_id)
        opened = next((e for e in events if e["event"] == EV_PROPOSAL_OPENED), None)
        if opened is None:
            raise ReversionError(f"No proposal {proposal_id!r}.")
        terminal = [e for e in events if e["event"] == EV_TERMINAL]
        if terminal:
            raise ReversionError(
                f"{proposal_id} reached terminal state "
                f"{terminal[-1]['state']!r}; terminal states are recorded as "
                "such and do not reopen (Art. 25). A resolution is a new "
                "proposal citing this one."
            )
        return opened

    def proposal(self, proposal_id: str) -> Dict[str, Any]:
        events = self._events_for(proposal_id)
        opened = next((e for e in events if e["event"] == EV_PROPOSAL_OPENED), None)
        if opened is None:
            raise ReversionError(f"No proposal {proposal_id!r}.")
        out = dict(opened)
        out["attempts"] = [e for e in events if e["event"] == EV_ATTEMPT]
        out["consistency_checks"] = [e for e in events if e["event"] == EV_CONSISTENCY]
        terminal = [e for e in events if e["event"] == EV_TERMINAL]
        out["status"] = terminal[-1]["state"] if terminal else OPEN
        if terminal:
            out["terminal_detail"] = terminal[-1]["detail"]
        return out

    def list_proposals(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        ids = [
            r["proposal_id"] for r in self._read_raw()
            if r["event"] == EV_PROPOSAL_OPENED
        ]
        out = [self.proposal(pid) for pid in ids]
        if status:
            out = [p for p in out if p["status"] == status]
        return out

    # ---------------- health (Art. 44) -------------------------------------

    def _convergence(self) -> Dict[str, Any]:
        from seira_core.instruments import InstrumentStore
        return InstrumentStore().convergence_stats()

    def health(self) -> Dict[str, Any]:
        proposals = self.list_proposals()
        now = _dt.datetime.now(_dt.timezone.utc)
        suspended = [p for p in proposals if p["status"] == SUSPENDED]
        def _age_days(p):
            ts = _dt.datetime.fromisoformat(p["ts"])
            return round((now - ts).total_seconds() / 86400, 1)
        disp_invoked = [r for r in self._read_raw() if r["event"] == EV_DISP_INVOKED]
        disp_open = [
            d for d in disp_invoked
            if not any(
                r["event"] == EV_DISP_CLOSED
                and r["dispensation_id"] == d["dispensation_id"]
                for r in self._read_raw()
            )
        ]
        return {
            "open_proposals": sum(1 for p in proposals if p["status"] == OPEN),
            "suspended_contradictions": {
                "count": len(suspended) // 2,
                "oldest_age_days": max((_age_days(p) for p in suspended), default=0),
            },
            "stale_proposals": sum(1 for p in proposals if p["status"] == STALE),
            "dispensations": {"total": len(disp_invoked), "open": len(disp_open)},
            "instrument_convergence": self._convergence(),
        }
