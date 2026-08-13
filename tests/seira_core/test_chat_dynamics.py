"""Phase W2 tests — the dynamic chat: conversations, supersession
(nothing deleted, Art. 23), regenerate/edit, live-event stream, upload.
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
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from seira_web.app import create_app  # noqa: E402


class EchoLLM:
    """Answers deterministically with a text reply derived from the last
    user message; never calls tools. Counts calls for regenerate tests."""

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools):
        self.calls += 1
        last_user = ""
        for m in reversed(messages):
            if m["role"] == "user" and isinstance(m["content"], str):
                last_user = m["content"]
                break
        return {"content": [
            {"type": "text", "text": f"answer#{self.calls} to: {last_user[:60]}"},
        ], "stop_reason": "end_turn"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    llm = EchoLLM()
    app = create_app(llm_client_factory=lambda model=None: llm)
    c = TestClient(app, follow_redirects=False)
    c.llm = llm
    c.post("/signup", data={"email": "a@example.com",
                            "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
    return c


def _conv_id(client):
    r = client.post("/api/conversations")
    return r.json()["conv_id"]


def test_conversations_are_separate_threads(client):
    c1, c2 = _conv_id(client), _conv_id(client)
    r1 = client.post("/api/chat", json={"action": "send", "conv_id": c1,
                                        "message": "about the moon"}).json()
    r2 = client.post("/api/chat", json={"action": "send", "conv_id": c2,
                                        "message": "about the sea"}).json()
    page1 = client.get(f"/?c={c1}").text
    # c1's page shows c1's exchange; c2's REPLY never leaks into c1's thread.
    # (Both titles appear in the sidebar by design — that's what history is.)
    assert "about the moon" in page1 and r1["reply"] in page1
    assert r2["reply"] not in page1


def test_regenerate_supersedes_without_deleting(client):
    cid = _conv_id(client)
    r1 = client.post("/api/chat", json={"action": "send", "conv_id": cid,
                                        "message": "hello"}).json()
    r2 = client.post("/api/chat", json={"action": "regenerate",
                                        "conv_id": cid}).json()
    assert r2["reply"].startswith("answer#") and r2["reply"] != r1["reply"]
    # Live thread shows only the new answer…
    from seira_web import conversations as convs
    from seira_core.tenancy import tenant_scope
    from seira_web import accounts as acct
    account = acct.verify_login("a@example.com", "long-enough-password")
    with tenant_scope(account["tenant_id"]):
        live = convs.display_records(cid)
        raw = convs.records(cid)
    live_assistant = [r for r in live if r["kind"] == "assistant"]
    assert len(live_assistant) == 1 and live_assistant[0]["text"] == r2["reply"]
    # …but the superseded answer is still in the raw record (Art. 23):
    raw_assistant = [r for r in raw if r["kind"] == "assistant"]
    assert len(raw_assistant) == 2
    assert any(r["kind"] == "supersede_from" for r in raw)


def test_edit_forks_and_preserves_the_abandoned_branch(client):
    cid = _conv_id(client)
    client.post("/api/chat", json={"action": "send", "conv_id": cid,
                                   "message": "first question"})
    from seira_web import conversations as convs
    from seira_core.tenancy import tenant_scope
    from seira_web import accounts as acct
    account = acct.verify_login("a@example.com", "long-enough-password")
    with tenant_scope(account["tenant_id"]):
        user_id = convs.last_live_user(cid)["id"]
    r = client.post("/api/chat", json={"action": "edit", "conv_id": cid,
                                       "target_id": user_id,
                                       "new_text": "better question"}).json()
    assert "better question" in r["reply"]
    with tenant_scope(account["tenant_id"]):
        live = convs.display_records(cid)
        raw = convs.records(cid)
    assert [x["text"] for x in live if x["kind"] == "user"] == ["better question"]
    assert any(x.get("text") == "first question" for x in raw)  # branch kept


def test_stream_emits_real_activity_then_reply(client):
    cid = _conv_id(client)
    with client.stream("POST", "/api/chat/stream",
                       json={"action": "send", "conv_id": cid,
                             "message": "hello stream"}) as resp:
        assert resp.status_code == 200
        events = []
        buf = ""
        for chunk in resp.iter_text():
            buf += chunk
            while "\n\n" in buf:
                part, buf = buf.split("\n\n", 1)
                if part.startswith("data: "):
                    events.append(json.loads(part[6:]))
    kinds = [e["event"] for e in events]
    assert kinds[0] == "phase"           # "Reading who she is"
    assert "reply" in kinds and kinds[-1] == "done"
    reply = next(e for e in events if e["event"] == "reply")
    assert reply["text"].startswith("answer#")


def test_upload_txt_and_refuse_unsupported_type(client):
    r = client.post("/api/upload",
                    files={"file": ("notes.txt", b"the moon is a harsh mistress",
                                    "text/plain")})
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.post("/api/upload",
                    files={"file": ("archive.zip", b"PK\x03\x04...",
                                    "application/zip")})
    assert r.status_code == 400
    r = client.post("/api/upload",
                    files={"file": ("bad.txt", b"\xff\xfe\x00broken",
                                    "text/plain")})
    assert r.status_code == 400  # not UTF-8


def test_attachment_reaches_the_model_and_the_record(client):
    cid = _conv_id(client)
    r = client.post("/api/chat", json={
        "action": "send", "conv_id": cid, "message": "what does it say?",
        "attachment": {"name": "notes.txt", "text": "the vesica holds the point"},
    }).json()
    assert "vesica holds the point" in r["reply"]  # EchoLLM saw the content
    page = client.get(f"/?c={cid}").text
    assert "Received: notes.txt" in page
