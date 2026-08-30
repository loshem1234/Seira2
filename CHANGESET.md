# CHANGESET — Surface the real write_file/patch approval error

One file.

    model_tools.py

## What changed

Around line 1290-1305: the `except Exception as _edit_approval_err:`
block that produces "Edit approval denied: approval guard failed" for
`write_file`/`patch` was logging the real cause at `debug` level only
(invisible in normal Railway logs) and returning a generic message
with no diagnostic value.

Now:
- Logged at `warning` level with a full traceback (`exc_info=True`).
- The tool result text itself includes the real exception type and
  message, e.g. `Edit approval denied: approval guard failed
  (ModuleNotFoundError: ...)` — so next time this fires, ask her to
  paste the exact tool result and we'll know immediately what's wrong,
  instead of me having to guess blind from source.

This doesn't fix the underlying cause — it makes the cause visible,
which is the prerequisite for actually fixing it. Same pattern for
`tool_search`: ask her to run it and paste the raw JSON, specifically
`total_available` and the full (untruncated) match list.

Run `python -m pytest tests/seira_core/ -q` — 273 passed, unaffected
by this change (it's error-path only, no test currently exercises the
failure branch directly).
