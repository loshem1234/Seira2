"""seira_web.voice — her spoken voice, via Google's Gemini TTS.

Her designed voice (made in AI Studio, an id like ``voice_…``) is used
through the Gemini Interactions API. Everything here is deliberately
boring: no sentence of hers is ever stored in a provider's account, the
audio is cached on disk by a hash of (text, voice, style), so a message
is paid for once and replays free.

Configuration
  * ``GEMINI_API_KEY`` (env var, Railway)  — required. Never stored in a file.
  * voice id / style / model — chosen on the Commands page, saved in
    ``corpus/voice/settings.json`` (``SEIRA_VOICE_ID`` env var is the default).

Long replies are split at sentence boundaries (the API caps a single
request), synthesized in parallel, and stitched into one file.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from seira_core.paths import seira_home

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
CHUNK_CHARS = 1800          # per request; far under the token cap
MAX_CHARS = 60_000          # a whole reply, hard ceiling
TIMEOUT = 90.0
_RATE, _WIDTH, _CHANNELS = 24000, 2, 1


class VoiceError(RuntimeError):
    pass


# ── settings ────────────────────────────────────────────────────────────
def _dir() -> Path:
    return seira_home() / "corpus" / "voice"


def _settings_path() -> Path:
    return _dir() / "settings.json"


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def get_settings() -> Dict[str, Any]:
    s = {"voice_id": os.environ.get("SEIRA_VOICE_ID", "").strip(),
         "style": "", "model": DEFAULT_MODEL}
    p = _settings_path()
    if p.exists():
        try:
            s.update({k: v for k, v in json.loads(p.read_text("utf-8")).items()
                      if k in s and isinstance(v, str)})
        except (ValueError, OSError):
            pass
    return s


def save_settings(voice_id: str, style: str = "", model: str = "") -> Dict[str, Any]:
    voice_id = (voice_id or "").strip()
    if voice_id and not re.fullmatch(r"[A-Za-z0-9_\-]{1,200}", voice_id):
        raise VoiceError("That does not look like a voice id.")
    model = (model or DEFAULT_MODEL).strip()
    if not re.fullmatch(r"[a-z0-9.\-]{3,60}", model):
        raise VoiceError("That does not look like a model name.")
    s = {"voice_id": voice_id, "style": (style or "").strip()[:300], "model": model}
    _dir().mkdir(parents=True, exist_ok=True)
    _settings_path().write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def status() -> Dict[str, Any]:
    s = get_settings()
    return {"key": bool(api_key()), "voice_id": s["voice_id"], "style": s["style"],
            "model": s["model"], "ready": bool(api_key() and s["voice_id"])}


# ── text prep ───────────────────────────────────────────────────────────
_FENCE = re.compile(r"```.*?```", re.S)


def speakable(text: str) -> str:
    """What is worth saying aloud: no code blocks, links as their words,
    no markdown furniture."""
    t = _FENCE.sub(" ", text or "")
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~]{1,3}([^*_~\n]+)[*_~]{1,3}", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> List[str]:
    """Split at paragraph, then sentence, then word boundaries."""
    out: List[str] = []
    for para in [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]:
        pieces = re.split(r"(?<=[.!?…])\s+", para)
        cur = ""
        for s in pieces:
            while len(s) > limit:                       # one huge "sentence"
                cut = s.rfind(" ", 0, limit)
                if cut <= 0:
                    cut = limit
                if cur: out.append(cur); cur = ""
                out.append(s[:cut].strip()); s = s[cut:].strip()
            if cur and len(cur) + 1 + len(s) > limit:
                out.append(cur); cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            out.append(cur)
    # merge tiny neighbours so we do not make many tiny requests
    merged: List[str] = []
    for c in out:
        if merged and len(merged[-1]) + len(c) + 2 <= limit // 2:
            merged[-1] += "\n\n" + c
        else:
            merged.append(c)
    return merged


# ── the API ─────────────────────────────────────────────────────────────
def _headers() -> Dict[str, str]:
    k = api_key()
    if not k:
        raise VoiceError("GEMINI_API_KEY is not set on the server.")
    return {"x-goog-api-key": k, "Content-Type": "application/json"}


def _err(r: httpx.Response) -> VoiceError:
    try:
        msg = r.json().get("error", {}).get("message") or r.text
    except Exception:
        msg = r.text
    return VoiceError(f"Google said ({r.status_code}): {str(msg)[:300]}")


def list_voices() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    token = ""
    for _ in range(10):
        params = {"page_size": "100"}
        if token:
            params["page_token"] = token
        r = httpx.get(f"{API_ROOT}/voices", headers=_headers(), params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            raise _err(r)
        d = r.json()
        for v in d.get("voices", []):
            out.append({"id": v.get("id", ""), "name": v.get("display_name") or v.get("id", ""),
                        "type": v.get("type", "")})
        token = d.get("next_page_token") or d.get("nextPageToken") or ""
        if not token:
            break
    # her created voices first
    out.sort(key=lambda v: (not v["id"].startswith("voice_"),))
    return out


def _find_audio(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    found = None
    for step in d.get("steps", []) or []:
        if step.get("type") != "model_output":
            continue
        for c in step.get("content", []) or []:
            if c.get("type") == "audio" and c.get("data"):
                found = c
    if found is None and isinstance(d.get("output_audio"), dict):
        found = d["output_audio"]
    return found


def _as_wav_frames(raw: bytes) -> bytes:
    """Return raw PCM frames, whatever container the API sent."""
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as w:
            if (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (_RATE, _WIDTH, _CHANNELS):
                raise VoiceError("Unexpected audio format from Google.")
            return w.readframes(w.getnframes())
    return raw  # headerless 24 kHz mono 16-bit PCM


def synthesize_chunk(text: str, voice_id: str, style: str, model: str) -> bytes:
    """One request → PCM frames."""
    content: Dict[str, Any] = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice_id}]},
    }
    last: Optional[Exception] = None
    for attempt in range(2):
        try:
            r = httpx.post(f"{API_ROOT}/interactions", headers=_headers(), json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            last = VoiceError(f"Could not reach Google: {e.__class__.__name__}")
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            last = _err(r)
            continue
        if r.status_code != 200:
            raise _err(r)
        a = _find_audio(r.json())
        if not a:
            raise VoiceError("Google returned no audio.")
        return _as_wav_frames(base64.b64decode(a["data"]))
    raise last or VoiceError("Speech request failed.")


def _encode(pcm: bytes) -> tuple[bytes, str]:
    """MP3 when the encoder is available (about a tenth the size), else WAV."""
    try:
        import lameenc
        enc = lameenc.Encoder()
        enc.set_bit_rate(64)
        enc.set_in_sample_rate(_RATE)
        enc.set_channels(1)
        enc.set_quality(3)
        return bytes(enc.encode(pcm) + enc.flush()), "mp3"
    except Exception:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(_CHANNELS); w.setsampwidth(_WIDTH); w.setframerate(_RATE)
            w.writeframes(pcm)
        return buf.getvalue(), "wav"


def _cache_name(text: str, voice_id: str, style: str, model: str) -> str:
    return hashlib.sha256(f"{model}\x1f{voice_id}\x1f{style}\x1f{text}".encode()).hexdigest()[:40]


def cached_path(name: str) -> Optional[Path]:
    if not re.fullmatch(r"[0-9a-f]{40}\.(mp3|wav)", name):
        return None
    p = _dir() / "audio" / name
    return p if p.exists() else None


def speak(text: str, *, voice_id: str = "", style: Optional[str] = None) -> Dict[str, Any]:
    """Text → cached audio file. Returns {name, cached, chars}."""
    s = get_settings()
    vid = (voice_id or s["voice_id"]).strip()
    if not vid:
        raise VoiceError("No voice is chosen yet — pick one on the Commands page.")
    sty = s["style"] if style is None else style
    clean = speakable(text)[:MAX_CHARS]
    if not clean:
        raise VoiceError("Nothing to say aloud (it is all code or links).")
    base = _cache_name(clean, vid, sty, s["model"])
    for ext in ("mp3", "wav"):
        if cached_path(f"{base}.{ext}"):
            return {"name": f"{base}.{ext}", "cached": True, "chars": len(clean)}
    pieces = chunk_text(clean)
    with ThreadPoolExecutor(max_workers=min(4, len(pieces))) as ex:
        frames = list(ex.map(lambda t: synthesize_chunk(t, vid, sty, s["model"]), pieces))
    audio, ext = _encode(b"".join(frames))
    d = _dir() / "audio"
    d.mkdir(parents=True, exist_ok=True)
    name = f"{base}.{ext}"
    tmp = d / (name + ".part")
    tmp.write_bytes(audio)
    tmp.replace(d / name)
    return {"name": name, "cached": False, "chars": len(clean)}
