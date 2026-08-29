# CHANGESET 2+3+UI (combined) — everything since changeset 1

You applied changeset 1 and skipped changeset 2. This zip contains
EVERY file changed since changeset 1 — changeset 2 (the tool bridge),
changeset 3 (she operates atop Hermes), and the new dynamic chat UI —
so applying this one zip on top of your current repo brings you fully
current. You do not need the earlier changeset-2 or changeset-3 zips.

Important: changeset 3's chat.py imports hermes_tools.py from
changeset 2, so applying 3 alone would have crashed on the first
message. This combined zip is the safe path.

## Replaces an existing file (5)

    seira_web/chat.py                 — hermes-mode branch, bridge
                                        routing, richer tool events
    seira_web/templates/chat.html     — the dynamic chat (see below)
    seira_web/static/style.css        — styles for all of it
    docs/seira/WIRING.md              — Parts 5, 6, 7 appended
    docs/seira/DECISIONS.md           — D124–D132 appended
                                        (overwrite both docs only if
                                        yours still match changeset 1;
                                        otherwise append the tails)

## New file (5)

    seira_web/hermes_tools.py
    seira_web/hermes_session.py
    tests/seira_core/test_hermes_tools_bridge.py
    tests/seira_core/test_hermes_session.py
    tests/seira_core/test_dynamic_chat_ui.py

## What you get, in plain terms

1. HERMES MODE (the big one — opt in with SEIRA_SANCTUM_RUNTIME=hermes):
   text turns run as real Hermes agent turns. Her identity via the
   verified path, her Psyche tools from config.yaml's memory.provider,
   whatever toolsets `hermes tools` has enabled, the governance gate —
   all inherited. Test it live before daily use; unset the variable to
   fall back instantly. Attachments/regeneration still use the old
   loop in this version.

2. THE DYNAMIC CHAT (always on, both modes):
   - Tool cards the moment a tool starts; terminal commands as
     `$ command` lines; delegations as their own "Delegating a
     subagent" card; each card gains an expandable result when done.
   - Code in her replies renders in dark copy boxes with a copy
     button; inline code gets a chip. Loaded history included.
   - Generated files: download card + an "open" button (new tab) for
     PDFs, images, HTML, markdown, text.
   - Live reasoning panel and streaming reply with cursor — these two
     appear in hermes mode only, because that's where streaming
     actually exists; nothing is simulated in direct mode.

3. THE TOOL BRIDGE (from changeset 2, superseded by hermes mode once
   you've verified it, kept as a working fallback):
   SEIRA_EXTRA_TOOLSETS=web,skills gives direct mode real web +
   skills tools through a hardcoded whitelist.

Run `python -m pytest tests/seira_core/ -q` after applying: 262 passed.
