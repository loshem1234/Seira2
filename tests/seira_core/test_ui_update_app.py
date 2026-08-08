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
