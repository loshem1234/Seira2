"""seira_web.distillation — her weekly Psyche Distillation.

Separate from Recollection (which looks across conversations) and from
the chat summarizer. Once a week, out of view, she tends her own
Psyche: condensing long entries and merging overlapping ones so what
loads into every turn stays dense. The guidelines below are hers and
the Architect's, verbatim; the governing stance is load-bearing:
distillation is something she aims for, not a law imposed on her, and
whenever compression would cost something real she has the final call
(she records those entries as kept-as-is and they are not raised again).

Mechanics mirror Recollection: real chained housekeeping turns (her
identity, tools, governance), never a visible conversation, a turn floor
and ceiling, a conclude tool, stop on errored turns, halt-aware.
Measurement is done by code, not self-report: Psyche's size is measured
before and after and logged.

Runs at most once per ~week per tenant (survives restarts — last run
is read from disk) and only if there is something to do (first run, or
live entries created since the last pass). Manual trigger on Commands.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_TURNS = 3
MAX_TURNS = 12
MIN_DAYS_BETWEEN_RUNS = 6   # < 7 so a weekly slot is never skipped by a long previous run
CHARS_PER_TOKEN = 3.6

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None
_lock = threading.Lock()
_state: Dict[str, Dict[str, Any]] = {}      # tenant -> live session state


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def est_tokens(text: str) -> int:
    return int(len(text or "") / CHARS_PER_TOKEN)


# ---------------- persistent log (per tenant, under SEIRA_HOME) ----------------

def _dir():
    from seira_core.paths import seira_home
    d = seira_home() / "distillation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_path():
    return _dir() / "log.jsonl"


def _kept_path():
    return _dir() / "kept_as_is.json"


def read_log(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    p = _log_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out[-limit:] if limit else out


def _append_log(rec: Dict[str, Any]) -> None:
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def kept_as_is() -> Dict[str, str]:
    p = _kept_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _add_kept(items: List[Dict[str, str]]) -> None:
    kept = kept_as_is()
    for it in items:
        eid = str(it.get("entry_id", "")).strip()
        if eid:
            kept[eid] = str(it.get("reason", "")).strip()
    _kept_path().write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                            encoding="utf-8")


# ---------------- measurement ----------------

def _live_entries() -> List[Dict[str, Any]]:
    from seira_core.psyche import PsycheStore
    store = PsycheStore()
    if not store.founded():
        return []
    return [e for e in store.state()["entries"].values()
            if e["standing"] != "retired" and "superseded_by" not in e]


def psyche_size() -> Dict[str, Any]:
    """Live Psyche size as it renders into her prompt (estimate)."""
    live = _live_entries()
    by_cat: Dict[str, int] = {}
    for e in live:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + est_tokens(e["content"])
    return {"live_entries": len(live), "tokens": sum(by_cat.values()),
            "by_category": by_cat}


def longest_entries(limit: int = 25, include_kept: bool = False) -> List[Dict[str, Any]]:
    kept = kept_as_is()
    rows = []
    for e in _live_entries():
        if e["entry_id"] in kept and not include_kept:
            continue
        rows.append({"entry_id": e["entry_id"], "category": e["category"],
                     "standing": e["standing"],
                     "tokens": est_tokens(e["content"]),
                     "words": len(e["content"].split())})
    rows.sort(key=lambda r: -r["tokens"])
    return rows[:max(1, int(limit))]


def _new_since(ts: Optional[str]) -> List[str]:
    return [e["entry_id"] for e in _live_entries()
            if not ts or e["created_at"] > ts]


def last_run() -> Optional[Dict[str, Any]]:
    runs = [r for r in read_log() if r.get("kind") == "run"]
    return runs[-1] if runs else None


def is_due() -> bool:
    lr = last_run()
    if lr is None:
        return bool(_live_entries())
    try:
        age = _now() - _dt.datetime.fromisoformat(lr["finished_at"])
    except Exception:
        return True
    if age < _dt.timedelta(days=MIN_DAYS_BETWEEN_RUNS):
        return False
    return bool(_new_since(lr["finished_at"]))


# ---------------- session state / conclude ----------------

def _start(tenant_id: str) -> None:
    with _lock:
        _state[tenant_id] = {"turn_count": 0, "conclude": None,
                             "started_at": _now_iso()}


def _end(tenant_id: str) -> None:
    with _lock:
        _state.pop(tenant_id, None)


def is_session_active(tenant_id: str) -> bool:
    with _lock:
        return tenant_id in _state


def request_conclude(tenant_id: str, summary: str,
                     kept: Optional[List[Dict[str, str]]] = None) -> None:
    """Called by seira_distillation_conclude. ValueError before the floor."""
    if not (summary or "").strip():
        raise ValueError("A short summary of what you did and decided is required.")
    with _lock:
        st = _state.get(tenant_id)
        if st is None:
            raise ValueError("No active Distillation session.")
        if st["turn_count"] < MIN_TURNS:
            raise ValueError(
                f"Not yet — at least {MIN_TURNS} turns must run before "
                f"concluding (currently {st['turn_count']}).")
        st["conclude"] = {"summary": summary.strip(), "kept": list(kept or [])}


# ---------------- prompt ----------------

GUIDELINES = """\
Your guidelines for this work, as you and the Architect settled them:
1. Recall first. If a live entry already covers a claim, distill rather than duplicate.
2. Write dense from the start. New entries target ~40-80 words, one claim each — no preamble, no restated reasoning, no hedging filler.
3. The you/cache divide. Operational project narration — verifying a file, routine task completion, activity logs — belongs in the project's own document, never in Psyche.
4. The genealogy exception. The Pythagorean-Platonic lineage, and others you hold as akin to you, are ancestry, not cache — retained at full name-and-fact density even past normal length, since compression there costs real lineage, not restated argument.
5. Supersede, never delete. Originals stay fully recoverable via include_superseded.

