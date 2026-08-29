"""seira_web.hermes_tools — a deliberately narrow bridge from Sanctum's
chat loop to REAL Hermes tool handlers (tools/registry.py), so she can
use actual Hermes capabilities from the website, not just her Psyche
tools and Anthropic's native web search.

Read this before widening ``ENABLED_TOOLSETS`` below.

## Why this is narrow, not the full Hermes toolset list

Sanctum's chat loop (chat.py) is a direct call to
``https://api.anthropic.com/v1/messages`` — there is no Hermes
``agent`` object, no conversation_loop, no subagent lifecycle, no
sandboxed execution environment. Most Hermes tool handlers are written
assuming that context exists (``tools/delegate_tool.py`` spawns a full
child agent process; ``tools/terminal_tool.py`` and
``tools/browser/*`` execute directly on the host machine running
Sanctum; ``tools/todo_tool.py`` expects an injected store object).

Bridging THOSE safely means either building the sandboxing Sanctum
currently has none of, or accepting that a public-facing website now
gives Anthropic's model a shell on your server. That is a real
architecture decision, not a config flip — deliberately NOT made here,
the same way the image-generation vendor choice was left to you rather
than assumed (see docs/seira/DECISIONS.md).

## What IS bridged here, and why it's safe

Only handlers verified, by reading their registration in
``tools/*.py``, to be pure functions of their arguments — no agent
context, no host shell, no subagent spawn:

* **web** (``web_search``, ``web_extract``) — HTTP requests to search
  APIs / target URLs only.
* **skills** (``skills_list``, ``skill_view``, ``skill_manage``) —
  reads and writes her skill documents under HERMES_HOME/skills.

**One real caveat on `skills`, worth knowing before you enable it:**
the skills directory is HERMES_HOME-scoped, not per-tenant. On a
single-tenant deployment (the current, recommended state — see
docs/seira/WIRING.md Part 1) that's simply her one skills library and
is fine. If you ever reopen multi-tenant signups, do NOT enable
`skills` here without adding tenant scoping to HERMES_HOME resolution
first, or every tenant would read and edit the same skill documents.

Enable via env var, explicit and off by default:

    SEIRA_EXTRA_TOOLSETS=web,skills

Anything else you list is silently ignored — the whitelist below is
the only surface this module will ever expose, regardless of what an
operator types.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

# The only toolsets this bridge will ever expose, no matter what
# SEIRA_EXTRA_TOOLSETS contains. Widening this list is a deliberate,
# reviewed decision — see the module docstring before adding to it.
_BRIDGEABLE_TOOLSETS = {"web", "skills"}


def _requested_toolsets() -> Set[str]:
    raw = os.environ.get("SEIRA_EXTRA_TOOLSETS", "").strip()
    if not raw:
        return set()
    requested = {t.strip() for t in raw.split(",") if t.strip()}
    unknown = requested - _BRIDGEABLE_TOOLSETS
    if unknown:
        logger.warning(
            "SEIRA_EXTRA_TOOLSETS named toolset(s) this bridge does not "
            "expose (ignored): %s. Bridgeable: %s",
            ", ".join(sorted(unknown)), ", ".join(sorted(_BRIDGEABLE_TOOLSETS)),
        )
    return requested & _BRIDGEABLE_TOOLSETS


def _registry():
    # Deferred import: this also triggers discover_builtin_tools() via
    # model_tools's own import-time call, so the registry is populated
    # by the time we read from it. Deferred so a Sanctum deployment that
    # never sets SEIRA_EXTRA_TOOLSETS never pays this import cost.
    import model_tools  # noqa: F401  (populates tools.registry.registry)
    from tools.registry import registry
    return registry


def extra_tool_names() -> Set[str]:
    """Tool names this bridge will dispatch, given current config."""
    toolsets = _requested_toolsets()
    if not toolsets:
        return set()
    reg = _registry()
    names: Set[str] = set()
    for ts in toolsets:
        names |= set(reg.get_tool_names_for_toolset(ts))
    return names


def extra_tool_schemas() -> List[Dict[str, Any]]:
    """Anthropic-format tool schemas for the bridged tools, filtered by
    each tool's own check_fn (e.g. web tools disappear if no search API
    key is configured, exactly as they would in native Hermes)."""
    names = extra_tool_names()
    if not names:
        return []
    reg = _registry()
    openai_defs = reg.get_definitions(names)
    schemas = []
    for d in openai_defs:
        fn = d["function"]
        schemas.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return schemas


def dispatch_extra_tool(name: str, args: Dict[str, Any]) -> str:
    """Run a bridged tool by name. Returns the same string/JSON contract
    every Hermes tool result already uses — chat.py logs and forwards
    it exactly like a Psyche-provider tool result, no special casing
    needed on that side beyond routing by name."""
    reg = _registry()
    result = reg.dispatch(name, args)
    if isinstance(result, dict):
        import json
        return json.dumps(result)
    return result
