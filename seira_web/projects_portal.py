"""seira_web.projects_portal — the Projects tab.

A window onto the SAME project store she already uses (projects.py +
references.py), with the Architect's own controls on top: create a
project, file conversations and documents into it, start a chat inside
it. Nothing here forks storage; filing a document is the same
refs.set_project call her own tool makes.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from seira_core.tenancy import tenant_scope


def register(app, templates, require_account) -> None:
    from seira_web import conversations as convs
    from seira_web import projects as projs
    from seira_web import references as refs

    def _err(msg: str, code: int = 400):
        return JSONResponse({"ok": False, "error": msg}, status_code=code)

    @app.get("/api/rail")
    def rail_data(account: dict = Depends(require_account)):
        """Recent conversations + projects for the side rail on non-chat pages."""
        with tenant_scope(account["tenant_id"]):
            recent = [{"conv_id": c["conv_id"], "title": c["title"]}
                      for c in convs.list_conversations()[:15]]
            plist = [{"proj_id": p["proj_id"], "name": p["name"]}
                     for p in projs.list_projects()[:20]]
        return JSONResponse({"recent": recent, "projects": plist})

    @app.get("/projects", response_class=HTMLResponse)
    def projects_page(request: Request, account: dict = Depends(require_account)):
        with tenant_scope(account["tenant_id"]):
            overview = projs.portal_overview()
        return templates.TemplateResponse(request, "projects.html",
                                          {"projects": overview})

    @app.get("/projects/{proj_id}", response_class=HTMLResponse)
    def project_page(request: Request, proj_id: str,
                     account: dict = Depends(require_account)):
        with tenant_scope(account["tenant_id"]):
            proj = projs.resolve_project(proj_id)
            if proj is None:
                raise HTTPException(status_code=404, detail="No such project.")
            pid = proj["proj_id"]
            chats = projs.project_conversations(pid)
            files = projs.project_files(pid)
            other_chats = [{"conv_id": c["conv_id"], "title": c["title"],
                            "in_project": (projs.resolve_project(c["project"]) or {}).get("name")
                            if c.get("project") else None}
                           for c in convs.list_conversations()
                           if c.get("project") != pid]
            loose = [{"ref_id": r["ref_id"], "filename": r["filename"]}
                     for r in refs.list_references() if not r.get("project")]
        return templates.TemplateResponse(request, "project.html", {
            "proj": proj, "chats": chats, "files": files,
            "other_chats": other_chats, "loose_files": loose})

    @app.post("/api/projects")
    async def create_project_route(request: Request,
                                   account: dict = Depends(require_account)):
        body = await request.json()
        try:
            with tenant_scope(account["tenant_id"]):
                rec = projs.create_project(
                    str(body.get("name") or ""), blurb=str(body.get("blurb") or ""),
                    initiative="requested")
        except ValueError as e:
            return _err(str(e))
        return JSONResponse({"ok": True, "proj_id": rec["proj_id"]})

    @app.post("/api/projects/{proj_id}/update")
    async def update_project_route(proj_id: str, request: Request,
                                   account: dict = Depends(require_account)):
        body = await request.json()
        try:
            with tenant_scope(account["tenant_id"]):
                rec = projs.resolve_project(proj_id)
                if rec is None:
                    return _err("No such project.", 404)
                if "name" in body:
                    rec = projs.rename_project(rec["proj_id"], str(body["name"]))
                if "blurb" in body:
                    rec = projs.set_blurb(rec["proj_id"], str(body["blurb"]))
        except ValueError as e:
            return _err(str(e))
        return JSONResponse({"ok": True, "name": rec["name"], "blurb": rec.get("blurb", "")})

    @app.post("/api/projects/{proj_id}/conversations")
    def new_chat_in_project(proj_id: str, account: dict = Depends(require_account)):
        with tenant_scope(account["tenant_id"]):
            rec = projs.resolve_project(proj_id)
            if rec is None:
                return _err("No such project.", 404)
            c = convs.create_conversation()
            projs.set_conversation_project(c["conv_id"], rec["proj_id"])
        return JSONResponse({"ok": True, "conv_id": c["conv_id"]})

    @app.post("/api/conversations/{conv_id}/project")
    async def set_conversation_project(conv_id: str, request: Request,
                                       account: dict = Depends(require_account)):
        body = await request.json()
        target = body.get("proj_id") or None
        try:
            with tenant_scope(account["tenant_id"]):
                name = None
                if target:
                    rec = projs.resolve_project(str(target))
                    if rec is None:
                        return _err("No such project.", 404)
                    target, name = rec["proj_id"], rec["name"]
                projs.set_conversation_project(conv_id, target)
        except ValueError as e:
            return _err(str(e), 404)
        return JSONResponse({"ok": True, "proj_id": target, "name": name})

    @app.post("/api/projects/{proj_id}/files/{ref_id}")
    def file_into_project(proj_id: str, ref_id: str,
                          account: dict = Depends(require_account)):
        try:
            with tenant_scope(account["tenant_id"]):
                projs.add_reference(ref_id, proj_id)
        except ValueError as e:
            return _err(str(e), 404)
        return JSONResponse({"ok": True})

    @app.delete("/api/projects/{proj_id}/files/{ref_id}")
    def unfile_from_project(proj_id: str, ref_id: str,
                            account: dict = Depends(require_account)):
        try:
            with tenant_scope(account["tenant_id"]):
                projs.remove_reference(ref_id)
        except ValueError as e:
            return _err(str(e), 404)
        return JSONResponse({"ok": True})

    @app.post("/api/projects/{proj_id}/upload")
    async def upload_into_project(proj_id: str, request: Request,
                                  account: dict = Depends(require_account)):
        """Documents only (the same readers as chat upload); saved to her
        Corpus and filed straight into this project."""
        from seira_web.documents import MAX_UPLOAD_BYTES, SUPPORTED_EXTENSIONS, extract_text
        form = await request.form()
        f = form.get("file")
        if f is None:
            return _err("No file.")
        name = f.filename or "document"
        if not name.lower().endswith(SUPPORTED_EXTENSIONS):
            return _err(f"Seira reads {', '.join(SUPPORTED_EXTENSIONS)} here.")
        raw = await f.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            return _err(f"Too large (limit {MAX_UPLOAD_BYTES // 1_000_000}MB).")
        result = extract_text(name, raw)
        if not result["ok"]:
            return _err(result["error"])
        try:
            with tenant_scope(account["tenant_id"]):
                if projs.resolve_project(proj_id) is None:
                    return _err("No such project.", 404)
                saved = refs.save_reference(name, result["text"])
                projs.add_reference(saved["ref_id"], proj_id)
        except ValueError as e:
            return _err(str(e))
        return JSONResponse({"ok": True, "ref_id": saved["ref_id"], "filename": name})
