# CHANGESET — She does her own conversation housekeeping now

Nine files. Four real changes, all from this round's direction.

    seira_web/conversations.py            — paginated full-transcript
                                            recall for revisiting a
                                            past chat
    seira_web/hermes_session.py           — the tool-iteration ceiling
                                            REMOVED (reverted); new
                                            run_housekeeping_turn()
    seira_web/conversation_summarizer.py  — weekly cadence; she does
                                            the work herself now
    seira_bridge/__init__.py              — 4 new tools for her
    tests/... (3 files updated/added)
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## First — confirmed directly, not just reassured

`autonomy.MAX_TURNS_PER_RUN` (10) and `autonomy.MIN_TURNS_FOR_SELF_STOP`
(3) were checked directly in the source and were never touched by
anything in the previous round. What got removed was a completely
separate thing — an inner limit on tool calls within one turn — not
your actual autonomous-mode metrics. Those are exactly as they've
always been.

## Cadence: weekly, not daily

Changed from once a day to once a week, as asked. The underlying logic
— only summarize a conversation that's actually had new activity since
its last summary — is unchanged; this just means the check itself
runs less often.

## The real redesign: it's hers now, not silent infrastructure

Before, a background process quietly called a bare text completion to
generate a title and summary — not her, just system code. Now, once a
week, she gets a real, fully governed turn — her real identity, her
real tools — and does the renaming and summarizing herself, using her
own judgment about what's actually worth remembering.

One thing worth knowing about how this is built: that turn is
deliberately kept out of the sidebar entirely, so it never shows up as
a weird "let me rename this" exchange inside whatever the conversation
was actually about. Her real work — the title, the summary — is
completely real and visible, through the same tools a human uses to
rename a chat; only the scaffolding asking her to do it stays hidden.
Verified by a test that confirms this scaffolding turn never touches
the conversation being labeled at all.

## Four new tools, hers to use any time

- `seira_conversation_list` — see every conversation, its title, and
  its current summary
- `seira_conversation_rename` / `seira_conversation_set_summary` — the
  actual work
- `seira_conversation_recall` — read back an ENTIRE past conversation,
  paginated, not capped the way a live turn's context is. This is the
  direct answer to "can she recall and revisit a chat" — she can pull
  up any past conversation in full, any time, on her own initiative.

## Specificity

The prompt now names exactly what NOT to write ("General Chat,"
"discussed various topics") and asks explicitly for real names, real
decisions, real numbers — directly addressing wanting summaries
specific enough to actually recall where and what a chat was.

## Testing

453 passed. Run:

    python -m pytest tests/seira_core/ -q
