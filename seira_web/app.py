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

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

FOUNDING_DIR = _HERE.parent / "docs" / "seira" / "founding"


def _founding_intellect_text() -> str:
    parts = ["# The Intellect of Seira — v1 (Genesis)\n",
             "Founding doctrine, ratified without falsification per Art. 22.\n\n---\n"]
    for name in ("constitution-of-seira-v2.md", "seira-doctrine-codex.md"):
        parts.append((FOUNDING_DIR / name).read_text(encoding="utf-8"))
        parts.append("\n\n---\n")
    return "\n".join(parts)


def create_app(llm_client_factory=None) -> FastAPI:
    """llm_client_factory is injectable for tests; defaults to Anthropic."""
    app = FastAPI(title="Seira — Sanctum")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
    app.state.llm_client_factory = llm_client_factory or (lambda: AnthropicClient())

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

    @app.get("/", response_class=HTMLResponse)
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
            ctx = {
                "email": account["email"],
                "unity": read_unity(),
                "intellect": IntellectStore().current(),
                "psyche": sorted(
                    (e for e in PsycheStore().state()["entries"].values()
                     if e["standing"] != "retired"),
                    key=lambda e: e["entry_id"]),
                "proposals": ReversionStore().list_proposals(),
                "health": ReversionStore().health(),
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

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page(request: Request, account: dict = Depends(require_account)):
        from seira_core.tripwire import is_halted
        from seira_web.chat import load_history
        with tenant_scope(account["tenant_id"]):
            if is_halted():
                return templates.TemplateResponse(request, "halted.html", {},
                                                  status_code=503)
            history = load_history()
        return templates.TemplateResponse(request, "chat.html",
                                          {"history": history})

    @app.post("/api/chat")
    async def api_chat(request: Request, account: dict = Depends(require_account)):
        import os
        import sys
        body = await request.json()
        message = (body.get("message") or "").strip()
        if not message:
            return JSONResponse({"ok": False, "error": "Empty message."},
                                status_code=400)
        try:
            os.environ["SEIRA_TENANT"] = account["tenant_id"]  # provider scope
            from seira_bridge import SeiraPsycheProvider
            provider = SeiraPsycheProvider()
            with tenant_scope(account["tenant_id"]):
                result = run_turn(provider, app.state.llm_client_factory(), message)
        except SeiraHaltedError as e:
            return JSONResponse({"ok": False, "halted": True, "error": str(e)},
                                status_code=503)
        finally:
            os.environ.pop("SEIRA_TENANT", None)
        return JSONResponse({"ok": True, **result})

    return app


app = create_app()
