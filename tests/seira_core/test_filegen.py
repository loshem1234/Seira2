"""File generation tests — md, docx, pdf, code."""

import pytest

from seira_web.filegen import FileGenError, create_file, get_output_path, list_outputs


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


def test_markdown_creation(home):
    rec = create_file("md", "notes", "# Title\n\nBody text.\n\n- a\n- b")
    assert rec["filename"] == "notes.md"
    path = get_output_path(rec["out_id"])
    assert path.exists() and "# Title" in path.read_text()


def test_docx_creation_and_no_double_extension(home):
    rec = create_file("docx", "report.docx", "# Report\n\nParagraph.\n\n- one\n- two")
    assert rec["filename"] == "report.docx"  # not report.docx.docx
    path = get_output_path(rec["out_id"])
    assert path.exists() and path.stat().st_size > 0
    from docx import Document
    doc = Document(str(path))
    assert any("Report" in p.text for p in doc.paragraphs)


def test_pdf_creation(home):
    rec = create_file("pdf", "summary", "# Summary\n\nBody text here.\n\n- item a\n- item b")
    path = get_output_path(rec["out_id"])
    assert path.exists() and path.read_bytes()[:4] == b"%PDF"


def test_code_creation_resolves_extension(home):
    rec = create_file("code", "script", "print('hi')", language="python")
    assert rec["filename"] == "script.py"
    rec2 = create_file("code", "app", "console.log('hi')", language="javascript")
    assert rec2["filename"] == "app.js"
    rec3 = create_file("code", "notes", "plain text", language="")
    assert rec3["filename"] == "notes.txt"


def test_empty_content_refused(home):
    with pytest.raises(FileGenError):
        create_file("md", "empty", "   ")


def test_bad_format_refused(home):
    with pytest.raises(FileGenError):
        create_file("xlsx", "sheet", "content")


def test_list_outputs_ordered_newest_first(home):
    create_file("md", "first", "content one")
    create_file("md", "second", "content two")
    listed = list_outputs()
    assert [r["filename"] for r in listed] == ["second.md", "first.md"]


def test_filename_cannot_cause_path_traversal(home):
    """The DISPLAY filename may contain odd characters after sanitizing,
    but the actual on-disk path is always the random out_id — user input
    never reaches the filesystem path directly."""
    from seira_web.filegen import _outputs_dir
    rec = create_file("md", "../../etc/passwd", "content")
    assert "/" not in rec["filename"]
    written_path = get_output_path(rec["out_id"]).resolve()
    assert written_path.parent == _outputs_dir().resolve()


def test_file_created_event_fires_with_real_download_path(home):
    """Chat-loop-level: seira_create_file must emit a distinct
    file_created SSE event carrying a real, working download_path —
    not just a generic tool chip."""
    import sys
    from pathlib import Path
    for c in [Path(__file__).resolve().parents[2],
             Path("/home/claude/repo/hermes-agent-main")]:
        if (c / "agent" / "memory_provider.py").exists():
            sys.path.insert(0, str(c))
            break
    import pytest as _pytest
    _pytest.importorskip("agent.memory_provider")

    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    from seira_web import conversations as convs
    from seira_web.chat import run_turn

    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am careful."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    provider = SeiraPsycheProvider()
    conv_id = convs.create_conversation()["conv_id"]

    class FileMakerLLM:
        def __init__(self):
            self.calls = 0

        def complete(self, system, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return {"content": [{"type": "tool_use", "id": "tu1",
                                     "name": "seira_create_file",
                                     "input": {"format": "md", "filename": "notes",
                                              "content": "# Notes\n\nSome content."}}],
                        "stop_reason": "tool_use"}
            return {"content": [{"type": "text", "text": "Made the file."}],
                    "stop_reason": "end_turn"}

    events = []
    result = run_turn(provider, FileMakerLLM(), conv_id, "write me some notes",
                      emit=events.append)
    assert result["reply"] == "Made the file."
    file_events = [e for e in events if e["event"] == "file_created"]
    assert len(file_events) == 1
    assert file_events[0]["filename"] == "notes.md"
    assert file_events[0]["download_path"].startswith("/api/outputs/")

    from seira_web.filegen import get_output_path
    out_id = file_events[0]["download_path"].rsplit("/", 1)[-1]
    assert get_output_path(out_id).exists()
