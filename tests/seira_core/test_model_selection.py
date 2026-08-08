"""Model selection and length preference reach the LLM client and the
system prompt respectively — the backend half of the UI update."""

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


class RecordingLLM:
    def __init__(self, model=None):
        self.model = model
        self.seen_system = None

    def complete(self, system, messages, tools):
        self.seen_system = system
        return {"content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    seen = {}

    def factory(model=None):
        llm = RecordingLLM(model)
        seen["last"] = llm
        return llm

    app = create_app(llm_client_factory=factory)
    c = TestClient(app, follow_redirects=False)
    c.seen = seen
    c.post("/signup", data={"email": "a@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
    return c


def test_model_selection_reaches_the_client(client):
    r = client.post("/api/chat", json={"action": "send",
                                       "message": "hi", "model": "claude-opus-4-8"})
    assert r.json()["ok"] is True
    assert client.seen["last"].model == "claude-opus-4-8"


def test_no_model_selection_falls_back_to_default(client):
    client.post("/api/chat", json={"action": "send", "message": "hi"})
    assert client.seen["last"].model is None  # factory itself applies the default


def test_length_preference_is_added_to_the_system_prompt(client):
    client.post("/api/chat", json={"action": "send", "message": "hi",
                                   "length_pref": "short"})
    system = client.seen["last"].seen_system
    assert "100 characters" in system
    client.post("/api/chat", json={"action": "send", "message": "hi again",
                                   "length_pref": "full"})
    system2 = client.seen["last"].seen_system
    assert "RESPONSE LENGTH PREFERENCE" not in system2


def test_chat_page_exposes_model_choices(client):
    body = client.get("/").text
    assert "claude-sonnet-5" in body and "claude-opus-4-8" in body
