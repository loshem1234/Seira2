"""Tests for seira_web.projects — the living archive: named, tagged
groupings of Corpus documents, with a deliberately narrow always-visible
index (Loshem's explicit design, 2026-08-31) as the one exception to
"Corpus is recall-only".
"""

import json
import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_web import conversations as convs  # noqa: E402
from seira_web import projects as projs  # noqa: E402
from seira_web import references as refs  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I organize what accumulates."}],
        architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


# ---------------- storage layer ----------------

def test_create_project_and_list(home):
    rec = projs.create_project("Website Redesign", blurb="Planning the new homepage")
    assert rec["proj_id"].startswith("proj-")
    assert rec["tag"] == "website-redesign"
    listed = projs.list_projects()
    assert len(listed) == 1 and listed[0]["name"] == "Website Redesign"


def test_project_name_required(home):
    with pytest.raises(ValueError):
        projs.create_project("   ")


def test_project_tag_collision_disambiguated(home):
    a = projs.create_project("Launch Plan", tag="launch")
    b = projs.create_project("Another Launch", tag="launch")
    assert a["tag"] == "launch"
    assert b["tag"] != "launch"


def test_resolve_project_by_id_tag_or_name(home):
    rec = projs.create_project("Q3 Roadmap", tag="q3-roadmap")
    assert projs.resolve_project(rec["proj_id"])["proj_id"] == rec["proj_id"]
    assert projs.resolve_project("q3-roadmap")["proj_id"] == rec["proj_id"]
    assert projs.resolve_project("Q3 Roadmap")["proj_id"] == rec["proj_id"]
    assert projs.resolve_project("nonexistent") is None


def test_set_blurb_updates_and_touches_updated_timestamp(home):
    rec = projs.create_project("Ongoing Thing")
    original_updated = rec["updated"]
    updated = projs.set_blurb(rec["proj_id"], "Now includes the API redesign too")
    assert updated["blurb"] == "Now includes the API redesign too"


# ---------------- retroactive grouping ----------------

def test_add_existing_reference_to_project_retroactively(home):
    ref_rec = refs.save_reference("old-notes.txt", "some earlier notes")
    proj_rec = projs.create_project("Grouped Later")
    projs.add_reference(ref_rec["ref_id"], proj_rec["proj_id"])
    files = projs.project_files(proj_rec["proj_id"])
    assert len(files) == 1 and files[0]["ref_id"] == ref_rec["ref_id"]


def test_add_reference_to_unknown_project_raises(home):
    ref_rec = refs.save_reference("notes.txt", "content")
    with pytest.raises(ValueError):
        projs.add_reference(ref_rec["ref_id"], "no-such-project")


def test_remove_reference_ungroups_it(home):
    ref_rec = refs.save_reference("notes.txt", "content")
    proj_rec = projs.create_project("Temp Group")
    projs.add_reference(ref_rec["ref_id"], proj_rec["proj_id"])
    projs.remove_reference(ref_rec["ref_id"])
    assert projs.project_files(proj_rec["proj_id"]) == []


# ---------------- recall: manifest vs full ----------------

def test_recall_manifest_mode_gives_previews_not_full_text(home):
    proj_rec = projs.create_project("Research")
    refs.save_reference("a.md", "A" * 5000, project=proj_rec["proj_id"])
    refs.save_reference("b.md", "B" * 5000, project=proj_rec["proj_id"])
    result = projs.recall(proj_rec["proj_id"], mode="manifest")
    assert result["found"] and result["file_count"] == 2
    for f in result["files"]:
        assert len(f["preview"]) <= 240
        assert "text" not in f  # manifest never carries full content


def test_recall_full_mode_gives_full_text_within_budget(home):
    proj_rec = projs.create_project("Deep Dive")
    refs.save_reference("a.md", "short content a", project=proj_rec["proj_id"])
    refs.save_reference("b.md", "short content b", project=proj_rec["proj_id"])
    result = projs.recall(proj_rec["proj_id"], mode="full", full_budget_chars=100_000)
    assert result["mode"] == "full"
    assert {f["text"] for f in result["files"]} == {"short content a", "short content b"}
    assert result["omitted_for_space"] == []


