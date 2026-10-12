"""List ordering (only a real prompt reorders), splitting a conversation,
and higher projects."""
import hashlib
import sys
import time
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break

from seira_web import conversations as convs  # noqa: E402
from seira_web import projects as projs  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    return tmp_path


def _order():
    return [c["title"] for c in convs.list_conversations()]


def test_only_a_human_prompt_reorders_the_list(home):
    old = convs.create_conversation("old")
    time.sleep(0.01)
    new = convs.create_conversation("new")
    assert _order() == ["new", "old"]
    # background activity on the old chat: autonomous turn, assistant reply,
    # rename, project filing — none may bring it to the top
    time.sleep(0.01)
    convs.append(old["conv_id"], "user", text="go", autonomous=True)
    convs.append(old["conv_id"], "assistant", text="ok", autonomous=True)
    convs.touch(old["conv_id"])
    convs.rename_conversation(old["conv_id"], "old renamed")
    projs_id = projs.create_project("P")["proj_id"]
    projs.set_conversation_project(old["conv_id"], projs_id)
    assert _order() == ["new", "old renamed"]
    # but "updated" (the activity stamp) still moves, so summaries/recollection see it
    rec = [c for c in convs.list_conversations() if c["conv_id"] == old["conv_id"]][0]
    assert rec["updated"] > rec["listed_at"]
    # a real prompt does reorder
    time.sleep(0.01)
    convs.append(old["conv_id"], "user", text="hello")
    convs.touch(old["conv_id"])
    assert _order() == ["old renamed", "new"]


def test_legacy_conversations_keep_their_order(home):
    a = convs.create_conversation("a")
    b = convs.create_conversation("b")
    idx = convs._load_index()
    for k in idx.values():
        k.pop("listed_at", None)
    idx[a["conv_id"]]["updated"] = "2026-01-02T00:00:00+00:00"
    idx[b["conv_id"]]["updated"] = "2026-01-01T00:00:00+00:00"
    convs._save_index(idx)
    assert _order() == ["a", "b"]


def _chat():
    c = convs.create_conversation("Mixed")
    cid = c["conv_id"]
    for i, (k, t) in enumerate([("user", "topic A q"), ("assistant", "A a"),
                                ("user", "topic B q"), ("assistant", "B a"),
                                ("user", "B again"), ("assistant", "B more")]):
        convs.append(cid, k, text=t)
    return cid


def test_split_moves_tail_to_new_conversation_without_deleting(home):
    from seira_web.conversation_split import split_conversation
    cid = _chat()
    pid = projs.create_project("Proj")["proj_id"]
    projs.set_conversation_project(cid, pid)
    new = split_conversation(cid, 3)
    assert [r["text"] for r in convs.display_records(cid)] == ["topic A q", "A a"]
    moved = convs.display_records(new["conv_id"])
    assert [r["text"] for r in moved] == ["topic B q", "B a", "B again", "B more"]
    assert [r["id"] for r in moved] == [1, 2, 3, 4]          # renumbered
    idx = {c["conv_id"]: c for c in convs.list_conversations()}
    assert idx[new["conv_id"]]["project"] == pid               # inherits project
    assert idx[new["conv_id"]]["split_from"]["conv_id"] == cid
    assert idx[cid]["split_to"] == [new["conv_id"]]
    # nothing deleted: the original file still holds every record
    assert len([r for r in convs.records(cid) if r["kind"] in ("user", "assistant")]) == 6
    # the new thread keeps working: model history sees only its own part
    assert [m["content"] for m in convs.model_history(new["conv_id"])][0] == "topic B q"
    # split the new one again to carve out a third topic
    third = split_conversation(new["conv_id"], 3)
    assert [r["text"] for r in convs.display_records(third["conv_id"])] == ["B again", "B more"]


def test_split_refuses_bad_targets(home):
    from seira_web.conversation_split import split_conversation
    cid = _chat()
    with pytest.raises(ValueError):
        split_conversation(cid, 1)       # nothing would stay behind
    with pytest.raises(ValueError):
        split_conversation(cid, 2)       # not one of his own messages
    with pytest.raises(ValueError):
        split_conversation(cid, 99)


def test_higher_projects_rules_and_manifest(home):
    a = projs.create_project("Proclus", blurb="Elements")["proj_id"]
    b = projs.create_project("Damascius")["proj_id"]
    c = projs.create_project("Iamblichus")["proj_id"]
    projs.set_parent(b, a)
    projs.set_parent(c, a)
    assert {p["proj_id"] for p in projs.children_of(a)} == {b, c}
    with pytest.raises(ValueError):
        projs.set_parent(a, b)           # a has children, can't move under another
    with pytest.raises(ValueError):
        projs.set_parent(a, a)
    d = projs.create_project("Deep")["proj_id"]
    with pytest.raises(ValueError):
        projs.set_parent(d, b)           # b is already inside a: one level only
    text = projs.concise_index_text()
    assert "[higher project: 2 inside]" in text
    lines = text.splitlines()
    top = next(i for i, l in enumerate(lines) if l.startswith('- "Proclus"'))
    assert any(l.startswith('  - "Damascius"') for l in lines[top + 1:top + 4])
    assert not any(l.startswith('- "Damascius"') for l in lines)   # nested, not top-level
    projs.set_parent(b, None)
    assert any(l.startswith('- "Damascius"') for l in projs.concise_index_text().splitlines())


def test_portal_routes_for_split_and_groups(home, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from seira_core.tenancy import tenant_scope
    monkeypatch.setenv("SEIRA_ADMIN_TOKEN", "t0k")
    monkeypatch.setenv("SEIRA_ADMIN_TENANT_ID", "t-test")
    from seira_web.app import create_app
    cl = TestClient(create_app(), follow_redirects=False)
    cl.cookies.set("seira_admin_session",
                   hashlib.sha256(b"seira-admin-session-v1:t0k").hexdigest())
    a = cl.post("/api/projects", json={"name": "Higher"}).json()["proj_id"]
    b = cl.post("/api/projects", json={"name": "Lower"}).json()["proj_id"]
    assert cl.post(f"/api/projects/{b}/parent", json={"parent_id": a}).json()["ok"]
    assert cl.post(f"/api/projects/{a}/parent", json={"parent_id": b}).status_code == 400
    grid = cl.get("/projects").text
    assert "higher project" in grid and "Lower" in grid
    assert "Part of" in cl.get(f"/projects/{b}").text
    assert "Projects inside it" in cl.get(f"/projects/{a}").text
    with tenant_scope("t-test"):
        cid = _chat()
    r = cl.post(f"/api/conversations/{cid}/split", json={"target_id": 3, "title": "B topic"})
    assert r.json()["ok"]
    assert cl.post(f"/api/conversations/{cid}/split", json={"target_id": 1}).status_code == 400
