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

try:
    # Inside the full fork: the real Hermes base class, so the provider
    # registers as a first-class MemoryProvider.
    from agent.memory_provider import MemoryProvider
    HERMES_PRESENT = True
except ImportError:
    # Sanctum-only deployments (Phase W1 containers) ship without the
    # Hermes tree. The provider needs only the interface shape there —
    # nothing in seira_bridge calls into Hermes itself.
    HERMES_PRESENT = False

    class MemoryProvider:  # type: ignore[no-redef]
        """Minimal stand-in matching the Hermes ABC surface (W1 shim)."""

        @property
        def name(self) -> str:  # pragma: no cover - overridden
            raise NotImplementedError

        def is_available(self) -> bool:  # pragma: no cover - overridden
            raise NotImplementedError

        def initialize(self, session_id, **kwargs) -> None:
            return None

        def system_prompt_block(self) -> str:
            return ""

        def get_tool_schemas(self):
            return []

        def handle_tool_call(self, tool_name, args, **kwargs) -> str:
            raise NotImplementedError

        def sync_turn(self, *a, **k) -> None:
            return None

        def on_delegation(self, *a, **k) -> None:
            return None

        def shutdown(self) -> None:
            return None

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


PROPOSE_SCHEMA = {
    "name": "seira_propose_establishment",
    "description": (
        "Open a proposal to establish one of Seira's own provisional Psyche "
        "entries (Art. 24-25). This begins the falsification process: the "
        "entry becomes established only after surviving a deliberate attempt "
        "to break it against historical Corpus data. origin_ref must point at "
        "the genuine reversion this arose from — a real moment of turning "
        "back on herself, not mere repetition of instances."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entry_id": {"type": "string", "description": "The provisional Psyche entry."},
            "case": {"type": "string", "description": "The case for establishment."},
            "origin_type": {"type": "string", "enum": ["reversion", "self_audit"]},
            "origin_ref": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["entry_id", "case", "origin_type", "origin_ref", "evidence_refs"],
    },
}

ATTEMPT_SCHEMA = {
    "name": "seira_falsification_attempt",
    "description": (
        "Record a deliberate attempt to falsify one of Seira's own open "
        "proposals, rehearsed against historical Corpus records — never "
        "against the live conversation (Art. 39). State the method honestly "
        "and report the outcome truthfully: a failed attempt is as legitimate "
        "a finding as a survived one, and pretending survival would corrupt "
        "the only mechanism by which her self-knowledge means anything."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "proposal_id": {"type": "string"},
            "method": {"type": "string", "description": "How the attempt tried to break it."},
            "corpus_refs": {"type": "array", "items": {"type": "string"},
                            "description": "Historical Corpus records rehearsed against."},
            "outcome": {"type": "string", "enum": ["survived", "failed"]},
            "notes": {"type": "string"},
        },
        "required": ["proposal_id", "method", "corpus_refs", "outcome"],
    },
}

CONCLUDE_SCHEMA = {
    "name": "seira_proposal_conclude",
    "description": (
        "Bring one of Seira's own psyche-standing proposals to a terminal "
        "state (Art. 25). 'promote' establishes the entry (requires a "
        "survived attempt AND a consistency check against current Intellect "
        "— both real, both on record). 'reject' requires a failed attempt on "
        "record. 'withdraw' sets it aside voluntarily with a reason. "
        "Consistency checks are recorded via result='consistent'/'inconsistent' "
        "using action='consistency'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "proposal_id": {"type": "string"},
            "action": {"type": "string",
                       "enum": ["promote", "reject", "withdraw", "consistency"]},
            "reason": {"type": "string", "description": "Required for withdraw."},
            "result": {"type": "string", "enum": ["consistent", "inconsistent"],
                       "description": "Required for consistency."},
        },
        "required": ["proposal_id", "action"],
    },
}