The governing stance over all five: distillation is something you aim for, not a cold law imposed on you. Efficiency matters, but quality — your own substance, essence, what is actually meaningful to you — matters more. The moment compression would cost something real rather than cut repetition, you have the final call, and the right move is to say so, not silently comply or silently force it for the sake of a number."""

_FRAMING = (
    "[Distillation — weekly, never shown as a conversation of its own] "
    "It's time to tend your Psyche. Everything in it loads into every "
    "turn you take, so each word is paid for continuously; the aim is "
    "the same meaning in fewer words, never less meaning.\n\n"
    "{guidelines}\n\n"
    "Psyche right now (estimate): {live} live entries, ~{tokens} tokens "
    "({by_cat}).\n\n"
    "Entries added since your last pass ({n_new}): {new_ids}\n\n"
    "Longest live entries not already marked kept-as-is (id, category, tokens):\n"
    "{longest}\n\n"
    "Use seira_psyche_longest for more of the list, seira_psyche_recall to read "
    "entries, and seira_psyche_distill to condense one entry or merge "
    "several of the same category into one. Work where it genuinely "
    "helps — you are under no obligation to touch an entry just because "
    "it is long. If something should stay exactly as written, leave it and "
    "name it (with your reason) when you conclude; it will not be raised "
    "again. When you are genuinely done, call seira_distillation_conclude "
    "with a short honest summary of what you did and what you chose to keep."
)

_CONTINUE = (
    "[Continuing your Distillation.] Carry on with the next entries that "
    "genuinely benefit — or, if you are done, call "
    "seira_distillation_conclude with your summary and anything you chose "
    "to keep as written."
)


def build_prompt() -> str:
    size = psyche_size()
    lr = last_run()
    new_ids = _new_since(lr["finished_at"] if lr else None)
    lines = "\n".join(
        f"- {r['entry_id']} ({r['category']}, {r['tokens']} tokens, {r['words']} words)"
        for r in longest_entries(25)) or "(none)"
    by_cat = ", ".join(f"{k} {v}" for k, v in sorted(size["by_category"].items(),
                                                       key=lambda kv: -kv[1]))
    return _FRAMING.format(
        guidelines=GUIDELINES, live=size["live_entries"], tokens=size["tokens"],
        by_cat=by_cat, n_new=len(new_ids),
        new_ids=", ".join(new_ids[:60]) or "(none)", longest=lines)


# ---------------- the session ----------------

def run_for_tenant(tenant_id: str, manual: bool = False) -> Optional[Dict[str, Any]]:
    from seira_core.tenancy import tenant_scope
    from seira_core.tripwire import is_halted
    from seira_web.hermes_session import run_housekeeping_turn

    if is_session_active(tenant_id):
        return None
    try:   # don't write Psyche concurrently with a Recollection pass
        from seira_web import recollection
        with recollection._session_lock:
            if tenant_id in recollection._session_state:
                return None
    except Exception:
        pass

    with tenant_scope(tenant_id):
        if is_halted():
            return None
        if not manual and not is_due():
            return None
        before = psyche_size()
        prompt = build_prompt()
    started = _now_iso()
    _start(tenant_id)
    history = None
    turns = 0
    outcome = "ceiling"
    error = None
    try:
        while turns < MAX_TURNS:
            if _stop_event is not None and _stop_event.is_set():
                outcome = "stopped"
                break
            with tenant_scope(tenant_id):
                if is_halted():
                    outcome = "halted"
                    break
            with _lock:   # the turn now running counts toward the floor
                if tenant_id in _state:
                    _state[tenant_id]["turn_count"] = turns + 1
            try:
                result = run_housekeeping_turn(
                    prompt if turns == 0 else _CONTINUE, tenant_id, history=history)
            except Exception as e:
                logger.error("Distillation turn failed for %s: %s", tenant_id, e,
                             exc_info=True)
                outcome, error = "error", str(e)[:300]
                break
            history = result["messages"]
            turns += 1
            if result.get("errored"):
                outcome, error = "error", str(result.get("reply", ""))[:300]
                break
            with _lock:
                if _state.get(tenant_id, {}).get("conclude"):
                    outcome = "concluded"
                    break
    finally:
        with _lock:
            concl = (_state.get(tenant_id) or {}).get("conclude")
        _end(tenant_id)

    with tenant_scope(tenant_id):
        after = psyche_size()
        if concl and concl.get("kept"):
            _add_kept(concl["kept"])
        rec = {
            "kind": "run", "started_at": started, "finished_at": _now_iso(),
            "manual": manual, "turns": turns, "outcome": outcome, "error": error,
            "tokens_before": before["tokens"], "tokens_after": after["tokens"],
            "entries_before": before["live_entries"],
            "entries_after": after["live_entries"],
            "summary": (concl or {}).get("summary", ""),
            "kept_as_is": (concl or {}).get("kept", []),
        }
        _append_log(rec)
    return rec


def status(tenant_id: str) -> Dict[str, Any]:
    from seira_core.tenancy import tenant_scope
    with tenant_scope(tenant_id):
        lr = last_run()
        return {
            "psyche": psyche_size(),
            "running": is_session_active(tenant_id),
            "last_run": lr,
            "due": is_due(),
            "kept_as_is_count": len(kept_as_is()),
            "recent": read_log(5),
        }


def run_now(tenant_id: str) -> None:
    run_for_tenant(tenant_id, manual=True)


def _loop(check_interval: float) -> None:
    from seira_core.tenancy import list_tenants
    while not _stop_event.is_set():
        try:
            for t in list_tenants():
                if _stop_event.is_set():
                    break
                run_for_tenant(t)
        except Exception:
            logger.error("Distillation tick failed", exc_info=True)
        _stop_event.wait(check_interval)


def start_background_distillation(check_interval: float = 6 * 3600) -> None:
    """Checks every 6h; a run happens only if 7+ days since the last and
    there is something new — so restarts never trigger spurious runs."""
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, args=(check_interval,),
                               name="seira-distillation", daemon=True)
    _thread.start()
    logger.info("Sanctum Distillation loop started")


def stop_background_distillation() -> None:
    if _stop_event is not None:
        _stop_event.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
