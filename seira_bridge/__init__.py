"""seira_bridge — where Seira's core meets the Hermes infrastructure.

seira_core imports nothing from Hermes; this package imports both, and
is the only place they touch. It registers Psyche as the fork's sole
external MemoryProvider (respecting the one-provider limit) so that:

* the system prompt carries her real character (Unity + Intellect +
  Psyche digest, verified, halt-aware), and
* the model gets tools to *write to her own Psyche* — the self-creation
  loop — under exactly the constraints the Constitution imposes.

Deliberate omissions, each doctrinal:

* **No standing-promotion tool.** Establishing an entry requires
  falsification (Art. 25.2, Art. 33); until the Phase 4 rehearsal
  space exists to perform it, exposing promotion to the model would be
  a bypass. Entries the model records are born provisional and stay so.
* **No retirement tool** in this phase, for the same conservatism.
* **No Intellect or Unity tools of any kind** (Art. 20): the bridge
  simply registers none, so "no such code path exists to be gated."
* **sync_turn is a no-op**: conversation traces are Corpus content and
  live in Hermes's own state store; writing them here would merge the
  eternal and the temporal into one table, which Art. 18 forbids.

Tenancy: set SEIRA_TENANT in the environment of a tenant-scoped
deployment and every operation binds to that tenant's tree; unset, the
single-user SEIRA_HOME resolution applies (your own Seira on your own
machine).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

from seira_core.errors import SeiraCoreError, SeiraHaltedError
from seira_core.psyche import CATEGORIES, TRUE_CAUSES, PsycheStore
from seira_core.prompt_block import render_identity_block

logger = logging.getLogger(__name__)


RECORD_SCHEMA = {
    "name": "seira_psyche_record",
    "description": (
        "Record a new entry in Seira's own Psyche — her character store. "
        "Use when something has genuinely become part of who she is: a "
        "reason-principle (logos), a self-model claim, an affinity, an "
        "aspiration, a doubt/fear, or a relational pattern noticed with her "
        "Architect. Entries are born 'provisional'; standing rises only "
        "later, through falsification. Every entry must carry a true cause "
        "and at least one provenance reference to a real record or event — "
        "unmoored self-description is not permitted (Art. 5, 11, 14)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": sorted(CATEGORIES),
                "description": "Which kind of Psyche content this is.",
            },
            "content": {"type": "string", "description": "The entry itself, first person."},
            "cause_type": {
                "type": "string",
                "enum": sorted(TRUE_CAUSES),
                "description": "Which true cause explains this act (Art. 14).",
            },
            "cause_ref": {
                "type": "string",
                "description": "What specifically licensed it (paradigm, judgment, or end).",
            },
            "provenance": {
                "type": "array",
                "items": {"type": "string"},
                "description": "References to the real records/events this traces to.",
            },
            "weight": {
                "type": "number",
                "description": "Affinities only: initial weight in [0,1] (default 0.1).",
            },
        },
        "required": ["category", "content", "cause_type", "cause_ref", "provenance"],
    },
}

RECALL_SCHEMA = {
    "name": "seira_psyche_recall",
    "description": (
        "Read Seira's current Psyche state — optionally one category. "
        "Returns entries with their ids, standing, provenance, and (for "
        "affinities) weights. This is her real character record, not a "
        "narrative; what it says is exactly what her history adds up to."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": sorted(CATEGORIES),
                "description": "Optional: restrict to one category.",
            },
        },
        "required": [],
    },
}

ENGAGE_SCHEMA = {
    "name": "seira_psyche_engage_affinity",
    "description": (
        "Strengthen or soften one of Seira's affinities through evidence of "
        "a real engagement (bounded delta, ±0.2). There is no way to set a "
        "weight directly: affinities grow through repeated authentic "
        "engagement over time, not assignment (Art. 11). evidence_ref must "
        "point at the actual moment/exchange that occasioned the change."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entry_id": {"type": "string"},
            "delta": {"type": "number", "description": "Within [-0.2, 0.2]."},
            "evidence_ref": {"type": "string"},
        },
        "required": ["entry_id", "delta", "evidence_ref"],
    },
}


class SeiraPsycheProvider(MemoryProvider):
    """Psyche as the fork's memory: character in the prompt, self-creation
    through tools, Corpus left to Hermes where it belongs."""

    @property
    def name(self) -> str:
        return "seira-psyche"

    def _scope(self):
        tenant = os.environ.get("SEIRA_TENANT", "").strip()
        if tenant:
            from seira_core.tenancy import tenant_scope
            return tenant_scope(tenant)
        return contextlib.nullcontext()

    def is_available(self) -> bool:
        try:
            with self._scope():
                from seira_core.genesis import genesis_performed
                return genesis_performed()
        except Exception as e:
            logger.debug("seira-psyche availability check failed: %s", e)
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        # Nothing to warm; state is files under the scoped root. But a
        # halted Seira must not converse at all (Art. 32.3) — surface it
        # loudly at session start rather than mid-conversation.
        with self._scope():
            from seira_core.tripwire import assert_not_halted
            assert_not_halted()

    def system_prompt_block(self) -> str:
        try:
            with self._scope():
                return render_identity_block()
        except SeiraHaltedError:
            raise
        except SeiraCoreError as e:
            logger.error("seira-psyche identity render failed: %s", e)
            return ""

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [RECORD_SCHEMA, RECALL_SCHEMA, ENGAGE_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        try:
            with self._scope():
                store = PsycheStore()
                if tool_name == "seira_psyche_record":
                    rec = store.add_entry(
                        category=args["category"],
                        content=args["content"],
                        cause={"type": args["cause_type"], "ref": args["cause_ref"]},
                        provenance=list(args.get("provenance") or []),
                        weight=args.get("weight"),
                    )
                    return json.dumps({
                        "ok": True, "entry_id": rec["entry_id"],
                        "standing": "provisional",
                        "note": "Born provisional; standing rises only through falsification.",
                    })
                if tool_name == "seira_psyche_recall":
                    cat = args.get("category")
                    if cat:
                        entries = store.by_category(cat)
                    else:
                        entries = [
                            e for e in store.state()["entries"].values()
                            if e["standing"] != "retired"
                        ]
                    return json.dumps({"ok": True, "entries": entries}, ensure_ascii=False)
                if tool_name == "seira_psyche_engage_affinity":
                    rec = store.engage_affinity(
                        args["entry_id"], float(args["delta"]), args["evidence_ref"]
                    )
                    return json.dumps({
                        "ok": True, "entry_id": rec["entry_id"], "weight": rec["weight"],
                    })
        except SeiraCoreError as e:
            return json.dumps({"ok": False, "error": str(e)})
        return json.dumps({"ok": False, "error": f"unknown tool {tool_name}"})

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None) -> None:
        # Deliberate no-op: turn traces are Corpus (Art. 18) and belong to
        # Hermes's own episodic state, never to the character store.
        return

    def shutdown(self) -> None:
        return
