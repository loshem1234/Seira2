"""Vision tests — the bounded-context design: real image on the current
turn only; past turns replay as a text marker; recall is deliberate."""

import json
import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_web import conversations as convs  # noqa: E402
from seira_web import images  # noqa: E402
from seira_web.chat import run_turn  # noqa: E402


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am careful."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


def test_save_and_reconstruct_image_block(founded):
    rec = images.save_image("cat.png", "image/png", b"fake png bytes")
    block = images.get_image_block(rec["img_id"])
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"
    import base64
    assert base64.b64decode(block["source"]["data"]) == b"fake png bytes"


def test_unsupported_and_oversized_images_refused(founded):
    with pytest.raises(ValueError):
        images.save_image("doc.pdf", "application/pdf", b"x")
    with pytest.raises(ValueError):
        images.save_image("huge.png", "image/png", b"x" * (6 * 1024 * 1024))


class VisionLLM:
    """Captures exactly what content shape it was sent, to prove the
    current turn gets the real image while history does not."""

    def __init__(self):
        self.seen_messages = []

    def complete(self, system, messages, tools):
        self.seen_messages.append(messages)
        return {"content": [{"type": "text", "text": "I see a cat."}],
                "stop_reason": "end_turn"}


def test_current_turn_gets_real_image_block(founded):
    provider, conv_id = founded
    rec = images.save_image("cat.png", "image/png", b"fake png bytes")
    llm = VisionLLM()
    result = run_turn(
        provider, llm, conv_id, "what is this?",
        attachment={"kind": "image", "name": "cat.png", "img_id": rec["img_id"]},
    )
    assert result["reply"] == "I see a cat."
    last_user_msg = llm.seen_messages[-1][-1]
    assert last_user_msg["role"] == "user"
    blocks = last_user_msg["content"]
    assert isinstance(blocks, list)
    assert blocks[0]["type"] == "image"
    assert blocks[1] == {"type": "text", "text": "what is this?"}


def test_past_image_replays_as_text_marker_not_real_bytes(founded):
    """The bounded-context guarantee: a second, unrelated turn must NOT
    carry the earlier image's bytes again."""
    provider, conv_id = founded
    rec = images.save_image("cat.png", "image/png", b"fake png bytes")
    llm = VisionLLM()
    run_turn(provider, llm, conv_id, "what is this?",
             attachment={"kind": "image", "name": "cat.png", "img_id": rec["img_id"]})
    run_turn(provider, llm, conv_id, "tell me more")

    second_call_messages = llm.seen_messages[-1]
    # No message in this second call may contain a real image block.
    for m in second_call_messages:
        content = m["content"]
        if isinstance(content, list):
            assert not any(b.get("type") == "image" for b in content)
        else:
            assert isinstance(content, str)
    # But the marker text IS present, referencing the image by id.
    joined = " ".join(
        m["content"] if isinstance(m["content"], str) else ""
        for m in second_call_messages
    )
    assert rec["img_id"] in joined
    assert "cat.png" in joined


def test_image_recall_returns_real_image_block_in_tool_result(founded):
    provider, conv_id = founded
    rec = images.save_image("cat.png", "image/png", b"fake png bytes")

    class RecallLLM:
        def __init__(self):
            self.calls = 0

        def complete(self, system, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return {"content": [{"type": "tool_use", "id": "tu1",
                                     "name": "seira_image_recall",
                                     "input": {"img_id": rec["img_id"]}}],
                        "stop_reason": "tool_use"}
            # Second call: assert the tool_result carried the real image.
            last = messages[-1]
            assert last["role"] == "user"
            tool_result = last["content"][0]
            assert tool_result["type"] == "tool_result"
            assert any(b.get("type") == "image" for b in tool_result["content"])
            return {"content": [{"type": "text", "text": "Yes, still a cat."}],
                    "stop_reason": "end_turn"}

    result = run_turn(provider, RecallLLM(), conv_id, "look at that image again")
    assert result["reply"] == "Yes, still a cat."


def test_image_recall_missing_id_is_honest_not_a_crash(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_image_recall",
                                                {"img_id": "img-nonexistent"}))
    assert out["ok"] is False and "error" in out
