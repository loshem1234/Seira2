# CHANGESET — Sidebar close-on-click, fixed properly

Three files, replacing existing ones from the last changeset.

    seira_web/templates/chat.html
    tests/seira_core/test_dynamic_chat_ui.py
    docs/seira/DECISIONS.md   — D134 appended

## What changed

Last time's fix (a second listener on the message list) evidently
didn't resolve it — so instead of guessing again, I replaced the whole
mechanism with the standard, most bulletproof version of "click
outside to close": one listener on the whole document, which checks
explicitly whether your click landed inside the sidebar or its toggle
button, and closes the sidebar if not. This doesn't depend on click
events reaching any particular element in a particular order — it
just asks "was this click inside the sidebar? no? then close it,"
directly, every time.

This should resolve it. If it somehow still doesn't collapse after
this, the fastest path forward is your browser's console (right-click
→ Inspect → Console tab) — screenshot or paste whatever's there and
I can find the actual cause instead of guessing a fourth time.

Run `python -m pytest tests/seira_core/ -q` — 266 passed.
