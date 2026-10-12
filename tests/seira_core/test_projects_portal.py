"""The Projects tab: filing conversations and documents, creating
projects, new chat inside a project, and the chat page's project hooks."""
import hashlib
import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from seira_core.tenancy import tenant_scope  # noqa: E402

TOKEN = "t0k"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("SEIRA_ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("SEIRA_ADMIN_TENANT_ID", "t-test")
    from seira_web.app import create_app
    c = TestClient(create_app(), follow_redirects=False)
    c.cookies.set("seira_admin_session",
                  hashlib.sha256(f"seira-admin-session-v1:{TOKEN}".encode()).hexdigest())
    c.tenant = "t-test"
    return c


def test_create_file_chat_and_remove(client):
    from seira_web import conversations as convs, projects as projs, references as refs
    r = client.post("/api/projects", json={"name": "Proclus", "blurb": "Elements"})
    pid = r.json()["proj_id"]
    with tenant_scope(client.tenant):
        assert projs.resolve_project(pid)["initiative"] == "requested"
        conv = convs.create_conversation("Old chat")
        ref = refs.save_reference("notes.md", "hello world")
    cid = conv["conv_id"]

    assert client.post(f"/api/conversations/{cid}/project", json={"proj_id": pid}).json()["ok"]
    assert client.post(f"/api/projects/{pid}/files/{ref['ref_id']}").json()["ok"]
    new_chat = client.post(f"/api/projects/{pid}/conversations").json()["conv_id"]

    page = client.get(f"/projects/{pid}")
    assert page.status_code == 200 and "Old chat" in page.text and "notes.md" in page.text
    grid = client.get("/projects")
    assert "Proclus" in grid.text and "2 chats" in grid.text and "1 file" in grid.text

    with tenant_scope(client.tenant):
        assert {c["conv_id"] for c in projs.project_conversations(pid)} == {cid, new_chat}
    assert client.post(f"/api/conversations/{cid}/project", json={"proj_id": None}).json()["ok"]
    assert client.delete(f"/api/projects/{pid}/files/{ref['ref_id']}").json()["ok"]
    with tenant_scope(client.tenant):
        assert [c["conv_id"] for c in projs.project_conversations(pid)] == [new_chat]
        assert projs.project_files(pid) == []


def test_rename_blurb_upload_and_errors(client):
    pid = client.post("/api/projects", json={"name": "A"}).json()["proj_id"]
    d = client.post(f"/api/projects/{pid}/update", json={"name": "B", "blurb": "bb"}).json()
    assert d["name"] == "B" and d["blurb"] == "bb"
    up = client.post(f"/api/projects/{pid}/upload", files={"file": ("x.txt", b"some text")})
    assert up.json()["ok"]
    assert "x.txt" in client.get(f"/projects/{pid}").text
    assert client.post(f"/api/projects/{pid}/upload",
                       files={"file": ("x.exe", b"zz")}).status_code == 400
    assert client.post("/api/projects", json={"name": "  "}).status_code == 400
    assert client.post("/api/conversations/c-nope/project", json={"proj_id": pid}).status_code == 404
    assert client.get("/projects/nope").status_code == 404
    assert client.post("/api/conversations/c-x/project", json={"proj_id": "nope"}).status_code == 404


def test_login_required(client):
    client.cookies.clear()
    assert client.get("/projects").status_code == 307


def test_chat_page_carries_project_hooks(client):
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    from seira_web import conversations as convs
    pid = client.post("/api/projects", json={"name": "Proc"}).json()["proj_id"]
    with tenant_scope(client.tenant):
        perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
        perform_psyche_genesis([{"category": "self_model", "content": "x"}], architect="L")
        conv = convs.create_conversation("Filed")
        from seira_web import projects as _p
        _p.set_conversation_project(conv["conv_id"], pid)
    html = client.get(f"/?c={conv['conv_id']}").text
    assert f'data-project="{pid}"' in html and "act-project" in html
    assert '"name": "Proc"' in html or '"name":"Proc"' in html
