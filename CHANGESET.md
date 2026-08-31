# CHANGESET — Living Projects + Her Own Repository (complete, final)

This SUPERSEDES the previous "living-projects" zip entirely — same
eight files, further refined. Apply this one; you don't need the
earlier one at all. If you already applied the earlier one, just
overwrite with these — no separate merge step, no partial application.

## Replaces an existing file (6)

    seira_bridge/__init__.py       — full living-projects tool set,
                                     PLUS: initiative field, explicit
                                     discretion language, filtering
    seira_web/references.py        — reference records carry an
                                     optional `project` field
    agent/prompt_builder.py        — hermes mode's identity path
                                     appends the concise project index
    tests/seira_core/test_bridge.py — governance test updated with all
                                      new tool names
    docs/seira/WIRING.md           — Parts 11 and 12 both included
    docs/seira/DECISIONS.md        — D151 through D158 all included

## New file (2)

    seira_web/projects.py          — the whole subsystem
    tests/seira_core/test_projects.py — 36 tests total

## What's new in THIS round, on top of last time

You asked for something specific: not just the technical ability to
create a project unprompted (which, honestly, was already there — no
tool in this whole system has ever required explicit permission to
use) but an actual STATED discretion, and a real, visible record of
what she started on her own versus what was asked of her.

- `seira_project_create`'s description now says it directly: *"You do
  not need to be asked or given permission — the same discretion you
  already have to search the web or generate an image extends here."*
- Every project now honestly self-reports `initiative: "self" |
  "requested"` — same discipline as her diary's mandatory provenance
  field. Not a formality: the tool asks for it every time, so stating
  it is a real, conscious act.
- Self-initiated projects are marked `(her own initiative)` right in
  her always-visible index — visible, not just logged.
- `seira_project_list` (and the underlying function) can filter to
  `initiative='self'` — a genuine, browsable "what I started on my
  own" view, without needing a second, separate storage location.

## Testing

325 passed (316 from last round + 9 new). Run:

    python -m pytest tests/seira_core/ -q
