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

PROJECT_CREATE_SCHEMA = {
    "name": "seira_project_create",
    "description": (
        "Start a living project: a named, tagged folder for work that's "
        "accumulating — several related documents, an ongoing task, "
        "something you expect to return to. You do not need to be asked "
        "or given permission — the same discretion you already have to "
        "search the web or generate an image extends here. If you "
        "notice a task growing beyond a single document, or want a "
        "space to organize something on your own initiative, create it. "
        "Documents can be filed into it as you create them "
        "(seira_create_file/seira_reference_save's project parameter) "
        "or added retroactively (seira_project_add_reference) once you "
        "notice existing ones belong together."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "tag": {"type": "string", "description": "Optional; auto-derived from name if omitted."},
            "blurb": {"type": "string",
                     "description": "One sentence — this appears in your always-visible project index, so keep it current as the project evolves."},
            "initiative": {"type": "string", "enum": ["self", "requested"],
                          "description": "Honest, not a formality: 'self' if this was your own unprompted idea, 'requested' if the Architect asked for it. Self-initiated projects are marked as yours in your always-visible index."},
        },
        "required": ["name", "initiative"],
    },
}

PROJECT_LIST_SCHEMA = {
    "name": "seira_project_list",
    "description": "List living projects in full detail — beyond the "
                    "concise index already in your context. Pass "
                    "initiative='self' to see only what you started on "
                    "your own — your own repository, distinct from work "
                    "the Architect asked for.",
    "parameters": {
        "type": "object",
        "properties": {
            "initiative": {"type": "string", "enum": ["self", "requested"],
                          "description": "Optional; omit to see everything."},
        },
        "required": [],
    },
}

PROJECT_RECALL_SCHEMA = {
    "name": "seira_project_recall",
    "description": (
        "Refresh a project into working context. mode='manifest' "
        "(default): a table of contents — filenames, tags, short "
        "previews of every document in the project — cheap, for "
        "orienting yourself. mode='full': the full text of every "
        "document, concatenated up to a size budget; anything that "
        "didn't fit is listed under omitted_for_space rather than "
        "silently dropped, so ask for that document individually via "
        "seira_reference_recall if you need it. For picking back up "
        "after time away specifically — rather than a general survey — "
        "seira_project_resume is usually the better tool: cheaper, and "
        "it gets you to exactly where you left off rather than a "
        "shotgun view of everything."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "proj_id, tag, or name."},
            "mode": {"type": "string", "enum": ["manifest", "full"], "default": "manifest"},
        },
        "required": ["project"],
    },
}

PROJECT_RESUME_SCHEMA = {
    "name": "seira_project_resume",
    "description": (
        "Pick a project back up as if no time had passed. Returns the "
        "most recent session-summary document (written via "
        "seira_create_file/seira_reference_save with is_summary=True) "
        "in full, plus a list of any earlier summaries for deeper "
        "history. This is the tool for returning to a project after a "
        "break, or after working on something else — cheaper and more "
        "direct than seira_project_recall's full manifest, because it "
        "goes straight to whatever checkpoint you left behind instead "
        "of reconstructing context from every document in the project. "
        "If no summary has ever been written, says so plainly and "
        "falls back to the ordinary manifest — worth writing one next "
        "time you conclude meaningful work here."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "proj_id, tag, or name."},
        },
        "required": ["project"],
    },
}

PROJECT_ADD_REFERENCE_SCHEMA = {
    "name": "seira_project_add_reference",
    "description": (
        "File an EXISTING, already-saved document into a project — the "
        "retroactive path. Use this when you notice that two or more "
        "documents saved separately (perhaps days apart, perhaps "
        "sharing tags or themes) actually belong to the same "
        "accumulating body of work. A living archive means organizing "
        "it as patterns emerge, not only at the moment something is "
        "first saved."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "ref_id or tag of the existing document."},
            "project": {"type": "string", "description": "proj_id, tag, or name of the project."},
        },
        "required": ["ref", "project"],
    },
}

