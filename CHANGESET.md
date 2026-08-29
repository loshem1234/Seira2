# CHANGESET — Everything since changeset 1, including the Docker fix

This supersedes the earlier "combined" zip — it has everything that
one had, PLUS the fix for the ModuleNotFoundError you hit. Apply this
one zip; you don't need any earlier changeset zip.

## Replaces an existing file (6)

    Dockerfile.sanctum              — THE FIX. Now copies the real
                                      Hermes agent code and installs
                                      its dependencies. Read the block
                                      comment at the top of the file —
                                      it explains exactly what's
                                      included, what's deliberately
                                      excluded, and why.
    seira_web/chat.py
    seira_web/templates/chat.html
    seira_web/static/style.css
    docs/seira/WIRING.md            — Parts 5–8 appended
    docs/seira/DECISIONS.md         — D124–D135 appended (overwrite
                                      only if yours still matches
                                      changeset 1; otherwise append
                                      the tails by hand)

## New file (6)

    seira_web/hermes_tools.py
    seira_web/hermes_session.py
    seira_web/requirements-hermes.txt   — the Hermes dependency list
                                          Dockerfile.sanctum installs
    tests/seira_core/test_hermes_tools_bridge.py
    tests/seira_core/test_hermes_session.py
    tests/seira_core/test_dynamic_chat_ui.py

## What actually happened, in order

1. `SEIRA_SANCTUM_RUNTIME=hermes` was set, and it failed with
   `ModuleNotFoundError: run_agent`.
2. The cause: `Dockerfile.sanctum` was built for an earlier phase and
   never contained the Hermes agent code — a real gap, not something
   wrong with the flag itself.
3. I tested — actually tested, isolated venv and isolated file copy,
   not read-and-assume — exactly which files and which pip packages
   are needed to import and run a per-turn Hermes agent call. That
   list is now in `Dockerfile.sanctum` and
   `seira_web/requirements-hermes.txt`.
4. What I could NOT test here: an actual `docker build` (no Docker in
   this environment). The dependency install and file-copy set were
   each verified as isolated stand-ins for that — strong evidence, not
   a substitute for watching the real build succeed on Railway.

## After applying

Redeploy on Railway (this will rebuild the image — expect a longer
build than before, since it's now installing ~30 more Python packages
and copying ~38MB more source; still no compiler toolchain, no Node,
no Playwright). Once it builds, test one real conversation with
`SEIRA_SANCTUM_RUNTIME=hermes` set before relying on it daily.

If the build fails on something Railway-specific, that's the one part
of this I genuinely couldn't verify from here — tell me the exact
error and I'll help you work through it.

Run `python -m pytest tests/seira_core/ -q` — 266 passed on this
changeset.
