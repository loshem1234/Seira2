"""Read-only measurement of what her context costs per turn.

Nothing here changes behavior. Token counts are estimates
(characters / 3.6) — good for comparing layers, not for billing.
Everything is measured from the live runtime (the same agent object a
real turn builds), not from documentation.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

CHARS_PER_TOKEN = 3.6


def est(text: Any) -> int:
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    return int(len(text) / CHARS_PER_TOKEN)


def build_report(tenant_id: str) -> Dict[str, Any]:
    from seira_web import conversations as convs
    from seira_web import hermes_session as hs
    from seira_core.tenancy import tenant_scope

    report: Dict[str, Any] = {"note": "Estimates (chars/3.6). Compare layers; do not bill from this."}
    with tenant_scope(tenant_id):
        # --- identity layers ---
        ident: Dict[str, int] = {}
        try:
            from seira_core.intellect import IntellectStore
            from seira_core.prompt_block import _render_psyche_digest, render_identity_block
            from seira_core.unity import read_unity
            ident["unity"] = est(read_unity())
            ident["intellect"] = est(IntellectStore().current()["content"])
            ident["psyche"] = est(_render_psyche_digest())
            ident["identity_block_total"] = est(render_identity_block())
        except Exception as e:  # report what we can
            ident["error"] = str(e)[:200]
        try:
            from seira_core.psyche import PsycheStore
            ents = PsycheStore().state()["entries"].values()
            live = [e for e in ents if e["standing"] != "retired" and "superseded_by" not in e]
            by_cat: Dict[str, int] = {}
            for e in live:
                by_cat[e["category"]] = by_cat.get(e["category"], 0) + est(e["content"])
            ident["psyche_live_entries"] = len(live)
            ident["psyche_superseded_entries"] = sum(
                1 for e in ents if "superseded_by" in e)
            ident["psyche_tokens_by_category"] = by_cat
        except Exception:
            pass
        report["identity"] = ident

        # --- agent: system prompt + tools + caching/compression ---
        agent = None
        try:
            agent = hs._build_agent(f"ctxreport-{uuid.uuid4().hex[:8]}", lambda ev: None)
            parts = agent._build_system_prompt_parts()
            report["system_prompt_tiers"] = {k: est(v) for k, v in parts.items()}
            report["system_prompt_total"] = sum(report["system_prompt_tiers"].values())
            tools = list(getattr(agent, "tools", None) or [])
            try:  # memory-provider (her seira_* self-tools) schemas, if not already counted
                have = {t.get("function", {}).get("name") or t.get("name") for t in tools}
                mm = getattr(agent, "_memory_manager", None)
                for sch in (mm.get_all_tool_schemas() if mm else []):
                    nm = sch.get("name") or sch.get("function", {}).get("name")
                    if nm not in have:
                        tools.append(sch)
            except Exception:
                pass
            from tools.registry import registry
            groups: Dict[str, Dict[str, Any]] = {}
            for t in tools:
                name = t.get("function", {}).get("name") or t.get("name", "?")
                ts = registry.get_toolset_for_tool(name) or (
                    "seira (her own tools)" if str(name).startswith("seira_") else "other")
                g = groups.setdefault(ts, {"tokens": 0, "tools": 0})
                g["tokens"] += est(t)
                g["tools"] += 1
            report["tools"] = {
                "count": len(tools),
                "total_tokens": sum(g["tokens"] for g in groups.values()),
                "by_toolset": dict(sorted(groups.items(), key=lambda kv: -kv[1]["tokens"])),
            }
            report["settings"] = {
                "prompt_caching": bool(getattr(agent, "_use_prompt_caching", False)),
                "cache_ttl": getattr(agent, "_cache_ttl", None),
                "compression_enabled": bool(getattr(agent, "compression_enabled", False)),
                "context_length": getattr(getattr(agent, "context_compressor", None),
                                          "context_length", None),
                "compression_threshold_tokens": getattr(
                    getattr(agent, "context_compressor", None), "threshold_tokens", None),
            }
        except Exception as e:
            report["agent_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        finally:
            try:
                if agent is not None and hasattr(agent, "close"):
                    agent.close()
            except Exception:
                pass

        # --- history: what is actually replayed per turn (last 30 turns) ---
        sizes: List[Dict[str, Any]] = []
        for c in convs.list_conversations(include_archived=False):
            try:
                hist = convs.model_history(c["id"])
            except Exception:
                continue
            sizes.append({"id": c["id"], "title": c.get("title", ""),
                          "messages": len(hist),
                          "tokens": sum(est(m["content"]) for m in hist)})
        sizes.sort(key=lambda s: -s["tokens"])
        toks = sorted(s["tokens"] for s in sizes)
        report["history"] = {
            "conversations": len(sizes),
            "replay_cap": "last 30 turns (60 messages) per chat; older turns are not sent",
            "median_tokens": toks[len(toks) // 2] if toks else 0,
            "max_tokens": toks[-1] if toks else 0,
            "largest": sizes[:8],
        }

    fixed = (report.get("system_prompt_total", 0) + report.get("tools", {}).get("total_tokens", 0))
    report["fixed_cost_per_turn_before_history"] = fixed
    return report