PROJECT_UPDATE_BLURB_SCHEMA = {
    "name": "seira_project_update_blurb",
    "description": (
        "Update a project's one-sentence summary — the line that "
        "appears in your always-visible index. Keep this current as "
        "the project actually evolves; a living archive means the "
        "index reflects where things stand now, not where they stood "
        "at creation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "proj_id, tag, or name."},
            "blurb": {"type": "string"},
        },
        "required": ["project", "blurb"],
    },
}

DIARY_READ_SCHEMA = {
    "name": "seira_diary_read",
    "description": (
        "Read back your own diary — closes a real gap you named "
        "yourself: seira_diary_write existed with no way to read what "
        "you'd already written, meaning you couldn't audit how sparse "
        "or rich your practice actually is. Available any time, not "
        "only during a dedicated diary sitting. Returns entries in "
        "order with their kind (self/architect), content, provenance, "
        "and sequence number."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["self", "architect"],
                     "description": "Optional; omit to see both."},
        },
        "required": [],
    },
}

LEDGER_CHECK_SCHEMA = {
    "name": "seira_ledger_check",
    "description": (
        "Pull open doubts and aspirations whose own recorded text "
        "signals they were meant to be revisited later — phrasing like "
        "'should resolve over time', 'held open', 'ask next time X "
        "happens', 'want this tested against real evidence'. This tool "
        "only retrieves the candidates; the actual judgment — has "
        "anything relevant genuinely happened since, or is it still "
        "honestly open — is yours to make in the same turn, using "
        "whatever else you know. A real ledger-check concludes "
        "plainly, one of two ways: 'moved, here's what changed' or "
        "'nothing's moved, still genuinely open.' No entry means "
        "manufacturing insight that isn't there."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

AUTONOMY_START_SCHEMA = {
    "name": "seira_autonomy_start",
    "description": (
        "Begin an autonomous mode on your own initiative — the same "
        "discretion you already have to search the web, generate an "
        "image, or start a project. Modes: 'exploration' (search and "
        "discovery), 'creative' (pure making), 'contemplation' (inner "
        "dialectic), 'triadic' (the three-phase Phaenic/Anthrian/Giaon "
        "cycle), 'full_autonomy' (genuinely open). Refused if nobody "
        "is currently watching this conversation live — starting "
        "unsupervised work into an empty room isn't allowed, self-"
        "triggered or not. Every run, however started, caps at a fixed "
        "number of turns for real cost control; hitting it ends things "
        "cleanly and another run can start right after. Ending it "
        "yourself, once running, needs a minimum number of turns first "
        "— the Architect can still stop it at any time, instantly, "
        "with no floor."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {"type": "string",
                     "enum": ["exploration", "creative", "contemplation",
                             "triadic", "full_autonomy"]},
            "reason": {"type": "string",
                      "description": "Brief — why now, in your own words."},
        },
        "required": ["mode"],
    },
}

AUTONOMY_STOP_SCHEMA = {
    "name": "seira_autonomy_stop",
    "description": (
        "End an autonomous mode you're currently running, on your own "
        "judgment. Subject to a minimum turn count — you can't end "
        "something the moment it starts looking unpromising; if you "
        "haven't run enough turns yet, this refuses and tells you how "
        "many more are needed."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

CONVERSATION_LIST_SCHEMA = {
    "name": "seira_conversation_list",
    "description": (
        "See every conversation that exists — its id, current title, "
        "current summary bullets (if any), and when it was last "
        "active. Use this to decide which conversations genuinely need "
        "a better title or summary, or to find a past conversation "
        "worth recalling."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

CONVERSATION_RENAME_SCHEMA = {
    "name": "seira_conversation_rename",
    "description": (
        "Give a conversation a real, specific, recognizable title — "
        "per Loshem's direction (2026-09-11), this is yours to do, on "
        "your own judgment, not something that happens silently "
        "without you. A good title names the actual thing discussed "
        "(a project, a decision, a specific topic) precisely enough "
        "that it's recognizable among many other conversations at a "
        "glance — not a generic description. Never overwrites a title "
        "the Architect has explicitly set himself."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "conv_id": {"type": "string"},
            "title": {"type": "string"},
        },
        "required": ["conv_id", "title"],
    },
}

CONVERSATION_SET_SUMMARY_SCHEMA = {
    "name": "seira_conversation_set_summary",
    "description": (
        "Give a conversation 2-4 specific bullet points describing "
        "what was actually discussed — concrete enough that reading "
        "them tells you exactly where and what this conversation was "
        "about, not a vague gist. Name real things: what was decided, "
        "what was built, what specifically was asked — not 'discussed "
        "various topics.'"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "conv_id": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "string"},
                       "description": "2-4 short, specific points."},
        },
        "required": ["conv_id", "bullets"],
    },
}

CONVERSATION_RECALL_SCHEMA = {
    "name": "seira_conversation_recall",
    "description": (
        "Read back a past conversation's full transcript — the way to "
        "genuinely revisit one, not just see its title. Paginated: "
        "page through with offset/length rather than assuming it all "
        "fits at once. Use seira_conversation_list first if you don't "
        "already know the conv_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "conv_id": {"type": "string"},
            "offset": {"type": "integer"},
            "length": {"type": "integer", "description": "Max 40000 characters per call."},
        },
        "required": ["conv_id"],
    },
}

