"""Her voice: text prep, chunking, the Gemini call shape, caching, routes."""
import base64
import hashlib
import io
import sys
import wave
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


def _wav(frames=b"\x01\x00" * 2400):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(frames)
    return b.getvalue()


class FakeResp:
    def __init__(self, code=200, js=None):
        self.status_code = code; self._js = js or {}; self.text = str(js)
    def json(self):
        return self._js


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("SEIRA_ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("SEIRA_ADMIN_TENANT_ID", "t-test")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("SEIRA_VOICE_ID", raising=False)
    from seira_web.app import create_app
    c = TestClient(create_app(), follow_redirects=False)
    c.cookies.set("seira_admin_session",
                  hashlib.sha256(f"seira-admin-session-v1:{TOKEN}".encode()).hexdigest())
    return c


def test_speakable_drops_code_links_markdown():
    from seira_web import voice
    t = voice.speakable("# Hi\n**Bold** and [a link](http://x.y).\n```py\nx=1\n```\n- one")
    assert "x=1" not in t and "http" not in t and "**" not in t and "#" not in t
    assert "a link" in t and "Bold" in t and "one" in t


def test_chunking_respects_limit_and_loses_nothing():
    from seira_web import voice
    text = " ".join(f"Sentence number {i} goes here." for i in range(300))
    parts = voice.chunk_text(text, 400)
    assert all(len(p) <= 400 for p in parts) and len(parts) > 5
    assert " ".join(parts).replace("\n\n", " ").split() == text.split()
    assert voice.chunk_text("x" * 5000, 400)  # one unbroken word still splits


def test_request_shape_and_audio_extraction(monkeypatch):
    from seira_web import voice
    seen = {}
    def post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return FakeResp(200, {"steps": [{"type": "model_output", "content": [
            {"type": "audio", "data": base64.b64encode(_wav()).decode()}]}]})
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setattr(voice.httpx, "post", post)
    pcm = voice.synthesize_chunk("Hello.", "voice_abc", "warm", "gemini-3.8-flash-tts")
    assert len(pcm) == 4800
    b = seen["body"]
    assert seen["url"].endswith("/interactions") and seen["headers"]["x-goog-api-key"] == "secret"
    assert b["generation_config"]["speech_config"] == [{"voice": "voice_abc"}]
    assert b["input"][0]["content"][0]["annotations"][0] == {"type": "speech_metadata", "style": "warm"}
    assert b["response_format"] == {"type": "audio"}


def test_raw_pcm_is_accepted(monkeypatch):
    from seira_web import voice
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(voice.httpx, "post", lambda *a, **k: FakeResp(200, {"steps": [
        {"type": "model_output", "content": [{"type": "audio", "data": base64.b64encode(b"\x00\x01" * 100).decode()}]}]}))
    assert len(voice.synthesize_chunk("x", "v", "", "m")) == 200


def test_google_error_is_readable(monkeypatch):
    from seira_web import voice
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(voice.httpx, "post", lambda *a, **k: FakeResp(403, {"error": {"message": "billing off"}}))
    with pytest.raises(voice.VoiceError, match="billing off"):
        voice.synthesize_chunk("x", "v", "", "m")


def test_routes_speak_cache_and_audio(client, monkeypatch):
    from seira_web import voice
    calls = []
    def post(url, headers=None, json=None, timeout=None):
        calls.append(json["input"][0]["content"][0]["text"])
        return FakeResp(200, {"steps": [{"type": "model_output", "content": [
            {"type": "audio", "data": base64.b64encode(_wav()).decode()}]}]})
    monkeypatch.setattr(voice.httpx, "post", post)

    assert client.get("/api/voice/status").json()["ready"] is False
    assert "voice" in client.post("/api/voice/speak", json={"text": "Hi."}).json()["error"].lower()
    assert client.post("/api/voice/settings", json={"voice_id": "bad id!"}).status_code == 400
    st = client.post("/api/voice/settings", json={"voice_id": "voice_abc", "style": "calm"}).json()
    assert st["ready"] and st["voice_id"] == "voice_abc"

    a = client.post("/api/voice/speak", json={"text": "Hello there. How are you?"}).json()
    assert a["cached"] is False and a["url"].startswith("/api/voice/audio/")
    b = client.post("/api/voice/speak", json={"text": "Hello there. How are you?"}).json()
    assert b["cached"] is True and b["url"] == a["url"] and len(calls) == 1   # paid once
    got = client.get(a["url"])
    assert got.status_code == 200 and len(got.content) > 100
    assert client.get("/api/voice/audio/../../etc/passwd").status_code in (404, 422)
    assert client.get("/api/voice/audio/" + "0" * 40 + ".mp3").status_code == 404
    # changing the voice changes the cache key
    client.post("/api/voice/settings", json={"voice_id": "voice_other"})
    c = client.post("/api/voice/speak", json={"text": "Hello there. How are you?"}).json()
    assert c["url"] != a["url"] and len(calls) == 2


def test_voice_list_orders_created_first(client, monkeypatch):
    from seira_web import voice
    monkeypatch.setattr(voice.httpx, "get", lambda *a, **k: FakeResp(200, {"voices": [
        {"id": "Kore", "display_name": "Kore", "type": "prebuilt"},
        {"id": "voice_1", "display_name": "Seira", "type": "prompted"}]}))
    v = client.get("/api/voice/voices").json()["voices"]
    assert v[0]["id"] == "voice_1"