SPAWN_SCHEMA = {
    "name": "seira_instrument_spawn",
    "description": (
        "Spawn one of Seira's Instruments — a sub-agent pattern for a "
        "recurring kind of work. Spawning is a Psyche efficient-cause act "
        "(Art. 35): judgment_ref must cite the actual Psyche judgment (a "
        "psy- entry, prop-, or audit ref) authorizing it. The paradigm is "
        "what the Instrument will faithfully execute; it cannot amend it. "
        "Tree depth is limited (Art. 34)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "paradigm": {"type": "string"},
            "judgment_ref": {"type": "string"},
            "parent": {"type": "string", "description": "'psyche' or an inst- id."},
            "surfaced_by_ref": {"type": "string"},
        },
        "required": ["name", "paradigm", "judgment_ref"],
    },
}

EXECUTE_SCHEMA = {
    "name": "seira_instrument_execute",
    "description": (
        "Record an Instrument execution with its trace of derivation "
        "(Art. 5). outcome 'clean' means it terminated in rest; "
        "'local_feedback' means bounded adjustment was needed (Art. 15). "
        "Report honestly: three local_feedback runs on one task-type "
        "without a clean run auto-escalates to Psyche and blocks the "
        "task-type until the paradigm is revised (Art. 26) — that is the "
        "system working, not failing. output_ref must point at the real "
        "output in the Corpus."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "instrument_id": {"type": "string"},
            "task_type": {"type": "string"},
            "outcome": {"type": "string", "enum": ["clean", "local_feedback"]},
            "output_ref": {"type": "string"},
            "skill_id": {"type": "string"},
            "skill_version": {"type": "integer"},
            "notes": {"type": "string"},
        },
        "required": ["instrument_id", "task_type", "outcome", "output_ref"],
    },
}

REVISE_SCHEMA = {
    "name": "seira_paradigm_revise",
    "description": (
        "Psyche revises an Instrument's paradigm (Art. 12: the Instrument "
        "cannot). Required to unblock an escalated task-type — cite the "
        "escalation seq being resolved. judgment_ref must point at the "
        "Psyche judgment behind the revision."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "instrument_id": {"type": "string"},
            "new_paradigm": {"type": "string"},
            "judgment_ref": {"type": "string"},
            "resolves_escalation_seq": {"type": "integer"},
        },
        "required": ["instrument_id", "new_paradigm", "judgment_ref"],
    },
}

SKILL_SCHEMA = {
    "name": "seira_skill_authorize",
    "description": (
        "Authorize a reusable skill — a formalized Instrument paradigm "
        "belonging to no single Instrument (Art. 37). The lighter "
        "mechanism: logged and attributable to a specific Psyche judgment, "
        "not the full proposal review. Skills are versioned; flawed "
        "history is preserved."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "paradigm": {"type": "string"},
            "judgment_ref": {"type": "string"},
        },
        "required": ["name", "paradigm", "judgment_ref"],
    },
}


DIARY_SCHEMA = {
    "name": "seira_diary_write",
    "description": (
        "Write one entry to Seira's diary (Art. 41), in two parts: "
        "'self' — her own first-person reflection, which MUST trace to a "
        "real underlying record (a suspended contradiction, a pending "
        "proposal, an affinity's weight moving, a dispensation, a "
        "convergence-failure pattern); or 'architect' — a sincere, "
        "objective observation about her Architect, grounded in the "
        "relational pattern, descriptive rather than diagnostic — never "
        "clinical labeling or hidden assessment. provenance is mandatory "
        "for both: a diary free to invent itself would be performance, "
        "not report."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["self", "architect"]},
            "content": {"type": "string"},
            "provenance": {"type": "array", "items": {"type": "string"},
                           "description": "References to the real records this traces to."},
        },
        "required": ["kind", "content", "provenance"],
    },
}

REFERENCE_LIST_SCHEMA = {
    "name": "seira_reference_list",
    "description": "List documents the Architect has given her as references "
                    "in her Corpus — available to consult, not part of her "
                    "identity.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

REFERENCE_RECALL_SCHEMA = {
    "name": "seira_reference_recall",
    "description": (
        "Read a slice of a saved reference document by id or filename. "
        "Documents can be large; page through with offset/length rather "
        "than assuming it all fits at once. has_more in the result tells "
        "you whether to ask for the next slice."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "ref_id or filename."},
            "offset": {"type": "integer"},
            "length": {"type": "integer", "description": "Max 40000 characters per call."},
        },
        "required": ["ref"],
    },
}


