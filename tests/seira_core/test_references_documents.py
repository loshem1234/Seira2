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


# ---------------- tagging (mirrors images.py's design exactly) ----------------

def test_reference_gets_a_default_tag_from_filename(home):
    rec = refs.save_reference("Q3 Report.pdf", "quarterly numbers here")
    assert rec["tag"] == "q3-report"


def test_explicit_tag_is_honored(home):
    rec = refs.save_reference("notes.txt", "content", tag="my special notes")
    assert rec["tag"] == "my-special-notes"


def test_colliding_tag_is_disambiguated_not_overwritten(home):
    a = refs.save_reference("a.txt", "first document", tag="shared-name")
    b = refs.save_reference("b.txt", "second document", tag="shared-name")
    assert a["tag"] == "shared-name"
    assert b["tag"] != "shared-name"
    assert b["tag"].startswith("shared-name-")


def test_set_tag_renames_and_enforces_uniqueness(home):
    a = refs.save_reference("a.txt", "content a")
    b = refs.save_reference("b.txt", "content b")
    refs.set_tag(a["ref_id"], "new-name")
    assert refs.find_by_tag("new-name")["ref_id"] == a["ref_id"]
    with pytest.raises(ValueError):
        refs.set_tag(b["ref_id"], "new-name")  # collision, refused not silent


def test_resolve_ref_finds_by_id_tag_or_filename(home):
    rec = refs.save_reference("brief.txt", "project brief content", tag="the-brief")
    assert refs.resolve_ref(rec["ref_id"])["ref_id"] == rec["ref_id"]
    assert refs.resolve_ref("the-brief")["ref_id"] == rec["ref_id"]
    assert refs.resolve_ref("brief.txt")["ref_id"] == rec["ref_id"]
    assert refs.resolve_ref("nothing-like-this") is None


def test_read_slice_reports_tag_and_source(home):
    refs.save_reference("web-page.txt", "extracted content", source="web", tag="found-it")
    result = refs.read_slice("found-it")
    assert result["found"] and result["tag"] == "found-it" and result["source"] == "web"


def test_old_records_without_a_tag_get_backfilled_on_load(home, tmp_path):
    """Records saved before tagging existed have no 'tag' key at all —
    the exact migration gap images.py already hit in production once."""
    rec = refs.save_reference("legacy.txt", "old content")
    # Simulate a pre-tagging record by stripping the tag from the index.
    index = refs._load_index()
    del index[rec["ref_id"]]["tag"]
    refs._save_index(index)
    reloaded = refs.list_references()
    assert reloaded[0]["tag"]  # backfilled, not missing/crashing


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