def test_recall_full_mode_respects_budget_and_reports_omissions(home):
    """project_files() orders most-recently-saved first (same
    convention as list_references()/list_projects() everywhere else),
    so with a tight budget the earlier-saved file is what gets
    omitted, not necessarily whichever was created first in the test."""
    proj_rec = projs.create_project("Huge Project")
    refs.save_reference("a.md", "x" * 100, project=proj_rec["proj_id"])
    refs.save_reference("b.md", "y" * 100, project=proj_rec["proj_id"])
    result = projs.recall(proj_rec["proj_id"], mode="full", full_budget_chars=50)
    assert len(result["files"]) == 1  # only one fit within the budget
    assert len(result["omitted_for_space"]) == 1  # the other was reported, not dropped
    loaded_name = result["files"][0]["filename"]
    omitted_name = result["omitted_for_space"][0]
    assert {loaded_name, omitted_name} == {"a.md", "b.md"}


def test_recall_of_unknown_project_is_honest_not_an_exception(home):
    result = projs.recall("no-such-project")
    assert result["found"] is False


def test_recall_invalid_mode_is_honest_not_an_exception(home):
    proj_rec = projs.create_project("X")
    result = projs.recall(proj_rec["proj_id"], mode="something-else")
    assert result["found"] is False and "mode" in result["error"]


# ---------------- the always-visible index: narrow, on purpose ----------------

def test_concise_index_empty_when_no_projects(home):
    assert projs.concise_index_text() == ""


def test_concise_index_shows_title_blurb_tag_only(home):
    projs.create_project("Website Redesign", tag="website",
                         blurb="Planning the new homepage")
    text = projs.concise_index_text()
    assert "Website Redesign" in text
    assert "website" in text
    assert "Planning the new homepage" in text


def test_concise_index_never_leaks_file_contents(home):
    """The whole point of the design: the always-visible index is a
    reminder that a project exists, never a preview of its contents.
    If this test ever needs to change, that's a real boundary change,
    not a refactor — worth pausing on."""
    proj_rec = projs.create_project("Secret Project", blurb="A summary line")
    refs.save_reference("sensitive.md", "THIS SHOULD NEVER APPEAR IN THE INDEX",
                        project=proj_rec["proj_id"])
    text = projs.concise_index_text()
    assert "THIS SHOULD NEVER APPEAR" not in text
    assert "sensitive.md" not in text


def test_concise_index_reaches_direct_mode_system_prompt(founded):
    provider, conv_id = founded
    projs.create_project("Direct Mode Test", blurb="Should appear here")
    block = provider.system_prompt_block()
    assert "Direct Mode Test" in block
    assert "Should appear here" in block


def test_concise_index_reaches_hermes_mode_identity_path(founded, tmp_path, monkeypatch):
    """Same content must reach BOTH prompt-construction paths — this is
    the exact class of bug (one path fixed, the other silently not)
    that happened earlier tonight with image_created; guarded here so
    it can't happen again for the project index specifically."""
    monkeypatch.delenv("HERMES_HOME", raising=False)
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    projs.create_project("Hermes Mode Test", blurb="Should also appear here")

    from agent.prompt_builder import load_soul_md
    block = load_soul_md()
    assert "Hermes Mode Test" in block
    assert "Should also appear here" in block


def test_no_hollow_projects_header_when_none_exist(founded):
    """A fresh Seira with no projects yet shouldn't carry an empty
    'LIVING PROJECTS' header for nothing."""
    provider, conv_id = founded
    block = provider.system_prompt_block()
    assert "LIVING PROJECTS" not in block


# ---------------- bridge tool dispatch, end to end ----------------

def test_project_create_tool(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_project_create", {
        "name": "New Effort", "blurb": "Just getting started",
    }))
    assert out["ok"] is True and out["proj_id"].startswith("proj-")


def test_project_list_tool(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_project_create", {"name": "A"})
    provider.handle_tool_call("seira_project_create", {"name": "B"})
    out = json.loads(provider.handle_tool_call("seira_project_list", {}))
    assert len(out["projects"]) == 2


def test_project_recall_tool(founded):
    provider, conv_id = founded
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Recall Test"}))
    provider.handle_tool_call("seira_reference_save", {
        "filename": "a.md", "content": "content here",
        "project": created["proj_id"],
    })
    out = json.loads(provider.handle_tool_call(
        "seira_project_recall", {"project": created["proj_id"]}))
    assert out["ok"] is True and out["file_count"] == 1


def test_reference_save_files_directly_into_project(founded):
    """A document can join a project at the moment it's saved, not
    only retroactively."""
    provider, conv_id = founded
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Direct File"}))
    out = json.loads(provider.handle_tool_call("seira_reference_save", {
        "filename": "note.md", "content": "filed directly",
        "project": created["proj_id"],
    }))
    assert out["ok"] is True
    files = projs.project_files(created["proj_id"])
    assert len(files) == 1


def test_reference_save_with_unknown_project_fails_clearly(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_reference_save", {
        "filename": "note.md", "content": "content",
        "project": "no-such-project",
    }))
    assert out["ok"] is False


