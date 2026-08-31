"""seira_web.projects — her living archive: named, tagged groupings of
Corpus documents for accumulating work, not one-off references.

A project is a thin grouping on top of the SAME references.py store —
no separate document format, no parallel storage. Each markdown file
filed under a project is a normal reference (references.py), tagged
with a project_id so it can be pulled back as a group. This is
deliberate: one Corpus, one tagging discipline, projects are just a
second axis on top of it.

Two very different visibility levels, on purpose:

  - The full CONTENTS of a project are Corpus content: recall-only,
    never preloaded — same discipline as every document and image.
  - A CONCISE INDEX of which projects exist — name, one sentence, tag,
    nothing more — is the one deliberate exception: always present in
    her context, alongside Unity/Intellect/Psyche, so she never forgets
    an ongoing project exists even when its contents aren't loaded.
    This is Loshem's explicit design choice (2026-08-31): a narrow,
    bounded carve-out (concise_index_text(), wired into both
    agent/prompt_builder.py's load_soul_md and
    seira_bridge.system_prompt_block()), not a general precedent for
    preloading Corpus content. If a project has no blurb yet, its
    index line is just the name and tag — a living index she's meant
    to keep current with set_blurb() as work actually happens, not a
    one-time description frozen at creation.

Grouping is retroactive as much as prospective: add_reference() lets
her notice that two documents saved separately, days apart, actually
belong to the same accumulating body of work, and file them together
after the fact — not only at the moment either was created.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from seira_core.paths import seira_home


def _projects_dir() -> Path:
    return seira_home() / "corpus" / "projects"


def _index_path() -> Path:
    return _projects_dir() / "index.json"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60] or "project"


def _load_index() -> Dict[str, Dict[str, Any]]:
    if not _index_path().exists():
        return {}
    return json.loads(_index_path().read_text(encoding="utf-8"))


def _save_index(index: Dict[str, Dict[str, Any]]) -> None:
    _projects_dir().mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _index_path())


def create_project(name: str, tag: str = "", blurb: str = "",
                   initiative: str = "self") -> Dict[str, Any]:
    if not name.strip():
        raise ValueError("A project needs a name.")
    if initiative not in ("self", "requested"):
        raise ValueError("initiative must be 'self' or 'requested'.")
    index = _load_index()
    proj_id = f"proj-{secrets.token_hex(6)}"
    default_tag = _slugify(tag) if tag.strip() else _slugify(name)
    existing_tags = {p["tag"] for p in index.values()}
    final_tag = default_tag
    if final_tag in existing_tags:
        final_tag = f"{final_tag}-{proj_id[5:9]}"
    record = {
        "proj_id": proj_id, "name": name[:200], "tag": final_tag,
        "blurb": blurb[:240], "created": _now(), "updated": _now(),
        # Honest self-report, same discipline as the diary's provenance
        # field — not inferred externally, since only she knows whether
        # this was her own unprompted idea or something asked of her.
        # Defaults to "self" at the storage layer (every call here is
        # already her tool use), but the tool schema still asks for it
        # explicitly each time, so stating it is a conscious act, not a
        # rubber-stamped default she never actually considers.
        "initiative": initiative,
    }
    index[proj_id] = record
    _save_index(index)
    return record


def set_blurb(proj_id_or_tag: str, blurb: str) -> Dict[str, Any]:
    """Keeps the always-visible index line current as work actually
    happens — a living index, not a snapshot frozen at creation."""
    rec = resolve_project(proj_id_or_tag)
    if rec is None:
        raise ValueError(f"No project matching {proj_id_or_tag!r}.")
    index = _load_index()
    index[rec["proj_id"]]["blurb"] = blurb[:240]
    index[rec["proj_id"]]["updated"] = _now()
    _save_index(index)
    return index[rec["proj_id"]]


def find_by_tag(tag: str) -> Optional[Dict[str, Any]]:
    tag = _slugify(tag)
    for r in _load_index().values():
        if r["tag"] == tag:
            return r
    return None


def find_by_name(name: str) -> Optional[Dict[str, Any]]:
    name = name.strip().lower()
    for r in _load_index().values():
        if r["name"].lower() == name:
            return r
    return None


def resolve_project(ref: str) -> Optional[Dict[str, Any]]:
    index = _load_index()
    if ref in index:
        return index[ref]
    rec = find_by_tag(ref)
    if rec is not None:
        return rec
    return find_by_name(ref)


def list_projects(initiative: Optional[str] = None) -> List[Dict[str, Any]]:
    """initiative=None: everything. initiative='self': only what she
    started on her own, unprompted — her own repository, filterable
    from the shared one rather than kept in a separate place. Records
    saved before this field existed default to 'self' (they were,
    definitionally, all her own tool calls already)."""
    projects = sorted(_load_index().values(), key=lambda r: r["updated"], reverse=True)
    if initiative is None:
        return projects
    return [p for p in projects if p.get("initiative", "self") == initiative]


def concise_index_text() -> str:
    """The always-loaded addendum, and ONLY this — title, one sentence,
    tag, and whether it was hers to begin with. Never file contents,
    never a document list. Empty string when she has no projects yet,
    so a fresh Seira's prompt doesn't carry a hollow header for
    nothing."""
    projects = list_projects()
    if not projects:
        return ""
    lines = ["# LIVING PROJECTS (index only — contents are recall-only; "
             "call seira_project_recall to actually load one)"]
    for p in projects:
        blurb = f" — {p['blurb']}" if p.get("blurb") else ""
        mark = " (her own initiative)" if p.get("initiative", "self") == "self" else ""
        lines.append(f"- \"{p['name']}\" [{p['tag']}]{mark}{blurb}")
    return "\n".join(lines)


def add_reference(ref_id: str, proj_id_or_tag: str) -> Dict[str, Any]:
    from seira_web import references as refs
    proj = resolve_project(proj_id_or_tag)
    if proj is None:
        raise ValueError(f"No project matching {proj_id_or_tag!r}.")
    rec = refs.resolve_ref(ref_id)
    if rec is None:
        raise ValueError(f"No reference matching {ref_id!r}.")
    refs.set_project(rec["ref_id"], proj["proj_id"])
    index = _load_index()
    index[proj["proj_id"]]["updated"] = _now()
    _save_index(index)
    return rec


def remove_reference(ref_id: str) -> Dict[str, Any]:
    from seira_web import references as refs
    rec = refs.resolve_ref(ref_id)
    if rec is None:
        raise ValueError(f"No reference matching {ref_id!r}.")
    refs.set_project(rec["ref_id"], None)
    return rec


def project_files(proj_id_or_tag: str) -> List[Dict[str, Any]]:
    from seira_web import references as refs
    proj = resolve_project(proj_id_or_tag)
    if proj is None:
        return []
    return [r for r in refs.list_references() if r.get("project") == proj["proj_id"]]


def session_summaries(proj_id_or_tag: str) -> List[Dict[str, Any]]:
    """Every checkpoint document filed under this project, most recent
    first — the trail of 'where we left off' across however many
    sessions there have been."""
    return [f for f in project_files(proj_id_or_tag) if f.get("is_summary")]


def resume(proj_id_or_tag: str) -> Dict[str, Any]:
    """The 'as if we never took a break' operation. Not the same as
    recall(): recall shows what's IN a project; resume gets you back
    to where you left off, cheaply, using whatever checkpoint she
    wrote at the end of the last session — not by reloading every
    document from scratch.

    Returns the most recent session summary's FULL text (this is the
    whole point — one targeted document, not a shotgun scan), plus a
    short list of any earlier summaries (so a project's session
    history stays discoverable, not just its latest state) and the
    project's own blurb for orientation. If no summary has ever been
    written yet, says so plainly and falls back to the ordinary
    manifest rather than pretending a checkpoint exists.
    """
    from seira_web import references as refs
    proj = resolve_project(proj_id_or_tag)
    if proj is None:
        return {"found": False, "error": f"No project matching {proj_id_or_tag!r}."}
    summaries = session_summaries(proj_id_or_tag)
    if not summaries:
        fallback = recall(proj_id_or_tag, mode="manifest")
        fallback["has_session_summary"] = False
        fallback["note"] = ("No session summary written yet for this project — "
                            "showing the ordinary manifest instead. Consider "
                            "writing one (seira_create_file with "
                            "is_summary=True) at the end of a working session "
                            "so the next visit can resume instantly.")
        return fallback
    latest = summaries[0]
    page = refs.read_slice(latest["ref_id"], 0, 40_000)
    earlier = [{"ref_id": s["ref_id"], "tag": s["tag"], "created": s["created"]}
              for s in summaries[1:]]
    return {
        "found": True, "has_session_summary": True, "project": proj["name"],
        "tag": proj["tag"], "blurb": proj.get("blurb", ""),
        "latest_summary": {"ref_id": latest["ref_id"], "tag": latest["tag"],
                           "created": latest["created"], "text": page["text"],
                           "truncated": page["has_more"]},
        "earlier_summaries": earlier,
        "total_file_count": len(project_files(proj_id_or_tag)),
    }


def recall(proj_id_or_tag: str, mode: str = "manifest",
          full_budget_chars: int = 40_000) -> Dict[str, Any]:
    """The 'refresh into a temporary context' operation.

    'manifest' (default): a table of contents — filenames, tags, short
    previews. Cheap, meant for orienting — "what's in here again?"

    'full': concatenates full text across every file up to a total
    character budget, listing anything that didn't fit rather than
    silently dropping it. For when she genuinely wants the whole
    project loaded, not just a reminder of its shape.
    """
    from seira_web import references as refs
    proj = resolve_project(proj_id_or_tag)
    if proj is None:
        return {"found": False, "error": f"No project matching {proj_id_or_tag!r}."}
    files = project_files(proj_id_or_tag)
    if mode == "manifest":
        entries = []
        for f in files:
            page = refs.read_slice(f["ref_id"], 0, 240)
            preview = page["text"].replace("\n", " ").strip()
            entries.append({"ref_id": f["ref_id"], "filename": f["filename"],
                            "tag": f["tag"], "preview": preview})
        return {"found": True, "mode": "manifest", "project": proj["name"],
                "tag": proj["tag"], "blurb": proj.get("blurb", ""),
                "file_count": len(files), "files": entries}
    if mode == "full":
        remaining = max(0, int(full_budget_chars))
        loaded: List[Dict[str, Any]] = []
        omitted: List[str] = []
        for f in files:
            if remaining <= 0:
                omitted.append(f["filename"])
                continue
            page = refs.read_slice(f["ref_id"], 0, remaining)
            loaded.append({"ref_id": f["ref_id"], "filename": f["filename"],
                           "tag": f["tag"], "text": page["text"],
                           "truncated": page["has_more"]})
            remaining -= len(page["text"])
        return {"found": True, "mode": "full", "project": proj["name"],
                "tag": proj["tag"], "blurb": proj.get("blurb", ""),
                "file_count": len(files), "files": loaded,
                "omitted_for_space": omitted}
    return {"found": False, "error": f"mode must be 'manifest' or 'full', got {mode!r}."}
