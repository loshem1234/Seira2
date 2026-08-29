"""seira_web.imagegen — she generates images, via OpenAI's GPT Image 2.

Anthropic has no image generation of its own (D85: flagged, deferred
pending an explicit vendor decision — now made). This is a genuinely
separate vendor, separate API key, separate recurring cost from her
conversation model.

Design points worth knowing:

* **Reference-aware, using her existing tagged image store.** If she
  (or the Architect) names a reference — "my portrait ref" — the raw
  bytes are pulled from her own Corpus and sent as a real reference
  image to OpenAI's edit endpoint, not just described in the prompt.
  Per OpenAI's own docs, reference images are processed at high
  fidelity automatically. Per OpenAI's own docs, character consistency
  is NOT guaranteed across generations — this is stated in her tool
  description too, so she doesn't oversell it to the Architect.

* **Generated images compound her reference library.** Every image
  she generates is saved back into the SAME tagged image store real
  uploads use. A later generation can reference an earlier generation,
  not just an original upload — the library gets more useful to draw
  from over time, not just larger.

* **No references present → the plain generation endpoint (JSON).
  One or more references present → the edit endpoint (multipart,
  actual file bytes).** These are genuinely different OpenAI API
  shapes; conflating them would silently drop reference fidelity.

* **Cost is real and tiered.** Requests with references cost more
  (reference images add input tokens) — surfaced in the tool result,
  not hidden.
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional, Protocol

import httpx

DEFAULT_MODEL = os.environ.get("SEIRA_IMAGE_MODEL", "gpt-image-2")
DEFAULT_QUALITY = os.environ.get("SEIRA_IMAGE_QUALITY", "medium")
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("SEIRA_IMAGE_TIMEOUT", "150"))
# OpenAI's own guidance: generation can take up to ~2 minutes for complex
# prompts/high quality/references; billing happens even if the client
# disconnects, so a client-side timeout must be generous, not aggressive.

VALID_QUALITIES = {"low", "medium", "high", "auto"}
VALID_ASPECTS = {"1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "16:9", "9:16", "21:9"}

_ASPECT_TO_SIZE = {  # OpenAI's generate endpoint wants explicit pixel sizes
    "1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536",
    "4:3": "1408x1024", "3:4": "1024x1408", "4:5": "1024x1280",
    "16:9": "1536x864", "9:16": "864x1536", "21:9": "1680x720",
}


class ImageGenError(Exception):
    pass


class ImageGenClient(Protocol):
    def generate(self, prompt: str, references: List[Dict[str, Any]],
                quality: str, aspect_ratio: str) -> bytes: ...


class OpenAIImageClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        if not self._api_key:
            raise ImageGenError(
                "OPENAI_API_KEY is not set; image generation is a separate "
                "vendor/API key from her conversation model."
            )

    def generate(self, prompt: str, references: List[Dict[str, Any]],
                quality: str = DEFAULT_QUALITY, aspect_ratio: str = "1:1") -> bytes:
        if quality not in VALID_QUALITIES:
            raise ImageGenError(f"quality must be one of {sorted(VALID_QUALITIES)}.")
        if aspect_ratio not in VALID_ASPECTS:
            raise ImageGenError(f"aspect_ratio must be one of {sorted(VALID_ASPECTS)}.")
        headers = {"Authorization": f"Bearer {self._api_key}"}

        if references:
            # The edit endpoint: real multipart file upload, one or more
            # reference images actually sent as bytes, not just described.
            files = []
            for i, ref in enumerate(references):
                files.append((
                    "image[]",
                    (ref.get("filename", f"ref{i}"), ref["raw"], ref["media_type"]),
                ))
            data = {"model": self._model, "prompt": prompt, "quality": quality}
            resp = httpx.post(
                "https://api.openai.com/v1/images/edits",
                headers=headers, data=data, files=files,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        else:
            payload = {
                "model": self._model, "prompt": prompt, "quality": quality,
                "size": _ASPECT_TO_SIZE[aspect_ratio],
            }
            resp = httpx.post(
                "https://api.openai.com/v1/images/generations",
                headers={**headers, "Content-Type": "application/json"},
                json=payload, timeout=REQUEST_TIMEOUT_SECONDS,
            )

        if resp.status_code != 200:
            raise ImageGenError(
                f"OpenAI image API returned {resp.status_code}: {resp.text[:300]}"
            )
        body = resp.json()
        try:
            b64 = body["data"][0]["b64_json"]
        except (KeyError, IndexError, TypeError):
            raise ImageGenError(f"Unexpected response shape from OpenAI: {body}")
        return base64.b64decode(b64)


def generate_and_save(
    prompt: str,
    reference_refs: Optional[List[str]] = None,
    tag: str = "",
    quality: str = DEFAULT_QUALITY,
    aspect_ratio: str = "1:1",
    client: Optional[ImageGenClient] = None,
) -> Dict[str, Any]:
    """Resolve any named references from her own Corpus, generate, and
    save the result back into the same tagged image store — the
    function the bridge tool actually calls."""
    from seira_web import images

    if not prompt.strip():
        raise ImageGenError("A prompt is required.")

    resolved_refs: List[Dict[str, Any]] = []
    missing: List[str] = []
    for ref in (reference_refs or []):
        found = images.get_image_bytes(ref)
        if found is None:
            missing.append(ref)
        else:
            resolved_refs.append(found)
    if missing:
        raise ImageGenError(
            f"Reference(s) not found: {', '.join(missing)}. Use "
            "seira_image_list to see what's actually saved."
        )

    active_client = client or OpenAIImageClient()
    raw = active_client.generate(prompt, resolved_refs, quality, aspect_ratio)

    default_tag = tag or f"generated-{prompt[:40]}"
    filename = f"{(tag or 'generated')[:60]}.png"
    saved = images.save_image(filename, "image/png", raw, tag=default_tag)
    return {
        **saved,
        "used_references": [r["tag"] for r in resolved_refs],
        "quality": quality,
    }