def test_create_file_files_directly_into_project(founded):
    provider, conv_id = founded
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Generated Docs"}))
    out = json.loads(provider.handle_tool_call("seira_create_file", {
        "format": "md", "filename": "output", "content": "# Generated\n\ncontent",
        "project": created["proj_id"],
    }))
    assert out["ok"] is True
    files = projs.project_files(created["proj_id"])
    assert len(files) == 1


def test_project_add_reference_tool_retroactive(founded):
    provider, conv_id = founded
    saved = json.loads(provider.handle_tool_call("seira_reference_save", {
        "filename": "earlier.md", "content": "written earlier, no project yet",
    }))
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Grouped After The Fact"}))
    out = json.loads(provider.handle_tool_call("seira_project_add_reference", {
        "ref": saved["ref_id"], "project": created["proj_id"],
    }))
    assert out["ok"] is True
    files = projs.project_files(created["proj_id"])
    assert len(files) == 1 and files[0]["ref_id"] == saved["ref_id"]


def test_project_update_blurb_tool(founded):
    provider, conv_id = founded
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Evolving Project", "initiative": "self"}))
    out = json.loads(provider.handle_tool_call("seira_project_update_blurb", {
        "project": created["proj_id"], "blurb": "Now further along",
    }))
    assert out["ok"] is True and out["blurb"] == "Now further along"


# ---------------- her own initiative: a real, visible, honest record ----------------

def test_initiative_defaults_to_self(home):
    """Every call here IS her own tool use already — the default
    reflects that, but the tool schema still asks explicitly each
    time so stating it is a conscious act, not a rubber stamp."""
    rec = projs.create_project("Something I Started")
    assert rec["initiative"] == "self"


def test_requested_projects_are_marked_distinctly(home):
    rec = projs.create_project("Architect's Request", initiative="requested")
    assert rec["initiative"] == "requested"


def test_invalid_initiative_value_is_rejected(home):
    with pytest.raises(ValueError):
        projs.create_project("Bad Value", initiative="something-else")


def test_list_projects_filters_by_initiative(home):
    projs.create_project("Mine", initiative="self")
    projs.create_project("Asked For", initiative="requested")
    mine = projs.list_projects(initiative="self")
    theirs = projs.list_projects(initiative="requested")
    assert len(mine) == 1 and mine[0]["name"] == "Mine"
    assert len(theirs) == 1 and theirs[0]["name"] == "Asked For"
    assert len(projs.list_projects()) == 2  # unfiltered sees everything


def test_concise_index_marks_self_initiated_projects(home):
    projs.create_project("My Own Thing", initiative="self")
    projs.create_project("Asked-For Thing", initiative="requested")
    text = projs.concise_index_text()
    assert "My Own Thing\" [my-own-thing] (her own initiative)" in text
    assert "Asked-For Thing\" [asked-for-thing]" in text
    assert "Asked-For Thing\" [asked-for-thing] (her own initiative)" not in text


def test_old_records_without_initiative_default_to_self_on_read(home):
    """Records saved before this field existed were, definitionally,
    still her own tool calls — reading them shouldn't require a
    migration, just a safe default."""
    rec = projs.create_project("Legacy Project")
    index = projs._load_index()
    del index[rec["proj_id"]]["initiative"]
    projs._save_index(index)
    reloaded = projs.list_projects(initiative="self")
    assert len(reloaded) == 1


def test_project_create_tool_records_initiative(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_project_create", {
        "name": "Tool Level Test", "initiative": "self",
    }))
    rec = projs.resolve_project(out["proj_id"])
    assert rec["initiative"] == "self"


def test_project_create_tool_defaults_gracefully_if_initiative_omitted(founded):
    """The schema marks initiative required, but a malformed call
    should never crash the turn — same defensive discipline as
    everywhere else in this bridge."""
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_project_create", {
        "name": "No Initiative Given",
    }))
    assert out["ok"] is True


