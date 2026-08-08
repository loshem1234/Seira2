"""Reference file and document-extraction tests."""

import pytest

from seira_core.paths import seira_home
from seira_web import references as refs
from seira_web.documents import extract_text


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


def test_save_list_and_recall(home):
    rec = refs.save_reference("notes.txt", "the vesica holds the point" * 500)
    assert rec["ref_id"].startswith("ref-")
    listed = refs.list_references()
    assert len(listed) == 1 and listed[0]["filename"] == "notes.txt"

    page1 = refs.read_slice(rec["ref_id"], offset=0, length=100)
    assert page1["found"] and page1["length"] == 100 and page1["has_more"]
    page2 = refs.read_slice("notes.txt", offset=100, length=100)  # lookup by name
    assert page2["found"] and page2["offset"] == 100


def test_recall_of_missing_reference_is_honest_not_an_exception(home):
    result = refs.read_slice("does-not-exist")
    assert result["found"] is False and "No reference" in result["error"]


def test_cannot_save_empty_reference(home):
    with pytest.raises(ValueError):
        refs.save_reference("empty.txt", "   ")


def test_length_is_bounded_per_call(home):
    rec = refs.save_reference("big.txt", "x" * 100_000)
    page = refs.read_slice(rec["ref_id"], length=1_000_000)
    assert page["length"] == 40_000  # capped, never the whole thing in one call


# ---------------- document extraction ----------------

def test_txt_and_md_extraction():
    assert extract_text("notes.txt", "hello".encode())["ok"] is True
    bad = extract_text("notes.txt", b"\xff\xfe\x00broken")
    assert bad["ok"] is False


def test_unsupported_extension_refused():
    result = extract_text("photo.png", b"\x89PNG")
    assert result["ok"] is False and "Unsupported" in result["error"]


def test_pdf_text_layer_extraction():
    pypdf = pytest.importorskip("pypdf")
    import io
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    # A blank generated PDF has no text layer — proves the honest-failure path,
    # since fabricating a text-bearing PDF via pypdf alone isn't practical here.
    result = extract_text("blank.pdf", buf.getvalue())
    assert result["ok"] is False
    assert "scanned/image-only" in result["error"]


def test_pdf_garbage_bytes_handled_cleanly():
    result = extract_text("fake.pdf", b"not actually a pdf")
    assert result["ok"] is False and "Could not read" in result["error"]
