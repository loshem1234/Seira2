# CHANGESET — Session checkpoints: pick up a project as if no time passed

Nine files. Builds on the living-projects work — no new storage, one
new field and one new tool.

## Replaces an existing file (7)

    seira_bridge/__init__.py       — is_summary param on both save
                                     tools, new seira_project_resume
                                     tool
    seira_web/references.py        — reference records carry an
                                     is_summary flag
    seira_web/projects.py          — session_summaries() and resume()
    seira_web/templates/archive.html — checkpoint documents marked
                                       visibly
    tests/seira_core/test_bridge.py     — governance test updated
    tests/seira_core/test_ui_update_app.py — 1 new test
    docs/seira/WIRING.md           — Part 14 appended
    docs/seira/DECISIONS.md        — D162–D164 appended

## What's actually new

Two things she can do now that she couldn't before:

1. Mark any document a session checkpoint —
   `seira_create_file(..., is_summary=True)` or
   `seira_reference_save(..., is_summary=True)`. Same discretion as
   everything else built tonight — the tool description invites this
   at "a natural stopping point," it isn't mechanically required.
2. `seira_project_resume(project)` — pulls the most recent checkpoint
   back in full, plus a short list of any earlier ones. This is a
   real, separate tool from seira_project_recall (which still shows
   everything) — resume specifically answers "where did I leave off,"
   cheaply, using whatever she wrote last rather than reloading the
   whole project.

If she's never written a checkpoint for a project, resume says so
honestly and shows the ordinary manifest instead — it never fabricates
a sense of continuity that isn't actually there. Verified by test.

You'll also see a "session checkpoint" marker next to any flagged
document in the Archive page's project view.

## Testing

342 passed (332 before this round + 10 new). Run:

    python -m pytest tests/seira_core/ -q