def test_project_list_tool_filters_by_initiative(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_project_create",
                              {"name": "Mine", "initiative": "self"})
    provider.handle_tool_call("seira_project_create",
                              {"name": "Requested", "initiative": "requested"})
    out = json.loads(provider.handle_tool_call(
        "seira_project_list", {"initiative": "self"}))
    assert len(out["projects"]) == 1 and out["projects"][0]["name"] == "Mine"


# ---------------- session summaries / resume: pick up where we left off ----------------

def test_reference_gains_is_summary_flag(home):
    proj_rec = projs.create_project("Checkpoint Test")
    rec = refs.save_reference("session-1.md", "notes from today",
                              project=proj_rec["proj_id"], is_summary=True)
    assert rec["is_summary"] is True


def test_ordinary_reference_defaults_is_summary_false(home):
    rec = refs.save_reference("plain.md", "just a normal document")
    assert rec["is_summary"] is False


def test_session_summaries_lists_only_flagged_documents(home):
    proj_rec = projs.create_project("Mixed Files")
    refs.save_reference("data.md", "raw data", project=proj_rec["proj_id"])
    refs.save_reference("summary-1.md", "session summary", project=proj_rec["proj_id"],
                        is_summary=True)
    summaries = projs.session_summaries(proj_rec["proj_id"])
    assert len(summaries) == 1 and summaries[0]["filename"] == "summary-1.md"


def test_resume_with_no_summary_falls_back_to_manifest_honestly(home):
    proj_rec = projs.create_project("No Checkpoint Yet")
    refs.save_reference("some-doc.md", "content", project=proj_rec["proj_id"])
    result = projs.resume(proj_rec["proj_id"])
    assert result["found"] is True
    assert result["has_session_summary"] is False
    assert "No session summary" in result["note"]
    assert result["mode"] == "manifest"  # the honest fallback, not a fake resume


def test_resume_returns_latest_summary_in_full(home):
    proj_rec = projs.create_project("Ongoing Work")
    refs.save_reference("summary-day1.md", "Day 1: started the outline.",
                        project=proj_rec["proj_id"], is_summary=True)
    refs.save_reference("summary-day2.md", "Day 2: finished the draft, need review next.",
                        project=proj_rec["proj_id"], is_summary=True)
    result = projs.resume(proj_rec["proj_id"])
    assert result["found"] is True and result["has_session_summary"] is True
    assert "Day 2" in result["latest_summary"]["text"]
    assert "need review next" in result["latest_summary"]["text"]


def test_resume_lists_earlier_summaries_for_deeper_history(home):
    proj_rec = projs.create_project("Long Running")
    refs.save_reference("s1.md", "first checkpoint", project=proj_rec["proj_id"],
                        is_summary=True)
    refs.save_reference("s2.md", "second checkpoint", project=proj_rec["proj_id"],
                        is_summary=True)
    refs.save_reference("s3.md", "third and latest checkpoint",
                        project=proj_rec["proj_id"], is_summary=True)
    result = projs.resume(proj_rec["proj_id"])
    assert "third and latest" in result["latest_summary"]["text"]
    assert len(result["earlier_summaries"]) == 2  # s1 and s2, not the latest


def test_resume_of_unknown_project_is_honest(home):
    result = projs.resume("no-such-project")
    assert result["found"] is False


def test_project_resume_tool_end_to_end(founded):
    provider, conv_id = founded
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Resume Tool Test", "initiative": "self"}))
    provider.handle_tool_call("seira_create_file", {
        "format": "md", "filename": "checkpoint",
        "content": "# Where we left off\n\nWaiting on the API design decision.",
        "project": created["proj_id"], "is_summary": True,
    })
    out = json.loads(provider.handle_tool_call(
        "seira_project_resume", {"project": created["proj_id"]}))
    assert out["ok"] is True
    assert "API design decision" in out["latest_summary"]["text"]


def test_create_file_is_summary_flag_reaches_the_reference(founded):
    provider, conv_id = founded
    created = json.loads(provider.handle_tool_call(
        "seira_project_create", {"name": "Flag Check", "initiative": "self"}))
    out = json.loads(provider.handle_tool_call("seira_create_file", {
        "format": "md", "filename": "checkpoint", "content": "content here",
        "project": created["proj_id"], "is_summary": True,
    }))
    rec = refs.resolve_ref(out["reference_tag"])
    assert rec["is_summary"] is True
