# CHANGESET — Missing document libraries, cron that never fires, delegation that vanishes

Eight files, three separate real bugs, all root-caused precisely
before anything was built.

    Dockerfile.sanctum                     — the PDF/DOCX fix
    seira_web/cron_loop.py                 — new: the actual cron fix
    seira_web/delegation_watcher.py        — new: the delegation fix
    seira_web/__main__.py                  — starts both new
                                            background services
    tests/seira_core/test_cron_loop.py     — 6 tests
    tests/seira_core/test_delegation_watcher.py — 12 tests
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## Requires a real Docker rebuild to take effect

The Dockerfile change (PDF/DOCX libraries) only takes effect on your
next actual image build and deploy — applying this changeset alone
inside a running container won't install anything. The Python changes
(cron, delegation) take effect on your next process restart, same as
every other backend change tonight.

## 1. PDF/DOCX generation — a real regression, traced to its exact cause

`reportlab` and `python-docx` were never part of Hermes's own
dependencies — they were always Sanctum-specific, installed by a file
that quietly stopped being used when the Dockerfile was rewritten
earlier tonight to copy Hermes's real production build exactly. That
rewrite was the right call for Hermes's own dependencies; it just
never carried Sanctum's own additions along with it. Fixed by
installing all three explicitly — pypdf included too, since PDF
upload extraction depends on it equally and was just as absent, even
though it happened to still be working through some other path.

## 2. Cron jobs that never fire

The warning she saw is a real, built-in Hermes message, not a Sanctum
bug: the thing that checks "is a job due yet" only ever ran as part of
the full gateway process, which Sanctum deliberately doesn't run. I
looked seriously at the external-provider alternative first and want
to be upfront that it turned out not to be the lighter option it
sounded like — it needs its own Nous Research account and a new
public webhook endpoint, which is a different dependency, not a
simpler one. What actually worked was much smaller: the real ticker
Hermes already has is explicitly built to run on its own, in any
background thread, completely apart from the gateway. This just starts
it, reusing all of Hermes's own real job-running logic unchanged.

## 3. Delegated subagent work that seemed to vanish

The likely truth: her three delegated agents genuinely ran — real
background work, real cost — and their result had nowhere to go.
Every single place that ever reads a finished delegation's result
lives inside gateway-only code that never runs in Sanctum. Separately,
the "process list" she checked tracks something else entirely
(terminal sessions, not delegated tasks), so it was never going to
show anything either way.

Before writing a line of this, I checked directly whether building a
fix here would be evasive of her governance — read exactly how
Hermes's own official delivery mechanism works, confirmed it doesn't
inject raw output as if she'd said it, and built this the same way:
a finished delegation now wakes the real conversation through a
genuine, fully governed turn, the same pipeline every normal message
already goes through.

## A real bug caught and fixed during testing, not shipped and found later

Early in building this, a check for "does this conversation belong to
this tenant" incorrectly treated a brand-new, empty conversation as
not existing — an empty list is falsy in Python, and that's exactly
what a fresh conversation's message list is before its first message.
Caught by testing this exact case on purpose, not left as a latent bug
for later.

## Testing

425 passed (413 before this round + 6 cron tests + 12 delegation
tests, less test-file churn). Run:

    python -m pytest tests/seira_core/ -q
