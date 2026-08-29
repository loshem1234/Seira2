"""App-level tests for the new UI-update backend surface: diary page,
expanded console context, and PDF upload through the real endpoint."""

import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")
pytest.importorskip("fastapi")
pypdf = pytest.importorskip("pypdf")

from fastapi.testclient import TestClient  # noqa: E402

from seira_web.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    app = create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app, follow_redirects=False)
    c.post("/signup", data={"email": "a@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
    return c


def test_diary_page_renders_both_kinds_empty(client):
    r = client.get("/diary")
    assert r.status_code == 200 and "Her diary" in r.text
    r2 = client.get("/diary?kind=architect")
    assert r2.status_code == 200 and "diary of you" in r2.text


def test_diary_shows_real_written_entries(client):
    from seira_web import accounts as acct
    from seira_core.tenancy import tenant_scope
    account = acct.verify_login("a@example.com", "long-enough-password")
    with tenant_scope(account["tenant_id"]):
        from seira_core.diary import DiaryStore
        DiaryStore().write_entry("architect", "He works late; values care over speed.",
                                 ["relational_pattern:psy-00003"])
    page = client.get("/diary?kind=architect").text
    assert "He works late; values care over speed." in page
    assert "relational_pattern:psy-00003" in page


def test_console_exposes_all_tabs_data(client):
    page = client.get("/console").text
    for marker in ("Unity", "Intellect", "Psyche", "Reversion", "Instruments",
                  "Version history", "Convergence"):
        assert marker in page


def _make_text_pdf_bytes() -> bytes:
    import io
    from pypdf import PdfWriter
    from reportlab.pdfgen import canvas  # optional dep check below
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 700, "The vesica piscis holds the point at its center.")
    c.save()
    return buf.getvalue()


def test_pdf_upload_extracts_and_saves_as_reference(client):
    try:
        pdf_bytes = _make_text_pdf_bytes()
    except ImportError:
        pytest.skip("reportlab not installed; covered at unit level in "
                   "test_references_documents.py instead.")
    r = client.post("/api/upload",
                    files={"file": ("clause.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "vesica piscis" in body["text"]
    assert body["ref_id"].startswith("ref-")


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setenv("SEIRA_MAX_UPLOAD_BYTES" if False else "X", "")  # no-op guard
    import seira_web.documents as docs
    monkeypatch.setattr(docs, "MAX_UPLOAD_BYTES", 10)  # force a tiny ceiling
    r = client.post("/api/upload",
                    files={"file": ("big.txt", b"way more than ten bytes", "text/plain")})
    assert r.status_code == 400 and "too large" in r.json()["error"]


def test_web_search_is_on_by_default_without_any_toggle(client, monkeypatch):
    """The standing-capability change: no 'web_search' field sent at all
    must still reach the model with the tool present."""
    import seira_web.app as appmod

    seen = {}

    class RecordingLLM:
        def complete(self, system, messages, tools):
            seen["tools"] = tools
            return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

    app = appmod.create_app(llm_client_factory=lambda model=None: RecordingLLM())
    from fastapi.testclient import TestClient
    c = TestClient(app, follow_redirects=False)
    c.post("/signup", data={"email": "b@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
    r = c.post("/api/chat", json={"action": "send", "message": "hi"})  # no web_search key at all
    assert r.json()["ok"] is True
    assert any(t.get("name") == "web_search" for t in seen["tools"])


def test_web_search_org_level_kill_switch(client, monkeypatch):
    import seira_web.app as appmod
    monkeypatch.setattr(appmod, "WEB_SEARCH_GLOBALLY_ENABLED", False)

    seen = {}

    class RecordingLLM:
        def complete(self, system, messages, tools):
            seen["tools"] = tools
            return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

    app = appmod.create_app(llm_client_factory=lambda model=None: RecordingLLM())
    from fastapi.testclient import TestClient
    c = TestClient(app, follow_redirects=False)
    c.post("/signup", data={"email": "c@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
    r = c.post("/api/chat", json={"action": "send", "message": "hi", "web_search": True})
    assert r.json()["ok"] is True
    assert not any(t.get("name") == "web_search" for t in seen["tools"])


def test_only_chat_page_locks_page_scroll(client):
    """Regression: console (and every other page) must scroll normally.
    Only the chat shell opts into the body-scroll lock."""
    chat_body = client.get("/").text
    console_body = client.get("/console").text
    diary_body = client.get("/diary").text
    assert '<body class="locked">' in chat_body
    assert '<body class="locked">' not in console_body
    assert '<body class="">' in console_body or '<body class="">' in diary_body


def test_chat_page_has_mobile_drawer_backdrop(client):
    """Regression for the mobile sidebar bug: the backdrop element must
    exist so the drawer has a dimming layer and a tap-to-close target."""
    body = client.get("/").text
    assert 'id="backdrop"' in body
    assert 'id="edgetab"' in body


def test_stylesheet_url_is_cache_busted_and_content_addressed(client, tmp_path, monkeypatch):
    """The actual root-cause fix: the stylesheet URL must change whenever
    its content does, so browsers/edges can never serve a stale version
    at a URL that looks unchanged."""
    import re
    body = client.get("/").text
    m = re.search(r'/static/style\.css\?v=([a-f0-9]{12})', body)
    assert m, "stylesheet link must carry a content version query param"
    v1 = m.group(1)

    import seira_web.app as appmod
    css_path = appmod._HERE / "static" / "style.css"
    original = css_path.read_text()
    try:
        css_path.write_text(original + "\n/* changed */\n")
        app2 = appmod.create_app(llm_client_factory=lambda model=None: None)
        from fastapi.testclient import TestClient
        c2 = TestClient(app2, follow_redirects=False)
        c2.post("/signup", data={"email": "z@example.com", "password": "long-enough-password"})
        c2.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
        body2 = c2.get("/").text
        v2 = re.search(r'/static/style\.css\?v=([a-f0-9]{12})', body2).group(1)
        assert v2 != v1  # content changed -> URL changed -> cache is bypassed
    finally:
        css_path.write_text(original)


def test_image_upload_works_even_with_generic_content_type(client):
    """The actual reported bug's likely cause: some mobile browsers send
    a generic/missing content_type for images. Extension must be a
    reliable fallback."""
    r = client.post("/api/upload", files={
        "file": ("photo.png", b"\x89PNG fake bytes", "application/octet-stream"),
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["kind"] == "image"


def test_heic_upload_gets_a_clear_actionable_error(client):
    r = client.post("/api/upload", files={
        "file": ("IMG_1234.HEIC", b"fake heic bytes", "image/heic"),
    })
    assert r.status_code == 400
    assert "HEIC" in r.json()["error"]


def test_image_tag_prompt_persists_through_upload(client):
    r = client.post("/api/upload", data={"tag": "my portrait ref"}, files={
        "file": ("selfie.jpg", b"\xff\xd8 fake jpeg bytes", "image/jpeg"),
    })
    assert r.status_code == 200
    assert r.json()["tag"] == "my-portrait-ref"


def test_image_serving_endpoint_returns_real_bytes(client):
    r = client.post("/api/upload", files={
        "file": ("cat.png", b"real png bytes here", "image/png"),
    })
    img_id = r.json()["img_id"]
    r2 = client.get(f"/api/images/{img_id}")
    assert r2.status_code == 200
    assert r2.content == b"real png bytes here"
    assert r2.headers["content-type"] == "image/png"


def test_image_serving_by_tag_also_works(client):
    client.post("/api/upload", data={"tag": "my portrait ref"}, files={
        "file": ("p.png", b"portrait bytes", "image/png"),
    })
    r = client.get("/api/images/my-portrait-ref")
    assert r.status_code == 200 and r.content == b"portrait bytes"


def test_image_appears_inline_in_chat_history_after_reload(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform2"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants2"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)

    class StubLLM:
        def complete(self, system, messages, tools):
            return {"content": [{"type": "text", "text": "I see it."}],
                    "stop_reason": "end_turn"}

    app = appmod.create_app(llm_client_factory=lambda model=None: StubLLM())
    c = TestClient(app, follow_redirects=False)
    c.post("/signup", data={"email": "img@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})

    r = c.post("/api/upload", files={"file": ("cat.png", b"cat bytes", "image/png")})
    img_id = r.json()["img_id"]
    c.post("/api/chat", json={
        "action": "send", "message": "what is this",
        "attachment": {"kind": "image", "name": "cat.png", "img_id": img_id},
    })
    page = c.get("/").text
    assert f'/api/images/{img_id}' in page
    assert '<img class="chatimg"' in page


def test_rename_conversation(client):
    r = client.post("/api/conversations")
    conv_id = r.json()["conv_id"]
    r2 = client.post(f"/api/conversations/{conv_id}/rename",
                     json={"title": "About the Archivum"})
    assert r2.status_code == 200 and r2.json()["title"] == "About the Archivum"
    page = client.get("/").text
    assert "About the Archivum" in page


def test_rename_empty_title_refused(client):
    r = client.post("/api/conversations")
    conv_id = r.json()["conv_id"]
    r2 = client.post(f"/api/conversations/{conv_id}/rename", json={"title": "  "})
    assert r2.status_code == 400


def test_rename_nonexistent_conversation(client):
    r = client.post("/api/conversations/c-doesnotexist/rename",
                    json={"title": "x"})
    assert r.status_code == 404


def test_archive_hides_from_sidebar_but_keeps_transcript(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient
    from seira_web import conversations as convs
    from seira_web import accounts as acct
    from seira_core.tenancy import tenant_scope

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform3"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants3"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)

    class StubLLM:
        def complete(self, system, messages, tools):
            return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

    app = appmod.create_app(llm_client_factory=lambda model=None: StubLLM())
    c = TestClient(app, follow_redirects=False)
    c.post("/signup", data={"email": "arch@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})

    r = c.post("/api/conversations")
    conv_id = r.json()["conv_id"]
    c.post("/api/chat", json={"action": "send", "conv_id": conv_id,
                              "message": "a real message"})
    r2 = c.post(f"/api/conversations/{conv_id}/archive")
    assert r2.status_code == 200

    page = c.get("/").text
    assert "a real message" not in page

    account = acct.verify_login("arch@example.com", "long-enough-password")
    with tenant_scope(account["tenant_id"]):
        visible = [x["conv_id"] for x in convs.list_conversations()]
        all_convs = [x["conv_id"] for x in convs.list_conversations(include_archived=True)]
        records = convs.records(conv_id)
    assert conv_id not in visible
    assert conv_id in all_convs  # never actually gone
    assert any(rec["text"] == "a real message" for rec in records if rec["kind"] == "user")


def test_archive_nonexistent_conversation(client):
    r = client.post("/api/conversations/c-doesnotexist/archive")
    assert r.status_code == 404


def test_signups_open_by_default(client):
    r = client.post("/signup", data={"email": "new@example.com",
                                     "password": "long-enough-password"})
    assert r.status_code == 303  # succeeds, redirects to onboarding


def test_signups_can_be_closed(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform4"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants4"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.setenv("SEIRA_SIGNUPS_ENABLED", "0")

    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app, follow_redirects=False)

    r_get = c.get("/signup")
    assert r_get.status_code == 403
    assert "closed" in r_get.text

    r_post = c.post("/signup", data={"email": "blocked@example.com",
                                     "password": "long-enough-password"})
    assert r_post.status_code == 403
    from seira_web import accounts as acct
    assert acct.verify_login("blocked@example.com", "long-enough-password") is None


def test_existing_login_unaffected_when_signups_closed(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform5"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants5"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)

    # Signups open, create the real account first...
    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app, follow_redirects=False)
    c.post("/signup", data={"email": "existing@example.com",
                            "password": "long-enough-password"})
    c.post("/logout")

    # ...then close signups and confirm login still works normally.
    monkeypatch.setenv("SEIRA_SIGNUPS_ENABLED", "0")
    r = c.post("/login", data={"email": "existing@example.com",
                               "password": "long-enough-password"})
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_login_page_hides_signup_link_when_closed(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform6"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants6"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.setenv("SEIRA_SIGNUPS_ENABLED", "0")

    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app, follow_redirects=False)
    page = c.get("/login").text
    assert 'href="/signup"' not in page


def test_healthz_reports_signups_status(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform7"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants7"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.setenv("SEIRA_SIGNUPS_ENABLED", "0")

    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app)
    assert c.get("/healthz").json()["signups_enabled"] is False


def test_admin_route_404s_when_no_token_configured(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform8"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants8"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.delenv("SEIRA_ADMIN_TOKEN", raising=False)
    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app)
    r = c.get("/api/admin/tenants")
    assert r.status_code == 404  # not 401 — doesn't even hint it exists


def test_admin_route_requires_correct_token(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform9"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants9"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.setenv("SEIRA_ADMIN_TOKEN", "the-real-secret")
    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app)

    r_none = c.get("/api/admin/tenants")
    assert r_none.status_code == 401
    r_wrong = c.get("/api/admin/tenants", headers={"x-admin-token": "guess"})
    assert r_wrong.status_code == 401


def test_admin_route_lists_every_account_with_real_founding_status(tmp_path, monkeypatch):
    import seira_web.app as appmod
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform10"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants10"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.setenv("SEIRA_ADMIN_TOKEN", "the-real-secret")
    app = appmod.create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app, follow_redirects=False)

    c.post("/signup", data={"email": "founded@example.com", "password": "long-enough-password"})
    c.post("/onboard", data={"telos": "t", "relation": "r", "self_model": "s"})
    c2 = TestClient(app, follow_redirects=False)
    c2.post("/signup", data={"email": "unfounded@example.com", "password": "long-enough-password"})
    # deliberately does NOT complete onboarding — a real "stray" case

    r = c.get("/api/admin/tenants", headers={"x-admin-token": "the-real-secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["total_accounts"] == 2
    by_email = {a["email"]: a for a in body["accounts"]}
    assert by_email["founded@example.com"]["seira_founded"] is True
    assert by_email["founded@example.com"]["halted"] is False
    assert by_email["unfounded@example.com"]["seira_founded"] is False