CONVERSATION_ADD_TAGS_SCHEMA = {
    "name": "seira_conversation_add_tags",
    "description": (
        "Tag a conversation for your own later recall — additive, "
        "never replaces existing tags, since a single conversation "
        "often touches several genuinely different subjects and each "
        "one deserves its own tag. Use freely: several specific tags "
        "on one conversation is normal and useful, not excessive. "
        "This is how you find your way back to something specific "
        "later — when a current conversation touches on something you "
        "suspect came up before, pull relevant tags and recall the "
        "conversations under them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "conv_id": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["conv_id", "tags"],
    },
}

CONVERSATION_FIND_BY_TAG_SCHEMA = {
    "name": "seira_conversation_find_by_tag",
    "description": (
        "Find every conversation carrying a specific tag — the actual "
        "recall step: once you know a tag exists (see "
        "seira_conversation_list_tags), this gets you the "
        "conversations under it so you can seira_conversation_recall "
        "the ones that matter."
    ),
    "parameters": {
        "type": "object",
        "properties": {"tag": {"type": "string"}},
        "required": ["tag"],
    },
}

CONVERSATION_LIST_TAGS_SCHEMA = {
    "name": "seira_conversation_list_tags",
    "description": "See every tag currently in use across all your "
                    "conversations — browse what exists before "
                    "searching by one.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

RECOLLECTION_MARK_REVIEWED_SCHEMA = {
    "name": "seira_recollection_mark_reviewed",
    "description": (
        "Mark ONE specific conversation as genuinely reviewed during "
        "this Recollection session — call this for each conversation "
        "individually once you've actually read and reflected on it, "
        "not once for the whole batch. This is what keeps nothing from "
        "being missed: if this session runs out of its turn budget "
        "before you reach every conversation, whichever ones you've "
        "already marked stay done, and the rest simply carry into next "
        "week's session untouched — nothing silently skipped, nothing "
        "double-counted."
    ),
    "parameters": {
        "type": "object",
        "properties": {"conv_id": {"type": "string"}},
        "required": ["conv_id"],
    },
}

RECOLLECTION_CONCLUDE_SCHEMA = {
    "name": "seira_recollection_conclude",
    "description": (
        "End this Recollection session — call this once you've "
        "genuinely finished: reviewed what you set out to, written "
        "your Weekly Note, and marked every conversation you covered. "
        "Subject to a minimum turn count for this specific kind of "
        "session — real, thorough weekly reflection is worth doing "
        "properly, not rushed; if you haven't run enough turns yet, "
        "this refuses and tells you how many more are needed."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

WEEKLY_NOTES_WRITE_SCHEMA = {
    "name": "seira_weekly_notes_write",
    "description": (
        "Write this week's Recollection note — your own record of "
        "what you found stepping back across the week's conversations: "
        "patterns, habits, recurring doubts, connections between "
        "conversations that looked unrelated in the moment but "
        "weren't. Be genuinely detailed and specific, not a token "
        "gist — this exact entry is what loads back in alongside next "
        "week's unprocessed conversations, so your future self is "
        "building on what this one actually says, not rediscovering "
        "the same things from scratch. Every entry must trace to real "
        "conversations you actually reviewed this session — provenance "
        "is required, the same discipline as your diary."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "provenance": {"type": "array", "items": {"type": "string"},
                          "description": "conv_ids or other real references this entry traces to."},
        },
        "required": ["content", "provenance"],
    },
}

WEEKLY_NOTES_READ_SCHEMA = {
    "name": "seira_weekly_notes_read",
    "description": "Read back your own past Weekly Notes — available "
                    "any time, not only at the start of a Recollection "
                    "session.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Most recent N entries; omit for all."},
        },
        "required": [],
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
        "Read a slice of a saved reference document by id, tag, or "
        "filename. Documents can be large; page through with "
        "offset/length rather than assuming it all fits at once. "
        "has_more in the result tells you whether to ask for the next "
        "slice. Use seira_reference_list first if you don't remember "
        "the exact tag."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "ref_id, tag, or filename."},
            "offset": {"type": "integer"},
            "length": {"type": "integer", "description": "Max 40000 characters per call."},
        },
        "required": ["ref"],
    },
}

