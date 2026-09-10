# CHANGESET — Auto-titled, self-summarizing conversations

Eight files. New capability, no bug fix this time.

    seira_web/conversation_summarizer.py — new: the background pass
    seira_web/conversations.py            — title_user_set tracking,
                                            the new update function
    seira_web/__main__.py                 — starts the new background
                                            service
    seira_web/templates/chat.html         — the summary icon + popover
    seira_web/static/style.css            — its styling
    tests/seira_core/test_conversation_summarizer.py — 22 tests
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## What you'll see

Every conversation in the sidebar now keeps itself labeled on its
own. Once a day (but only for conversations that actually had new
messages since their last summary — an untouched conversation costs
nothing), each one gets a short auto-generated title and a few bullet
points describing what's actually in it. A small icon appears next to
any conversation that has a summary — click or tap it to see the
bullets, or just hover the conversation name itself for a quick native
tooltip. Both work, since tapping is what actually works on a phone.

## Two things worth knowing

If you've renamed a conversation yourself, that name is permanent —
the auto-namer will never touch it, only conversations you've never
renamed get an automatic title. And a background summary pass never
bumps a conversation to the top of the list by itself; only you
actually talking in it does that.

## Testing

447 passed (425 before this round + 22 new). Run:

    python -m pytest tests/seira_core/ -q
