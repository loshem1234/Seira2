# CHANGESET — The Archive page

Seven files. This is a straightforward addition on top of everything
already applied — nothing here touches the projects/references/images
storage itself, only reads it.

## Replaces an existing file (5)

    seira_web/app.py               — two new routes: /archive and
                                     /archive/reference/{ref_id}
    seira_web/templates/base.html  — "Archive" added to the hamburger
                                     menu
    tests/seira_core/test_ui_update_app.py — 7 new tests
    docs/seira/WIRING.md           — Part 13 appended
    docs/seira/DECISIONS.md        — D159–D161 appended

## New file (2)

    seira_web/templates/archive.html            — the main page
    seira_web/templates/archive_reference.html  — the read-only
                                                  document viewer

## What you'll see

Open the hamburger menu → Archive. Three tabs:

- **Projects** — every living project, marked when it was her own
  initiative, with every document filed under it.
- **Documents** — anything not currently grouped into a project.
- **Images** — a thumbnail gallery.

Click any document to read it in full, read-only.

## Read-only, actually — not just by convention

No route this adds accepts anything but GET. Nothing here can modify
her Corpus — it's the same data her own tools already write to, just
made visible to you. Verified by test, not just intended: the document
viewer's content area is checked for the literal absence of a `<form>`
element.

## One technical detail worth knowing

Documents can be long, and the underlying read function caps each
internal call at 40,000 characters — a limit that exists to keep HER
reads bounded, not yours. The viewer loops that call server-side to
assemble a full page (up to 300,000 characters) rather than paginating
in the browser. There's a test specifically checking that the END of a
long document actually appears on the page, not just its first chunk.

## Testing

332 passed (325 before this round + 7 new). Run:

    python -m pytest tests/seira_core/ -q
