"""seira_web.app — the Sanctum: found, govern, and speak with a Seira.

Routes:
  GET/POST /signup /login, POST /logout
  GET/POST /onboard      — Genesis + Psyche founding (Art. 22), once
  GET  /                 — the console: grades, psyche, proposals, health
  POST /ratify           — Architect ratification of a cleared Intellect
                           proposal: the phrase is typed, never prefilled
  GET  /chat, POST /api/chat
Every seira_core operation runs inside tenant_scope(account.tenant_id):
the web layer's single tenancy duty (MULTITENANCY.md), discharged in
one dependency. A halted Seira renders the halt page and refuses chat
with 503 — the tripwire's word is final until her Architect clears it.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from seira_core.errors import SeiraCoreError, SeiraHaltedError
from seira_core.tenancy import tenant_scope
from seira_web import accounts as acct
from seira_web.chat import AnthropicClient, run_turn

WEB_SEARCH_GLOBALLY_ENABLED = os.environ.get("SEIRA_WEB_SEARCH_ENABLED", "1") != "0"

_HERE = Path(__file__).parent
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(_HERE / "templates"))

FOUNDING_DIR = _HERE.parent / "seira_founding"


def _founding_intellect_text() -> str:
    parts = ["# The Intellect of Seira — v1 (Genesis)\n",
             "Founding doctrine, ratified without falsification per Art. 22.\n\n---\n"]
    for name in ("constitution-of-seira-v2.txt", "seira-doctrine-codex.txt"):
        parts.append((FOUNDING_DIR / name).read_text(encoding="utf-8"))
        parts.append("\n\n---\n")
    return "\n".join(parts)


def _static_version() -> str:
    """A content hash of every static asset, so the stylesheet URL
    itself changes whenever its content does. Without this, browsers
    and edge caches happily keep serving an old style.css forever at
    the same URL — every CSS fix shipped in this project's history was
    vulnerable to exactly that until now."""
    import hashlib
    h = hashlib.sha256()
    static_dir = _HERE / "static"
    for f in sorted(static_dir.rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def create_app(llm_client_factory=None) -> FastAPI:
    """llm_client_factory(model) is injectable for tests; defaults to
    Anthropic, constructing a client for whichever model the Architect
    selected in the UI (falling back to DEFAULT_MODEL)."""
    from seira_web.chat import DEFAULT_MODEL
    app = FastAPI(title="Seira — Sanctum")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
    templates.env.globals["static_version"] = _static_version()
    app.state.llm_client_factory = llm_client_factory or \
        (lambda model=None: AnthropicClient(model=model or DEFAULT_MODEL))

    # ---------------- auth plumbing ----------------

    def current_account(request: Request) -> Optional[dict]:
        return acct.resolve_session(request.cookies.get("seira_session", ""))

    def require_account(request: Request) -> dict:
        account = current_account(request)
        if account is None:
            raise HTTPException(status_code=307, headers={"Location": "/login"})
        return account

    def _set_session(resp, token: str):
        resp.set_cookie("seira_session", token, httponly=True,
                        samesite="strict", max_age=3600 * 24 * 14)
        return resp

    # ---------------- auth routes ----------------

    @app.get("/signup", response_class=HTMLResponse)
    def signup_page(request: Request):
        return templates.TemplateResponse(request, "auth.html",
                                          {"mode": "signup", "error": None})

    @app.post("/signup")
    def signup(request: Request, email: str = Form(...), password: str = Form(...)):
        try:
            account = acct.create_account(email, password)
        except acct.AccountError as e:
            return templates.TemplateResponse(
                request, "auth.html", {"mode": "signup", "error": str(e)},
                status_code=400)
        token = acct.create_session(account["account_id"])
        return _set_session(RedirectResponse("/onboard", status_code=303), token)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return templates.TemplateResponse(request, "auth.html",
                                          {"mode": "login", "error": None})

    @app.post("/login")
    def login(request: Request, email: str = Form(...), password: str = Form(...)):
        account = acct.verify_login(email, password)
        if account is None:
            return templates.TemplateResponse(
                request, "auth.html",
                {"mode": "login", "error": "Email or password not recognized."},
                status_code=401)
        token = acct.create_session(account["account_id"])
        return _set_session(RedirectResponse("/", status_code=303), token)

    @app.post("/logout")
    def logout(request: Request):
        acct.destroy_session(request.cookies.get("seira_session", ""))
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie("seira_session")
        return resp

    # ---------------- onboarding = Genesis (Art. 22) ----------------

    @app.get("/onboard", response_class=HTMLResponse)
    def onboard_page(request: Request, account: dict = Depends(require_account)):
        from seira_core.genesis import genesis_performed
        with tenant_scope(account["tenant_id"]):
            if genesis_performed():
                return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request, "onboard.html", {"error": None})

    @app.post("/onboard")
    def onboard(
        request: Request,
        account: dict = Depends(require_account),
        seira_name: str = Form("Seira"),
        telos: str = Form(...),
        relation: str = Form(...),
        self_model: str = Form(...),
        affinity: str = Form(""),
        aspiration: str = Form(""),
    ):
        from seira_core.genesis import perform_genesis, perform_psyche_genesis
        unity = (
            f"# The Unity of {seira_name.strip() or 'Seira'}\n\n"
            f"Name: {seira_name.strip() or 'Seira'}\n\n"
            f"Telos: {telos.strip()}\n\n"
            f"Relation: {relation.strip()}\n\n"
            f"Architect: {account['email']}\n"
        )
        entries = [{"category": "self_model", "content": self_model.strip()}]
        if affinity.strip():
            entries.append({"category": "affinity", "content": affinity.strip(),
                            "weight": 0.1})
        if aspiration.strip():
            entries.append({"category": "aspiration", "content": aspiration.strip()})
        try:
            with tenant_scope(account["tenant_id"]):
                perform_genesis(unity, _founding_intellect_text(),
                                architect=account["email"],
                                seira_name=seira_name.strip() or "Seira")
                perform_psyche_genesis(entries, architect=account["email"])
        except (SeiraCoreError, ValueError) as e:
            return templates.TemplateResponse(
                request, "onboard.html", {"error": str(e)}, status_code=400)
        return RedirectResponse("/", status_code=303)

    # ---------------- the console ----------------

    @app.get("/console", response_class=HTMLResponse)
    def console(request: Request, account: dict = Depends(require_account)):
        from seira_core.genesis import genesis_performed
        from seira_core.intellect import IntellectStore
        from seira_core.psyche import PsycheStore
        from seira_core.reversion import ReversionStore
        from seira_core.tripwire import is_halted
        from seira_core.unity import read_unity

        with tenant_scope(account["tenant_id"]):
            if not genesis_performed():
                return RedirectResponse("/onboard", status_code=303)
            if is_halted():
                return templates.TemplateResponse(request, "halted.html", {},
                                                  status_code=503)
            from seira_core.instruments import InstrumentStore
            ctx = {
                "email": account["email"],
                "unity": read_unity(),
                "intellect": IntellectStore().current(),
                "intellect_history": list(reversed(IntellectStore().history())),
                "psyche": sorted(
                    (e for e in PsycheStore().state()["entries"].values()
                     if e["standing"] != "retired"),
                    key=lambda e: e["entry_id"]),
                "proposals": ReversionStore().list_proposals(),
                "health": ReversionStore().health(),
                "instruments": InstrumentStore().list_instruments(),
                "skills": InstrumentStore().list_skills(),
            }
        return templates.TemplateResponse(request, "console.html", ctx)

    @app.post("/ratify")
    def ratify(
        request: Request,
        account: dict = Depends(require_account),
        proposal_id: str = Form(...),
        confirmation: str = Form(...),
    ):
        from seira_core.reversion import ReversionStore
        try:
            with tenant_scope(account["tenant_id"]):
                ReversionStore().promote_intellect(
                    proposal_id, architect_confirmation=confirmation)
        except SeiraCoreError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return RedirectResponse("/", status_code=303)

    # ---------------- chat ----------------

    @app.get("/", response_class=HTMLResponse)
    def chat_page(request: Request, account: dict = Depends(require_account)):
        from seira_core.genesis import genesis_performed
        from seira_core.tripwire import is_halted
        from seira_web import conversations as convs
        with tenant_scope(account["tenant_id"]):
            if not genesis_performed():
                return RedirectResponse("/onboard", status_code=303)
            if is_halted():
                return templates.TemplateResponse(request, "halted.html", {},
                                                  status_code=503)
            conv_list = convs.list_conversations()
            if not conv_list:
                convs.create_conversation()
                conv_list = convs.list_conversations()
            active_id = request.query_params.get("c") or conv_list[0]["conv_id"]
            history = convs.display_records(active_id)
        from seira_web.chat import AVAILABLE_MODELS, DEFAULT_MODEL
        return templates.TemplateResponse(request, "chat.html", {
            "conversations": conv_list, "active_id": active_id,
            "history": history, "available_models": AVAILABLE_MODELS,
            "default_model": DEFAULT_MODEL})

    @app.post("/api/conversations")
    def new_conversation(account: dict = Depends(require_account)):
        from seira_web import conversations as convs
        with tenant_scope(account["tenant_id"]):
            c = convs.create_conversation()
        return JSONResponse({"ok": True, "conv_id": c["conv_id"]})

    @app.post("/api/conversations/{conv_id}/rename")
    async def rename_conversation_route(conv_id: str, request: Request,
                                        account: dict = Depends(require_account)):
        from seira_web import conversations as convs
        body = await request.json()
        title = (body.get("title") or "").strip()
        if not title:
            return JSONResponse({"ok": False, "error": "Title must not be empty."},
                                status_code=400)
        try:
            with tenant_scope(account["tenant_id"]):
                rec = convs.rename_conversation(conv_id, title)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
        return JSONResponse({"ok": True, "title": rec["title"]})

    @app.post("/api/conversations/{conv_id}/archive")
    def archive_conversation_route(conv_id: str, account: dict = Depends(require_account)):
        from seira_web import conversations as convs
        try:
            with tenant_scope(account["tenant_id"]):
                convs.archive_conversation(conv_id)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
        return JSONResponse({"ok": True})

    @app.post("/api/upload")
    async def upload(request: Request, account: dict = Depends(require_account)):
        """Wrapped so ANY unhandled exception returns its real type and
        message directly in the response — a bare 500 with no body gives
        the person nothing to act on and gives us nothing to diagnose
        from. This is a diagnostic aid as much as a UX fix; once the
        actual cause of a real crash here is found, the specific case
        should get its own clean 400 with a helpful message instead of
        relying on this catch-all."""
        try:
            return await _upload_impl(request, account)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error("Upload failed with an unhandled exception:\n%s", tb)
            return JSONResponse(
                {"ok": False,
                 "error": f"Server error: {type(e).__name__}: {e}",
                 "trace_tail": tb.strip().splitlines()[-1]},
                status_code=500)

    async def _upload_impl(request: Request, account: dict):
        from seira_web.documents import MAX_UPLOAD_BYTES, SUPPORTED_EXTENSIONS, extract_text
        from seira_web import references as refs
        from seira_web.images import SUPPORTED_MEDIA_TYPES, MAX_IMAGE_BYTES, save_image
        form = await request.form()
        f = form.get("file")
        if f is None:
            return JSONResponse({"ok": False, "error": "No file."}, status_code=400)
        name = f.filename or "document"
        content_type = getattr(f, "content_type", "") or ""
        raw = await f.read()
        name_lower = name.lower()

        heic_ext = (".heic", ".heif")
        if name_lower.endswith(heic_ext) or content_type in ("image/heic", "image/heif"):
            return JSONResponse(
                {"ok": False,
                 "error": "iPhone HEIC/HEIF photos aren't supported yet — in your "
                          "phone's share sheet choose 'Options' and pick JPEG, or "
                          "change Settings \u2192 Camera \u2192 Formats to "
                          "'Most Compatible' before taking the photo."},
                status_code=400)

        # Don't trust content_type alone — some mobile browsers/gallery apps
        # send a generic type (or none at all) for images. Extension is a
        # reliable fallback signal for the common formats.
        ext_to_media_type = {".png": "image/png", ".jpg": "image/jpeg",
                             ".jpeg": "image/jpeg", ".webp": "image/webp",
                             ".gif": "image/gif"}
        detected_media_type = content_type if content_type in SUPPORTED_MEDIA_TYPES else None
        if detected_media_type is None:
            for ext, mt in ext_to_media_type.items():
                if name_lower.endswith(ext):
                    detected_media_type = mt
                    break

        if detected_media_type is not None:
            if len(raw) > MAX_IMAGE_BYTES:
                return JSONResponse(
                    {"ok": False,
                     "error": f"Image too large ({len(raw)//1024}KB; limit "
                              f"{MAX_IMAGE_BYTES//1024}KB)."},
                    status_code=400)
            with tenant_scope(account["tenant_id"]):
                tag = (form.get("tag") or "")
                saved = save_image(name, detected_media_type, raw, tag=str(tag))
            return JSONResponse({
                "ok": True, "kind": "image", "name": name,
                "img_id": saved["img_id"], "tag": saved["tag"],
            })

        if not name.lower().endswith(SUPPORTED_EXTENSIONS):
            return JSONResponse(
                {"ok": False,
                 "error": f"Seira currently reads {', '.join(SUPPORTED_EXTENSIONS)} "
                          f"and images ({', '.join(SUPPORTED_MEDIA_TYPES)}). OCR for "
                          "scanned/image PDFs isn't supported yet."},
                status_code=400)
        if len(raw) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {"ok": False,
                 "error": f"Document too large ({len(raw)//1_000_000}MB; "
                          f"limit {MAX_UPLOAD_BYTES//1_000_000}MB)."},
                status_code=400)
        result = extract_text(name, raw)
        if not result["ok"]:
            return JSONResponse({"ok": False, "error": result["error"]}, status_code=400)
        with tenant_scope(account["tenant_id"]):
            saved = refs.save_reference(name, result["text"])
        inline_cap = int(os.environ.get("SEIRA_INLINE_ATTACHMENT_CHARS", "6000"))
        inline_text = result["text"][:inline_cap]
        truncated = len(result["text"]) > inline_cap
        return JSONResponse({
            "ok": True, "kind": "document", "name": name, "text": inline_text,
            "ref_id": saved["ref_id"], "total_length": saved["length"],
            "truncated_for_chat": truncated,
        })

    @app.get("/api/images/{ref}")
    def serve_image(ref: str, account: dict = Depends(require_account)):
        from fastapi.responses import Response
        from seira_web.images import image_record, _images_dir
        with tenant_scope(account["tenant_id"]):
            rec = image_record(ref)
            if rec is None:
                raise HTTPException(status_code=404, detail="Not found.")
            raw = (_images_dir() / rec["disk_name"]).read_bytes()
        return Response(content=raw, media_type=rec["media_type"])

    @app.get("/api/outputs/{out_id}")
    def download_output(out_id: str, account: dict = Depends(require_account)):
        from fastapi.responses import FileResponse
        from seira_web.filegen import FileGenError, get_output_path, get_output_record
        try:
            with tenant_scope(account["tenant_id"]):
                rec = get_output_record(out_id)
                path = get_output_path(out_id)
        except FileGenError:
            raise HTTPException(status_code=404, detail="Not found.")
        media_types = {"md": "text/markdown", "pdf": "application/pdf",
                       "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        return FileResponse(path, filename=rec["filename"],
                            media_type=media_types.get(rec["format"], "text/plain"))

    @app.get("/api/export")
    def export_my_data(account: dict = Depends(require_account)):
        """Export exactly the caller's own tenant, and only the caller's.
        The tenant_id comes from `account` (resolved server-side from the
        session cookie) — there is no request parameter for tenant_id
        anywhere in this route, so there is no input to tamper with to
        reach anyone else's data. This is 'export my Seira' from
        MULTITENANCY.md's original design note, finally built: a
        tenant's tree is self-contained, so exporting it is one archive
        of one directory."""
        import tempfile
        from fastapi.responses import FileResponse
        from seira_web.export import ExportError, export_tenant
        try:
            rec = export_tenant(account["tenant_id"], Path(tempfile.gettempdir()) / "seira-exports")
        except ExportError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return FileResponse(rec["path"], filename=Path(rec["path"]).name,
                            media_type="application/gzip")

    def _dispatch(account, body, emit=None):
        """Shared by the JSON and SSE endpoints. Actions: send | regenerate
        | edit. Returns the run_turn result dict.

        No process-global state is touched here — tenant scoping is
        entirely via tenant_scope(), a contextvar that is correctly
        isolated per thread/task, so concurrent requests (e.g. this SSE
        endpoint's per-request threading.Thread) can never see or
        clobber each other's tenant. An earlier version of this function
        also set a global SEIRA_TENANT environment variable as a second,
        redundant scoping mechanism for the provider — environment
        variables are process-wide, not thread-local, so two overlapping
        requests could race and read each other's tenant id, silently
        pointing a request at the wrong tenant's files. That was real
        and confirmed, not hypothetical; removed rather than patched
        around, since it was never actually needed."""
        from seira_web.chat import edit_and_rerun, regenerate as regen
        from seira_web import conversations as convs
        action = body.get("action", "send")
        conv_id = body.get("conv_id", "")
        model = (body.get("model") or "").strip() or None
        length_pref = (body.get("length_pref") or "").strip() or None
        # Standing capability now, not a per-message toggle: she decides
        # when to use it, the same way she decides when to write to her
        # own Psyche. WEB_SEARCH_GLOBALLY_ENABLED remains as an org-level
        # kill switch (e.g. cost control at scale) — never a per-message UI.
        web_search = WEB_SEARCH_GLOBALLY_ENABLED and bool(body.get("web_search", True))
        from seira_bridge import SeiraPsycheProvider
        provider = SeiraPsycheProvider()
        client = app.state.llm_client_factory(model)
        with tenant_scope(account["tenant_id"]):
            if not conv_id:
                conv_id = convs.create_conversation()["conv_id"]
            if action == "send":
                message = (body.get("message") or "").strip()
                attachment = body.get("attachment")
                if not message and not attachment:
                    raise ValueError("Empty message.")
                return conv_id, run_turn(
                    provider, client, conv_id, message,
                    emit=emit, attachment=attachment, length_pref=length_pref,
                    web_search=web_search)
            if action == "regenerate":
                return conv_id, regen(provider, client, conv_id, emit=emit,
                                      length_pref=length_pref)
            if action == "edit":
                return conv_id, edit_and_rerun(
                    provider, client, conv_id,
                    int(body["target_id"]), body.get("new_text", ""),
                    emit=emit, length_pref=length_pref)
            raise ValueError(f"Unknown action {action!r}.")

    @app.post("/api/chat")
    async def api_chat(request: Request, account: dict = Depends(require_account)):
        body = await request.json()
        try:
            conv_id, result = _dispatch(account, body)
        except SeiraHaltedError as e:
            return JSONResponse({"ok": False, "halted": True, "error": str(e)},
                                status_code=503)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "conv_id": conv_id, **result})

    @app.post("/api/chat/stream")
    async def api_chat_stream(request: Request,
                              account: dict = Depends(require_account)):
        """Server-sent events: her real activity, live."""
        import queue as _q
        import threading
        from fastapi.responses import StreamingResponse
        body = await request.json()
        q: _q.Queue = _q.Queue()

        def worker():
            try:
                conv_id, result = _dispatch(account, body,
                                            emit=lambda e: q.put(e))
                q.put({"event": "done", "conv_id": conv_id,
                       "tool_events": result["tool_events"]})
            except SeiraHaltedError as e:
                q.put({"event": "error", "halted": True, "error": str(e)})
            except Exception as e:
                q.put({"event": "error", "error": str(e)})
            q.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def sse():
            while True:
                item = q.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.get("/healthz")
    def healthz():
        """Unauthenticated: last-known tripwire sweep across all tenants,
        plus backup status, for Railway's own health checks and quick
        eyeballing without SSH."""
        from seira_core.tenancy import tripwire_all
        from seira_web.backup import list_backups
        from seira_web.r2 import r2_configured
        results = tripwire_all()
        halted = [t for t, r in results.items() if r.get("halted")]
        status_code = 503 if halted else 200
        daily = list_backups("daily")
        monthly = list_backups("monthly")
        return JSONResponse(
            {"tenants": len(results), "halted": halted,
             "backups": {
                 "daily": {"count": len(daily),
                          "latest": daily[0]["mtime"] if daily else None},
                 "monthly": {"count": len(monthly),
                            "latest": monthly[0]["mtime"] if monthly else None},
                 "r2_configured": r2_configured(),
             }},
            status_code=status_code)

    @app.get("/diary", response_class=HTMLResponse)
    def diary_page(request: Request, account: dict = Depends(require_account)):
        from seira_core.diary import DiaryStore
        from seira_core.tripwire import is_halted
        kind = request.query_params.get("kind", "self")
        if kind not in ("self", "architect"):
            kind = "self"
        with tenant_scope(account["tenant_id"]):
            if is_halted():
                return templates.TemplateResponse(request, "halted.html", {},
                                                  status_code=503)
            entries = list(reversed(DiaryStore().entries(kind=kind)))
        return templates.TemplateResponse(request, "diary.html",
                                          {"kind": kind, "entries": entries})

    return app


app = create_app()
