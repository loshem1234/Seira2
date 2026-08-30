# CHANGESET — Fix: generated images had nowhere to go

Three files.

    tools/tool_search.py       — fixes the "found via tool_search,
                                 rejected on call" contradiction
    seira_web/hermes_session.py — THE MAIN FIX for your actual
                                  question: hermes mode now surfaces
                                  generated images and files
    docs/seira/DECISIONS.md    — D145, D146 appended

## The main answer: her images aren't lost

Before applying anything: she's not making images into a void. They're
saved to disk regardless of what the UI shows. You (or she) can view
any already-generated image right now at:

    https://<your-sanctum-host>/api/images/<img_id-or-tag>

Ask her to call her `seira_image_list` tool to get the img_ids/tags of
everything she's already made.

## What was actually broken

`chat.py` (the old direct-API mode) always knew how to turn a
successful `seira_generate_image` result into something the browser
could display — but that logic lived ONLY in chat.py's own loop.
Hermes mode (`hermes_session.py`) routes tool calls through the real
Hermes agent instead, which had no idea `seira_generate_image` was
special. Result: images generated successfully, silently, with no path
to your screen. Fixed by adding the same detection hermes mode was
missing — copied from chat.py's own logic, not reinvented.

Fixed the same gap for `seira_create_file` (generated documents) while
in there, since it's the identical bug on a sibling tool.

## The smaller, separate fix

`tools/tool_search.py` had a bug where a tool could show up in search
results and then get rejected as unreachable when actually called —
this is what caused the confusing `image_generate`
found-but-not-callable report. Fixed by making a previously-silent
failure visible instead (same pattern as the earlier write_file fix).
Doesn't change whether `image_generate` (the Hermes-native tool,
separate from her own `seira_generate_image`) actually works yet — that
one still needs `image_gen.provider` configured in config.yaml, which
is a deliberate safety gate, not a bug.

## After applying

Redeploy, ask her to generate one more image, and this time it should
appear right in the chat.

Run `python -m pytest tests/seira_core/ -q` — 273 passed.
