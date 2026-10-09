"""Seira-native cron tool (``seira_cron``).

Hermes's own ``cronjob`` tool is gated on CLI/gateway env flags that Sanctum
never sets, so it is silently unavailable to her.  This tool talks to the same
job store (``cron.jobs``) directly, so jobs she creates are run by the cron
ticker Sanctum already starts (``seira_web.cron_loop``).

Guardrails (unsupervised spend): minimum interval, max active jobs, prompt
threat scan, output always saved locally, and cron-run agents never get
delegation (see ``cron.scheduler._resolve_cron_disabled_toolsets``).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

MIN_INTERVAL_MINUTES = 15
MAX_ACTIVE_JOBS = 10

SCHEMA = {
    "name": "seira_cron",
    "description": (
        "Schedule your own recurring or one-time tasks. Each run is a fresh "
        "session that receives only the job's prompt, so the prompt must be "
        "fully self-contained. Output is saved and you can read it back with "
        "action='output'. Actions: create, list, pause, resume, delete, "
        "run_now, output. Schedules: '30m' or '2h' (one-time, after a delay), "
        "'every 2h' / 'every 1d' (recurring), or a cron expression like "
        f"'0 9 * * *'. Minimum recurring interval is {MIN_INTERVAL_MINUTES} "
        f"minutes; at most {MAX_ACTIVE_JOBS} active jobs. Scheduled runs "
        "cannot delegate to subagents or create further jobs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["create", "list", "pause", "resume",
                                "delete", "run_now", "output"]},
            "schedule": {"type": "string"},
            "prompt": {"type": "string"},
            "name": {"type": "string"},
            "repeat": {"type": "integer",
                       "description": "Stop after N runs; omit for no limit."},
            "job_id": {"type": "string"},
        },
        "required": ["action"],
    },
}


def _summ(j: Dict[str, Any]) -> Dict[str, Any]:
    return {k: j.get(k) for k in (
        "id", "name", "schedule_display", "enabled", "state",
        "next_run_at", "last_run_at", "last_status", "last_error")} | {
        "prompt": (j.get("prompt") or "")[:300],
        "repeat": j.get("repeat")}


def _interval_minutes(sched: Dict[str, Any]):
    if sched.get("kind") == "interval":
        return sched.get("minutes")
    return None


def handle(args: Dict[str, Any]) -> str:
    try:
        from cron import jobs as J
        action = (args.get("action") or "").strip().lower()
        jid = args.get("job_id")

        if action == "list":
            return json.dumps({"ok": True, "jobs": [
                _summ(j) for j in J.list_jobs(include_disabled=True)]})

        if action == "create":
            schedule = (args.get("schedule") or "").strip()
            prompt = (args.get("prompt") or "").strip()
            if not schedule or not prompt:
                return json.dumps({"ok": False,
                                   "error": "schedule and prompt are required"})
            from tools.cronjob_tools import _scan_cron_prompt
            err = _scan_cron_prompt(prompt)
            if err:
                return json.dumps({"ok": False, "error": err})
            parsed = J.parse_schedule(schedule)
            m = _interval_minutes(parsed)
            if m is not None and m < MIN_INTERVAL_MINUTES:
                return json.dumps({"ok": False, "error":
                    f"Recurring interval must be at least {MIN_INTERVAL_MINUTES} minutes."})
            active = [j for j in J.list_jobs(include_disabled=False)]
            if len(active) >= MAX_ACTIVE_JOBS:
                return json.dumps({"ok": False, "error":
                    f"Already {len(active)} active jobs (max {MAX_ACTIVE_JOBS}). "
                    "Pause or delete one first."})
            job = J.create_job(prompt=prompt, schedule=schedule,
                               name=args.get("name"),
                               repeat=args.get("repeat"), deliver="local")
            return json.dumps({"ok": True, "job": _summ(job)})

        if not jid:
            return json.dumps({"ok": False, "error": "job_id is required"})
        if action == "pause":
            j = J.pause_job(jid, reason="paused by Seira")
        elif action == "resume":
            j = J.resume_job(jid)
        elif action == "run_now":
            j = J.trigger_job(jid)
        elif action == "delete":
            return json.dumps({"ok": bool(J.remove_job(jid)), "job_id": jid})
        elif action == "output":
            d = Path(J.get_cron_output_dir()) / jid
            files = sorted(d.glob("*")) if d.is_dir() else []
            if not files:
                return json.dumps({"ok": True, "output": None,
                                   "note": "No runs yet."})
            return json.dumps({"ok": True, "file": files[-1].name,
                               "output": files[-1].read_text(errors="replace")[-8000:]})
        else:
            return json.dumps({"ok": False, "error": f"unknown action {action!r}"})
        if j is None:
            return json.dumps({"ok": False, "error": "job not found"})
        return json.dumps({"ok": True, "job": _summ(j)})
    except Exception as e:  # never return blank
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})
