# CHANGESET — Images fixed correctly + documents get the same treatment

Eleven files. This is real architecture work, not a patch — read the
"what actually changed" section before applying, since two files
change SHAPE, not just behavior.

## Replaces an existing file (7)

    seira_bridge/__init__.py       — seira_image_recall now returns
                                     Hermes's native multimodal shape;
                                     two new tools (seira_reference_save,
                                     seira_reference_tag);
                                     seira_create_file auto-saves into
                                     the tagged Corpus
    seira_web/references.py        — full tagging added (mirrors
                                     images.py exactly)
    seira_web/images.py            — one new helper (get_image_data_uri)
    seira_web/hermes_session.py    — recognizes the new envelope,
                                     surfaces recall to the UI
    seira_web/chat.py              — direct mode updated to match (see
                                     "important" section below)
    tests/seira_core/test_vision.py     — one test updated for the new
                                          correct contract
    tests/seira_core/test_bridge.py     — governance test updated with
                                          the two new tool names
    docs/seira/WIRING.md           — Part 10 appended
    docs/seira/DECISIONS.md        — D148–D150 appended

## New file (2)

    tests/seira_core/test_references_documents.py  (tagging tests added)
    tests/seira_core/test_tagged_corpus.py          (new file)

## Important — why chat.py had to change too

`seira_image_recall` used to return a JSON string with a custom
`__image_block__` key. chat.py's direct mode (still used for
attachments and regeneration — hermes mode doesn't cover those yet)
knew how to unpack that specific shape. Changing the return shape
without updating chat.py would have silently broken direct mode. Both
paths are updated and tested — this isn't a hermes-mode-only fix.

## What actually changed, plainly

**Images:** recall now returns Hermes's own real multimodal format
instead of a lookalike. This is what makes the 2.28-million-character
truncation bug structurally impossible going forward, not just less
likely — verified by a test that calls Hermes's actual exemption
function and confirms it recognizes the new shape.

**Documents:** three sources — uploads (already worked), her own
generated files (new), and anything she deliberately keeps from the
web via the new `seira_reference_save` tool (new) — all write into one
tagged store. Generated documents join it automatically, no extra
step. Web content only gets saved when she chooses to, same discipline
as her diary.

## Testing

289 passed (274 pre-existing + 15 new tagging tests + 8 new bridge
tests, with 2 pre-existing tests correctly updated for the new
contract — not weakened). Run:

    python -m pytest tests/seira_core/ -q