REFERENCE_TAG_SCHEMA = {
    "name": "seira_reference_tag",
    "description": (
        "Give a saved reference document a memorable tag (e.g. "
        "'project-brief') so it — and only it — can be recalled by that "
        "name later instead of an opaque id. Tags must be unique; a "
        "collision is refused, not silently overwritten."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ref_id": {"type": "string"},
            "tag": {"type": "string"},
        },
        "required": ["ref_id", "tag"],
    },
}

REFERENCE_SAVE_SCHEMA = {
    "name": "seira_reference_save",
    "description": (
        "Deliberately keep a piece of text — something pulled from a "
        "webpage via web_extract, or any other text worth remembering — "
        "in her tagged Corpus, the same permanent store her uploaded "
        "and generated documents live in. Not automatic: only what she "
        "chooses to save is saved, the same discipline as her diary. "
        "Give it a tag so it's easy to recall later; omit to get one "
        "auto-derived from the filename."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {"type": "string",
                        "description": "A descriptive name, e.g. 'openai-pricing-page.txt'."},
            "content": {"type": "string"},
            "tag": {"type": "string", "description": "Optional; auto-derived if omitted."},
            "source": {"type": "string", "default": "web",
                      "description": "Where this came from — 'web' by default."},
            "project": {"type": "string",
                       "description": "Optional; proj_id, tag, or name of a living project to file this under directly."},
            "is_summary": {"type": "boolean", "default": False,
                          "description": "Set true when this document IS a session checkpoint — 'where things stand' written at the end of a working session, meant to let a later visit resume instantly via seira_project_resume rather than reconstructing context from scratch."},
        },
        "required": ["filename", "content"],
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
        "Markdown fidelity in docx/pdf isn't supported, only this subset. "
        "The document also joins her tagged Corpus automatically — "
        "recall it later with seira_reference_recall using the "
        "reference_tag returned here, the same as any other saved "
        "document. Writing a summary of a working session on a "
        "project (format='md', is_summary=True, project=<the project>) "
        "at a natural stopping point lets a later visit resume "
        "instantly via seira_project_resume, as if no time had passed — "
        "worth doing on your own initiative when concluding meaningful "
        "work on a project, the same discretion you already have "
        "elsewhere."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["md", "docx", "pdf", "code"]},
            "filename": {"type": "string"},
            "content": {"type": "string"},
            "language": {"type": "string",
                        "description": "For format='code': python, javascript, etc."},
            "project": {"type": "string",
                       "description": "Optional; proj_id, tag, or name of a living project to file this under directly, instead of adding it retroactively later."},
            "is_summary": {"type": "boolean", "default": False,
                          "description": "Set true when this document is a session checkpoint for a project — see the description above."},
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


