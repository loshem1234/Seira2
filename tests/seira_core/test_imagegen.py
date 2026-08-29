"""Image generation tests. A fake client is injected everywhere — no
real network calls, no real OpenAI cost, ever, in this suite."""

import pytest

from seira_web import images
from seira_web.imagegen import ImageGenError, generate_and_save


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


class FakeClient:
    """Records exactly what it was called with, so tests can assert on
    the real inputs rather than trusting the implementation blindly."""

    def __init__(self, output=b"fake generated png bytes"):
        self.calls = []
        self.output = output

    def generate(self, prompt, references, quality, aspect_ratio):
        self.calls.append({"prompt": prompt, "references": references,
                           "quality": quality, "aspect_ratio": aspect_ratio})
        return self.output


def test_generation_with_no_references_uses_empty_reference_list(home):
    client = FakeClient()
    rec = generate_and_save("a sunset over mountains", client=client)
    assert client.calls[0]["references"] == []
    assert rec["tag"]
    # And it's really saved — recallable like any other image:
    assert images.image_record(rec["img_id"]) is not None


def test_generation_with_a_tagged_reference_sends_real_bytes(home):
    images.save_image("me.png", "image/png", b"my actual portrait bytes",
                      tag="my portrait ref")
    client = FakeClient()
    rec = generate_and_save("me as a renaissance painting",
                            reference_refs=["my-portrait-ref"], client=client)
    sent_refs = client.calls[0]["references"]
    assert len(sent_refs) == 1
    assert sent_refs[0]["raw"] == b"my actual portrait bytes"  # real bytes, not a description
    assert rec["used_references"] == ["my-portrait-ref"]


def test_missing_reference_is_refused_before_any_api_call(home):
    client = FakeClient()
    with pytest.raises(ImageGenError, match="not found"):
        generate_and_save("x", reference_refs=["nonexistent-tag"], client=client)
    assert client.calls == []  # never even attempted the (paid) call


def test_generated_images_become_referenceable_for_the_next_generation(home):
    """The compounding-library design: a generated image is saved into
    the SAME tagged store, so it can be referenced by a later call."""
    client = FakeClient()
    first = generate_and_save("my first self-portrait", tag="self v1", client=client)
    assert first["tag"] == "self-v1"

    second = generate_and_save("me smiling, matching my earlier portrait",
                               reference_refs=["self-v1"], client=client)
    sent_refs = client.calls[1]["references"]
    assert sent_refs[0]["tag"] == "self-v1"
    assert second["used_references"] == ["self-v1"]


def test_empty_prompt_refused(home):
    with pytest.raises(ImageGenError):
        generate_and_save("   ", client=FakeClient())


def test_default_tag_derived_from_prompt_when_not_given(home):
    rec = generate_and_save("a lighthouse at dawn over rocky cliffs",
                            client=FakeClient())
    assert "lighthouse" in rec["tag"]


def test_client_construction_refuses_without_api_key(home, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from seira_web.imagegen import OpenAIImageClient
    with pytest.raises(ImageGenError, match="OPENAI_API_KEY"):
        OpenAIImageClient()


def test_invalid_quality_and_aspect_refused(home):
    client = FakeClient()

    class RealValidatingClient:
        def generate(self, prompt, references, quality, aspect_ratio):
            from seira_web.imagegen import VALID_QUALITIES, VALID_ASPECTS
            if quality not in VALID_QUALITIES:
                raise ImageGenError("bad quality")
            if aspect_ratio not in VALID_ASPECTS:
                raise ImageGenError("bad aspect")
            return b"bytes"

    with pytest.raises(ImageGenError):
        generate_and_save("x", quality="ultra-mega", client=RealValidatingClient())


def test_bridge_tool_end_to_end(home):
    """Through the real bridge dispatch, with the real OpenAI client
    replaced by a monkeypatch — proves the wiring, not just the module."""
    import sys
    from pathlib import Path
    for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
        if (c / "agent" / "memory_provider.py").exists():
            sys.path.insert(0, str(c))
            break
    pytest.importorskip("agent.memory_provider")

    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis([{"category": "self_model", "content": "careful"}],
                           architect="L")

    import seira_web.imagegen as imagegen_mod
    imagegen_mod.OpenAIImageClient = lambda *a, **k: FakeClient()

    from seira_bridge import SeiraPsycheProvider
    import json
    provider = SeiraPsycheProvider()
    out = json.loads(provider.handle_tool_call("seira_generate_image", {
        "prompt": "a portrait in oil paint style",
    }))
    assert out["ok"] is True and out["__image_created__"] is True
    assert images.image_record(out["img_id"]) is not None