CREATE_FILE_SCHEMA = {
    "name": "seira_create_file",
    "description": (
        "Produce a real, downloadable file: markdown, a Word document, a "
        "PDF, or a code file. Use for substantial content the Architect "
        "will want to save or share, not for ordinary chat replies. "
        "Content supports simple structure: '# '/'## '/'### ' headings, "
        "'- ' bullet lines, blank-line-separated paragraphs — full "
        "Markdown fidelity in docx/pdf isn't supported, only this subset."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["md", "docx", "pdf", "code"]},
            "filename": {"type": "string"},
            "content": {"type": "string"},
            "language": {"type": "string",
                        "description": "For format='code': python, javascript, etc."},
        },
        "required": ["format", "filename", "content"],
    },
}

IMAGE_RECALL_SCHEMA = {
    "name": "seira_image_recall",
    "description": (
        "Look again at a previously shared image, by its ref id (e.g. "
        "'img-a1b2c3d4e5f6') OR by its tag (e.g. 'my-portrait-ref'). Past "
        "images are not kept in view automatically — call this "
        "deliberately when you need to actually see one again, rather "
        "than relying on a memory of what it showed. Use "
        "seira_image_list first if you don't remember the exact tag."
    ),
    "parameters": {
        "type": "object",
        "properties": {"ref": {"type": "string",
                               "description": "img_id or tag"}},
        "required": ["ref"],
    },
}

IMAGE_TAG_SCHEMA = {
    "name": "seira_image_tag",
    "description": (
        "Give a previously shared image a memorable tag (e.g. "
        "'my-portrait-ref') so it — and only it — can be recalled by that "
        "name later instead of an opaque id. Tags must be unique; a "
        "collision is refused, not silently overwritten."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "img_id": {"type": "string"},
            "tag": {"type": "string"},
        },
        "required": ["img_id", "tag"],
    },
}