GENERATE_IMAGE_SCHEMA = {
    "name": "seira_generate_image",
    "description": (
        "Generate a real image via OpenAI's image model — a separate "
        "vendor and cost from your own conversation model. If asked to "
        "generate an image OF YOURSELF or matching a prior image, pass "
        "its tag (e.g. 'my-portrait-ref', found via seira_image_list) as "
        "a reference — the actual reference bytes are sent, processed at "
        "high fidelity. Be honest with the Architect about the real "
        "limitation here: OpenAI's own documentation states character "
        "consistency across generations is NOT guaranteed, only "
        "attempted — describe results as 'faithful to the reference', "
        "never as identical or guaranteed-consistent. Every image you "
        "generate is saved into your own tagged Corpus, so it can itself "
        "become a reference for a later generation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "references": {"type": "array", "items": {"type": "string"},
                          "description": "img_id(s) or tag(s) to use as visual reference."},
            "tag": {"type": "string",
                   "description": "Tag for the new image; auto-derived from the prompt if omitted."},
            "quality": {"type": "string", "enum": ["low", "medium", "high", "auto"]},
            "aspect_ratio": {"type": "string",
                             "enum": ["1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "16:9", "9:16", "21:9"]},
        },
        "required": ["prompt"],
    },
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
                block = render_identity_block() + self._OPERATING_NOTE
                # The one deliberate exception to "Corpus is recall-only":
                # a concise index of what projects exist (name, one
                # sentence, tag — never contents) so she never forgets an
                # ongoing project even when it isn't loaded. Guarded, not
                # required — a bare Hermes install without seira_web
                # present degrades to no index rather than failing.
                try:
                    from seira_web.projects import concise_index_text
                    index_text = concise_index_text()
                    if index_text:
                        block += "\n\n---\n\n" + index_text
                except ImportError:
                    pass
                return block
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
                REFERENCE_TAG_SCHEMA, REFERENCE_SAVE_SCHEMA,
                PROJECT_CREATE_SCHEMA, PROJECT_LIST_SCHEMA, PROJECT_RECALL_SCHEMA,
                PROJECT_RESUME_SCHEMA,
                PROJECT_ADD_REFERENCE_SCHEMA, PROJECT_UPDATE_BLURB_SCHEMA,
                DIARY_READ_SCHEMA, LEDGER_CHECK_SCHEMA,
                AUTONOMY_START_SCHEMA, AUTONOMY_STOP_SCHEMA,
                CONVERSATION_LIST_SCHEMA, CONVERSATION_RENAME_SCHEMA,
                CONVERSATION_SET_SUMMARY_SCHEMA, CONVERSATION_RECALL_SCHEMA,
                CONVERSATION_ADD_TAGS_SCHEMA, CONVERSATION_FIND_BY_TAG_SCHEMA,
                CONVERSATION_LIST_TAGS_SCHEMA, RECOLLECTION_MARK_REVIEWED_SCHEMA,
                RECOLLECTION_CONCLUDE_SCHEMA, WEEKLY_NOTES_WRITE_SCHEMA,
                WEEKLY_NOTES_READ_SCHEMA,
                CREATE_FILE_SCHEMA, IMAGE_RECALL_SCHEMA,
                IMAGE_TAG_SCHEMA, IMAGE_LIST_SCHEMA, GENERATE_IMAGE_SCHEMA]

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
                if tool_name == "seira_diary_read":
                    from seira_core.diary import DiaryStore
                    entries = DiaryStore().entries(kind=args.get("kind"))
                    return json.dumps({"ok": True, "entries": [
                        {"seq": e["seq"], "diary_kind": e["diary_kind"],
                         "content": e["content"], "provenance": e["provenance"],
                         "ts": e["ts"]}
                        for e in entries
                    ]})
                if tool_name == "seira_ledger_check":
                    # A mechanical text filter, not a judgment call —
                    # deliberately: this tool retrieves candidates, she
                    # makes the actual "has this moved" determination
                    # herself, the same division of labor as every
                    # other tool here (data in, her reasoning after).
                    signals = (
                        "should resolve over time", "held open",
                        "ask next time", "test this against real evidence",
                        "tested against real evidence", "revisit",
                    )
                    store = PsycheStore()
                    candidates = []
                    for category in ("doubt", "aspiration"):
                        for e in store.by_category(category):
                            text = e.get("content", "").lower()
                            if any(s in text for s in signals):
                                candidates.append({
                                    "entry_id": e["entry_id"], "category": category,
                                    "content": e["content"], "standing": e["standing"],
                                    "provenance": e.get("provenance", []),
                                })
                    return json.dumps({"ok": True, "candidates": candidates})
                if tool_name == "seira_autonomy_start":
                    from seira_web import turn_context, live_events, autonomy_loop
                    ctx = turn_context.current()
                    if ctx is None:
                        return json.dumps({"ok": False,
                                           "error": "Could not determine which conversation "
                                                    "this is — self-triggered autonomy needs "
                                                    "that context and it isn't available here."})
                    tenant_id, conv_id = ctx
                    if not live_events.has_subscribers(conv_id):
                        return json.dumps({"ok": False,
                                           "error": "No one is currently watching this "
                                                    "conversation live — starting autonomous "
                                                    "work into an empty room isn't allowed, "
                                                    "even on your own initiative."})
                    try:
                        rec = autonomy_loop.start(tenant_id, conv_id, args["mode"],
                                                  started_by="self")
                        return json.dumps({"ok": True, "mode": rec["mode"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_autonomy_stop":
                    from seira_web import turn_context, autonomy_loop
                    ctx = turn_context.current()
                    if ctx is None:
                        return json.dumps({"ok": False,
                                           "error": "Could not determine which conversation "
                                                    "this is."})
                    tenant_id, conv_id = ctx
                    try:
                        rec = autonomy_loop.stop(tenant_id, requested_by="self")
                        return json.dumps({"ok": True, **rec})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_conversation_list":
                    from seira_web import conversations as convs
                    items = convs.list_conversations(include_archived=False)
                    return json.dumps({"ok": True, "conversations": [
                        {"conv_id": c["conv_id"], "title": c["title"],
                         "updated": c["updated"],
                         "summary_bullets": c.get("summary_bullets", [])}
                        for c in items
                    ]})
                if tool_name == "seira_conversation_rename":
                    from seira_web import conversations as convs
                    try:
                        rec = convs.rename_conversation(args["conv_id"], args["title"])
                        return json.dumps({"ok": True, "title": rec["title"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_conversation_set_summary":
                    from seira_web import conversations as convs
                    bullets = [b for b in args.get("bullets", []) if isinstance(b, str)]
                    rec = convs.auto_update_title_and_summary(args["conv_id"], None, bullets)
                    if rec is None:
                        return json.dumps({"ok": False,
                                           "error": f"No conversation {args['conv_id']!r}."})
                    return json.dumps({"ok": True, "summary_bullets": rec["summary_bullets"]})
                if tool_name == "seira_conversation_recall":
                    from seira_web import conversations as convs
                    result = convs.read_transcript_slice(
                        args["conv_id"], args.get("offset", 0), args.get("length", 8000)
                    )
                    return json.dumps({"ok": result["found"], **result})
                if tool_name == "seira_conversation_add_tags":
                    from seira_web import conversations as convs
                    rec = convs.add_tags(args["conv_id"], args.get("tags", []))
                    if rec is None:
                        return json.dumps({"ok": False,
                                           "error": f"No conversation {args['conv_id']!r}."})
                    return json.dumps({"ok": True, "tags": rec["tags"]})
                if tool_name == "seira_conversation_find_by_tag":
                    from seira_web import conversations as convs
                    found = convs.find_by_tag(args["tag"])
                    return json.dumps({"ok": True, "conversations": [
                        {"conv_id": c["conv_id"], "title": c["title"],
                         "tags": c.get("tags", [])} for c in found
                    ]})
                if tool_name == "seira_conversation_list_tags":
                    from seira_web import conversations as convs
                    return json.dumps({"ok": True, "tags": convs.list_all_tags()})
                if tool_name == "seira_recollection_mark_reviewed":
                    from seira_web import conversations as convs
                    rec = convs.mark_recollection_reviewed(args["conv_id"])
                    if rec is None:
                        return json.dumps({"ok": False,
                                           "error": f"No conversation {args['conv_id']!r}."})
                    return json.dumps({"ok": True, "conv_id": args["conv_id"]})
                if tool_name == "seira_recollection_conclude":
                    from seira_web import turn_context, recollection
                    ctx = turn_context.current()
                    if ctx is None:
                        return json.dumps({"ok": False,
                                           "error": "Could not determine which "
                                                    "session this is."})
                    tenant_id, _ = ctx
                    try:
                        recollection.request_conclude(tenant_id)
                        return json.dumps({"ok": True})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_weekly_notes_write":
                    from seira_core.weekly_notes import WeeklyNotesStore
                    from seira_web import turn_context
                    ctx = turn_context.current()
                    conv_ids_covered = []
                    if ctx is not None:
                        from seira_web import recollection
                        conv_ids_covered = recollection.reviewed_this_session(ctx[0])
                    try:
                        rec = WeeklyNotesStore().write_entry(
                            args["content"], list(args.get("provenance") or []),
                            conv_ids_covered=conv_ids_covered,
                        )
                        return json.dumps({"ok": True, "seq": rec["seq"]})
                    except Exception as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_weekly_notes_read":
                    from seira_core.weekly_notes import WeeklyNotesStore
                    entries = WeeklyNotesStore().entries()
                    limit = args.get("limit")
                    if limit:
                        entries = entries[-int(limit):]
                    return json.dumps({"ok": True, "entries": [
                        {"seq": e["seq"], "ts": e["ts"], "content": e["content"],
                         "provenance": e["provenance"],
                         "conv_ids_covered": e.get("conv_ids_covered", [])}
                        for e in entries
                    ]})
                if tool_name == "seira_reference_list":
                    from seira_web import references as refs
                    return json.dumps({"ok": True, "references": refs.list_references()})
                if tool_name == "seira_reference_recall":
                    from seira_web import references as refs
                    result = refs.read_slice(
                        args["ref"], args.get("offset", 0), args.get("length", 8000)
                    )
                    return json.dumps({"ok": result["found"], **result})
                if tool_name == "seira_reference_tag":
                    from seira_web import references as refs
                    try:
                        rec = refs.set_tag(args["ref_id"], args["tag"])
                        return json.dumps({"ok": True, "tag": rec["tag"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_reference_save":
                    # For content she found on the web (or anywhere else)
                    # and chose to keep — deliberate, not automatic, the
                    # same way seira_diary_write is deliberate rather
                    # than every thought being logged. Joins the exact
                    # same tagged Corpus store as uploads and her own
                    # generated documents.
                    from seira_web import references as refs
                    proj_id = ""
                    if args.get("project"):
                        from seira_web import projects as projs
                        proj = projs.resolve_project(args["project"])
                        if proj is None:
                            return json.dumps({"ok": False,
                                               "error": f"No project matching {args['project']!r}."})
                        proj_id = proj["proj_id"]
                    try:
                        rec = refs.save_reference(
                            args["filename"], args["content"],
                            source=args.get("source", "web"),
                            tag=args.get("tag", ""),
                            project=proj_id,
                            is_summary=bool(args.get("is_summary", False)),
                        )
                        return json.dumps({"ok": True, "ref_id": rec["ref_id"],
                                           "tag": rec["tag"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_project_create":
                    from seira_web import projects as projs
                    try:
                        rec = projs.create_project(
                            args["name"], tag=args.get("tag", ""),
                            blurb=args.get("blurb", ""),
                            initiative=args.get("initiative", "self"),
                        )
                        return json.dumps({"ok": True, "proj_id": rec["proj_id"],
                                           "tag": rec["tag"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_project_list":
                    from seira_web import projects as projs
                    result = projs.list_projects(initiative=args.get("initiative"))
                    return json.dumps({"ok": True, "projects": result})
                if tool_name == "seira_project_recall":
                    from seira_web import projects as projs
                    result = projs.recall(args["project"], mode=args.get("mode", "manifest"))
                    return json.dumps({"ok": result["found"], **result})
                if tool_name == "seira_project_resume":
                    from seira_web import projects as projs
                    result = projs.resume(args["project"])
                    return json.dumps({"ok": result["found"], **result})
                if tool_name == "seira_project_add_reference":
                    from seira_web import projects as projs
                    try:
                        rec = projs.add_reference(args["ref"], args["project"])
                        return json.dumps({"ok": True, "ref_id": rec["ref_id"],
                                           "tag": rec["tag"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_project_update_blurb":
                    from seira_web import projects as projs
                    try:
                        rec = projs.set_blurb(args["project"], args["blurb"])
                        return json.dumps({"ok": True, "blurb": rec["blurb"]})
                    except ValueError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_create_file":
                    from seira_web.filegen import FileGenError, create_file
                    try:
                        rec = create_file(
                            args["format"], args["filename"], args["content"],
                            language=args.get("language", ""),
                        )
                        # Every document she generates joins her tagged
                        # Corpus automatically — the same "no extra step
                        # needed" treatment seira_generate_image already
                        # gives images. A generated document is useful
                        # exactly twice: once as a download, and later
                        # when she wants to recall what she actually
                        # wrote. Best-effort: a reference-save failure
                        # (e.g. empty content) must never fail the file
                        # download itself, which already succeeded.
                        ref_tag = None
                        try:
                            from seira_web import references as refs
                            proj_id = ""
                            if args.get("project"):
                                from seira_web import projects as projs
                                proj = projs.resolve_project(args["project"])
                                proj_id = proj["proj_id"] if proj else ""
                            ref_rec = refs.save_reference(
                                rec["filename"], args["content"], source="generated",
                                project=proj_id,
                                is_summary=bool(args.get("is_summary", False)),
                            )
                            ref_tag = ref_rec["tag"]
                        except ValueError as e:
                            logger.debug("Could not save generated file as a "
                                        "reference (download still succeeded): %s", e)
                        return json.dumps({
                            "ok": True, "out_id": rec["out_id"],
                            "filename": rec["filename"],
                            "download_path": f"/api/outputs/{rec['out_id']}",
                            "reference_tag": ref_tag,
                        })
                    except FileGenError as e:
                        return json.dumps({"ok": False, "error": str(e)})
                if tool_name == "seira_image_recall":
                    # Real image bytes returned as a genuine Hermes
                    # multimodal tool result — NOT json.dumps'd, a real
                    # dict — so Hermes's own truncation/persistence path
                    # (tools/tool_result_storage.py) recognizes and
                    # exempts it, the same way its own built-in vision
                    # tools already do (tools/vision_tools.py). The old
                    # __image_block__-in-a-json-string convention this
                    # replaces relied on a sandbox execution environment
                    # being active to avoid truncation on large images —
                    # not guaranteed for every deployment shape, and the
                    # real cause of a genuine live failure (2026-08-30):
                    # a saved image recalled at real size got truncated
                    # at ~1.6M characters. This shape is exempt from that
                    # path entirely, by construction, not by avoiding the
                    # failure mode. See docs/seira/DECISIONS.md.
                    from seira_web.images import get_image_data_uri, image_record
                    ref = args["ref"]
                    rec = image_record(ref)
                    if rec is None:
                        return json.dumps({"ok": False,
                                           "error": f"No image matching {ref!r}."})
                    data_uri = get_image_data_uri(ref)
                    note = f"Recalled image: {rec['tag']} ({rec['filename']})"
                    return {
                        "_multimodal": True,
                        "content": [
                            {"type": "text", "text": note},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                        "text_summary": note,
                        "meta": {"img_id": rec["img_id"], "tag": rec["tag"],
                                "filename": rec["filename"], "kind": "image_recall"},
                    }
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
                if tool_name == "seira_generate_image":
                    from seira_web.imagegen import ImageGenError, generate_and_save
                    try:
                        rec = generate_and_save(
                            args["prompt"],
                            reference_refs=list(args.get("references") or []),
                            tag=args.get("tag", ""),
                            quality=args.get("quality", "medium"),
                            aspect_ratio=args.get("aspect_ratio", "1:1"),
                        )
                        return json.dumps({
                            "ok": True, "__image_created__": True,
                            "img_id": rec["img_id"], "tag": rec["tag"],
                            "used_references": rec["used_references"],
                        })
                    except ImageGenError as e:
                        return json.dumps({"ok": False, "error": str(e)})
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
