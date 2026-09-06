"""Tests for seira_web.conversations' file locking — the real fix for
a live bug reported twice (2026-09-06): 'expected value at line 1
column N' JSON parse failures and 'text content blocks must contain
non-whitespace text' API errors, growing more frequent as a
conversation grew longer.

Root cause, reproduced directly before writing the fix: append() read
the whole conversation file to compute the next sequential id, then
wrote separately — an unprotected read-modify-write. Autonomous mode
writing on its own background thread roughly once a minute, while
normal requests can read or write the same conversation at the same
time, is a genuinely new concurrency scenario that didn't exist before
autonomous mode did. These tests use real threads against real disk,
not mocks — a race condition proven by reasoning alone isn't proven.
"""

import sys
import threading
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_web import conversations as convs  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


def test_concurrent_appends_produce_no_duplicate_ids(home):
    """The exact bug, reproduced directly: 30 unlocked concurrent
    appends produced 18 duplicate ids before this fix. Real threads,
    real disk — not a mock standing in for the race."""
    conv = convs.create_conversation()
    conv_id = conv["conv_id"]

    def do_append(i):
        convs.append(conv_id, "user", text=f"message {i}")

    threads = [threading.Thread(target=do_append, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recs = convs.records(conv_id)
    ids = [r["id"] for r in recs]
    assert len(recs) == 30
    assert len(ids) == len(set(ids)), "duplicate ids — the race is back"
    assert ids == list(range(1, 31)), "ids must be sequential with no gaps"


def test_concurrent_appends_produce_no_corrupt_json_lines(home):
    """Large payloads (a real long reply or document) are what would
    trigger byte-level write interleaving, not just the id race —
    tested with 20KB records specifically."""
    conv = convs.create_conversation()
    conv_id = conv["conv_id"]
    big_text = "x" * 20_000

    def do_append(i):
        convs.append(conv_id, "assistant", text=big_text, autonomous=True)

    threads = [threading.Thread(target=do_append, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # records() itself calls json.loads on every line — if any line
    # were corrupted, this call would raise instead of returning.
    recs = convs.records(conv_id)
    assert len(recs) == 20
    for r in recs:
        assert r["text"] == big_text  # not truncated, not merged with another record


def test_concurrent_read_during_write_never_sees_a_torn_file(home):
    """The other half of the race: a read (records()/model_history())
    happening while a write is in progress must never see a partial
    file — this is what the lock covers on the READ side too, not
    just serializing writes against each other."""
    conv = convs.create_conversation()
    conv_id = conv["conv_id"]
    convs.append(conv_id, "user", text="seed message")

    errors = []

    def writer():
        for i in range(15):
            convs.append(conv_id, "assistant", text=f"reply {i}" * 500)

    def reader():
        for _ in range(30):
            try:
                convs.records(conv_id)
            except Exception as e:
                errors.append(e)

    writer_thread = threading.Thread(target=writer)
    reader_threads = [threading.Thread(target=reader) for _ in range(4)]
    writer_thread.start()
    for t in reader_threads:
        t.start()
    writer_thread.join()
    for t in reader_threads:
        t.join()

    assert errors == [], f"reads saw a torn/corrupt file: {errors}"


def test_normal_single_threaded_use_is_unaffected(home):
    """The lock must not change behavior for the overwhelmingly common
    case — one request, one append, no contention."""
    conv = convs.create_conversation()
    conv_id = conv["conv_id"]
    rec1 = convs.append(conv_id, "user", text="hello")
    rec2 = convs.append(conv_id, "assistant", text="hi there")
    assert rec1["id"] == 1
    assert rec2["id"] == 2
    assert convs.records(conv_id) == [rec1, rec2]


def test_lock_file_does_not_leak_into_records_or_history(home):
    """The lock is a separate .lock file, never mistaken for
    conversation content."""
    conv = convs.create_conversation()
    conv_id = conv["conv_id"]
    convs.append(conv_id, "user", text="hello")
    recs = convs.records(conv_id)
    assert all(r.get("kind") in ("user", "assistant", "tool", "attachment",
                                 "supersede_from") for r in recs)


def test_reading_an_empty_conversation_still_works(home):
    """records() on a conversation with no messages yet must not
    require the lock file or conversation file to pre-exist in any
    special way."""
    conv = convs.create_conversation()
    assert convs.records(conv["conv_id"]) == []
