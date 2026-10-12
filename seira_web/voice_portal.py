"""Routes for her voice: status, voice list, settings, speak, audio."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from seira_core.tenancy import tenant_scope


class SpeakBody(BaseModel):
    text: str


class SettingsBody(BaseModel):
    voice_id: str = ""
    style: str = ""
    model: str = ""


def register(app, templates, require_account):
    from seira_web import voice

    @app.get("/api/voice/status")
    def voice_status(account: dict = Depends(require_account)):
        with tenant_scope(account["tenant_id"]):
            return voice.status()

    @app.get("/api/voice/voices")
    def voice_voices(account: dict = Depends(require_account)):
        try:
            return {"voices": voice.list_voices()}
        except voice.VoiceError as e:
            return {"error": str(e)}

    @app.post("/api/voice/settings")
    def voice_settings(body: SettingsBody, account: dict = Depends(require_account)):
        with tenant_scope(account["tenant_id"]):
            try:
                voice.save_settings(body.voice_id, body.style, body.model)
            except voice.VoiceError as e:
                raise HTTPException(status_code=400, detail=str(e))
            return voice.status()

    @app.post("/api/voice/speak")
    def voice_speak(body: SpeakBody, account: dict = Depends(require_account)):
        if len(body.text) > 200_000:
            raise HTTPException(status_code=413, detail="Too long.")
        with tenant_scope(account["tenant_id"]):
            try:
                res = voice.speak(body.text)
            except voice.VoiceError as e:
                return {"error": str(e)}
        return {"url": f"/api/voice/audio/{res['name']}", "cached": res["cached"]}

    @app.get("/api/voice/audio/{name}")
    def voice_audio(name: str, account: dict = Depends(require_account)):
        with tenant_scope(account["tenant_id"]):
            p = voice.cached_path(name)
        if p is None:
            raise HTTPException(status_code=404, detail="Not found.")
        return FileResponse(p, media_type="audio/mpeg" if name.endswith(".mp3") else "audio/wav",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})