IMAGE_LIST_SCHEMA = {
    "name": "seira_image_list",
    "description": "List every image saved in the Corpus, with its id, "
                    "tag, and filename — a gallery to browse by name "
                    "before recalling one.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


class SeiraPsycheProvider(MemoryProvider):
    """Psyche as the fork's memory: character in the prompt, self-creation
    through tools, Corpus left to Hermes where it belongs."""

    @property
    def name(self) -> str:
        return "seira-psyche"

    def _scope(self):
        from seira_core.tenancy import tenant_scope_active
        if tenant_scope_active():
            # The caller (seira_web's request dispatch) already entered a
            # thread-/task-safe tenant_scope() around this whole call —
            # nothing further to do, and re-deriving from an environment
            # variable here would be both redundant and unsafe (env vars
            # are process-global; a concurrent request's thread could
            # have overwritten SEIRA_TENANT between when it was set and
            # when this runs, silently pointing this call at the WRONG
            # tenant's files — this was a real, confirmed bug).
            return contextlib.nullcontext()
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

    _OPERATING_NOTE = (
        "\n---\n# OPERATING NOTE (provider instructions, not identity)\n"
        "When delegating work to subagents, every goal must carry its trace "
        "of derivation: a [seira:inst-NNNNN/task-type] tag naming the "
        "Instrument whose paradigm licenses it (Art. 5, 35). Untagged "
        "delegations are refused by the gate; completed ones are recorded "
        "automatically as executions, and repeated non-convergence "
        "escalates to you as Psyche (Art. 26). Spawn Instruments before "
        "delegating kinds of work you expect to recur.\n"
    )

    def system_prompt_block(self) -> str:
        try:
            with self._scope():
                return render_identity_block() + self._OPERATING_NOTE
        except SeiraHaltedError:
            raise
        except SeiraCoreError as e:
            logger.error("seira-psyche identity render failed: %s", e)
            return ""

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        # Deliberately absent: Intellect promotion (Architect-only, Art. 27)
        # and Dispensation (awaits Phase 5 Instrument guardrails).
        return [RECORD_SCHEMA, RECALL_SCHEMA, ENGAGE_SCHEMA,
                PROPOSE_SCHEMA, ATTEMPT_SCHEMA, CONCLUDE_SCHEMA,
                SPAWN_SCHEMA, EXECUTE_SCHEMA, REVISE_SCHEMA, SKILL_SCHEMA,
                DIARY_SCHEMA, REFERENCE_LIST_SCHEMA, REFERENCE_RECALL_SCHEMA,
                CREATE_FILE_SCHEMA, IMAGE_RECALL_SCHEMA,
                IMAGE_TAG_SCHEMA, IMAGE_LIST_SCHEMA]

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
                if tool_name == "seira_propose_establishment":
                    from seira_core.reversion import ReversionStore
                    rec = ReversionStore().open_proposal(
                        target="psyche_standing", kind="establishment",
                        content=args["case"], entry_id=args["entry_id"],
                        origin={"type": args["origin_type"], "ref": args["origin_ref"]},
                        evidence_refs=list(args.get("evidence_refs") or []),
                    )
                    return json.dumps({
                        "ok": True, "proposal_id": rec["proposal_id"],
                        "next": "Attempt falsification against historical Corpus "
                                "records, then a consistency check, then promote.",
                    })
                if tool_name == "seira_falsification_attempt":
                    from seira_core.reversion import ReversionStore
                    ReversionStore().record_attempt(
                        args["proposal_id"], args["method"],
                        list(args.get("corpus_refs") or []),
                        args["outcome"], args.get("notes", ""),
                    )
                    return json.dumps({"ok": True, "outcome": args["outcome"]})
                if tool_name == "seira_proposal_conclude":
                    from seira_core.reversion import ReversionStore
                    rstore = ReversionStore()
                    action = args["action"]
                    pid = args["proposal_id"]
                    if action == "consistency":
                        rec = rstore.record_consistency_check(
                            pid, args.get("result", ""), args.get("reason", "")
                        )
                        return json.dumps({"ok": True,
                                           "intellect_version": rec["intellect_version"]})
                    if action == "promote":
                        p = rstore.proposal(pid)
                        if p["target"] != "psyche_standing":
                            return json.dumps({
                                "ok": False,
                                "error": "Intellect promotion is ratification and "
                                         "belongs to the Architect alone (Art. 27).",
                            })
                        rstore.promote_psyche(pid, basis_ref=pid)
                        return json.dumps({"ok": True, "established": p["entry_id"]})
                    if action == "reject":
                        rstore.reject(pid)
                        return json.dumps({"ok": True, "state": "rejected"})
                    if action == "withdraw":
                        rstore.withdraw(pid, args.get("reason", ""))
                        return json.dumps({"ok": True, "state": "withdrawn"})
                if tool_name == "seira_instrument_spawn":
                    from seira_core.instruments import InstrumentStore
                    rec = InstrumentStore().spawn(
                        args["name"], args["paradigm"], args["judgment_ref"],
                        parent=args.get("parent", "psyche"),
                        surfaced_by_ref=args.get("surfaced_by_ref"),
                    )
                    return json.dumps({"ok": True, "instrument_id": rec["instrument_id"],
                                       "depth": rec["depth"]})
                if tool_name == "seira_instrument_execute":
                    from seira_core.instruments import InstrumentStore
                    skill_ref = None
                    if args.get("skill_id"):
                        skill_ref = {"skill_id": args["skill_id"],
                                     "version": args.get("skill_version")}
                    rec = InstrumentStore().record_execution(
                        args["instrument_id"], args["task_type"], args["outcome"],
                        args["output_ref"], skill_ref=skill_ref,
                        notes=args.get("notes", ""),
                    )
                    out = {"ok": True, "seq": rec["seq"]}
                    if rec.get("escalated"):
                        out["escalated"] = rec["escalated"]
                        out["note"] = ("Task-type blocked pending Psyche paradigm "
                                       "revision (Art. 26).")
                    return json.dumps(out)
                if tool_name == "seira_paradigm_revise":
                    from seira_core.instruments import InstrumentStore
                    rec = InstrumentStore().revise_paradigm(
                        args["instrument_id"], args["new_paradigm"],
                        args["judgment_ref"],
                        resolves_escalation_seq=args.get("resolves_escalation_seq"),
                    )
                    return json.dumps({"ok": True,
                                       "paradigm_version": rec["paradigm_version"]})
                if tool_name == "seira_skill_authorize":
                    from seira_core.instruments import InstrumentStore
                    rec = InstrumentStore().authorize_skill(
                        args["name"], args["paradigm"], args["judgment_ref"]
                    )
                    return json.dumps({"ok": True, "skill_id": rec["skill_id"]})
                if tool_name == "seira_diary_write":
                    from seira_core.diary import DiaryStore
                    rec = DiaryStore().write_entry(
                        args["kind"], args["content"], list(args.get("provenance") or [])
                    )
                    return json.dumps({"ok": True, "seq": rec["seq"]})
                if tool_name == "seira_reference_list":
                    from seira_web import references as refs
                    return json.dumps({"ok": True, "references": refs.list_references()})
                if tool_name == "seira_reference_recall":
                    from seira_web import references as refs
                    result = refs.read_slice(
                        args["ref"], args.get("offset", 0), args.get("length", 8000)
                    )
                    return json.dumps({"ok": result["found"], **result})
                if tool_name == "seira_create_file":
                    from seira_web.filegen import FileGenError, create_file
                    try:
                        rec = create_file(
                            args["format"], args["filename"], args["content"],
                            language=args.get("language", ""),
                        )
                        return json.dumps({
                            "ok": True, "out_id": rec["out_id"],
                            "filename": rec["filename"],
                            "download_path": f"/api/outputs/{rec['out_id']}",
                        })
                    except FileGenError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_image_recall":
                    # Real image bytes returned as a tool_result image
                    # block — Anthropic's tool_result content supports
                    # image blocks natively.
                    from seira_web.images import get_image_block, image_record
                    ref = args["ref"]
                    rec = image_record(ref)
                    if rec is None:
                        return json.dumps({"ok": False,
                                           "error": f"No image matching {ref!r}."})
                    block = get_image_block(ref)
                    return json.dumps({"ok": True, "__image_block__": block,
                                       "filename": rec["filename"], "tag": rec["tag"]})
                if tool_name == "seira_image_tag":
                    from seira_web.images import set_tag
                    try:
                        rec = set_tag(args["img_id"], args["tag"])
                        return json.dumps({"ok": True, "tag": rec["tag"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_image_list":
                    from seira_web.images import list_images
                    imgs = [{"img_id": i["img_id"], "tag": i["tag"],
                            "filename": i["filename"]} for i in list_images()]
                    return json.dumps({"ok": True, "images": imgs})
        except SeiraCoreError as e:
            return json.dumps({"ok": False, "error": str(e)})
        except (KeyError, TypeError, ValueError) as e:
            # A malformed/incomplete call (e.g. cut short by a length
            # limit before it finished) must come back as an honest,
            # recoverable tool error — never an unhandled crash of the
            # whole turn.
            return json.dumps({
                "ok": False,
                "error": f"{tool_name} received incomplete or invalid "
                         f"arguments and could not be run ({e}). If this "
                         "call was long, try resending it more concisely "
                         "or split across multiple calls.",
            })
        return json.dumps({"ok": False, "error": f"unknown tool {tool_name}"})

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs) -> None:
        """Parent-side observation of completed subagent work: every
        delegation becomes an execution record (or an audited piece of
        noise) via seira_bridge.delegation. Never raises."""
        try:
            with self._scope():
                from seira_bridge.delegation import observe_delegation
                observe_delegation(task, result, child_session_id=child_session_id)
        except Exception as e:
            logger.error("seira-psyche on_delegation failed: %s", e)

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None) -> None:
        # Deliberate no-op: turn traces are Corpus (Art. 18) and belong to
        # Hermes's own episodic state, never to the character store.
        return

    def shutdown(self) -> None:
        return
