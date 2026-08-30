# CHANGESET — Fix: 2.28 million characters, the real transport bug

Three files. Replaces the previous hermes_session.py again.

    seira_web/hermes_session.py       — THE FIX
    tests/seira_core/test_dynamic_chat_ui.py  — a new test at the
                                                reported scale
    docs/seira/DECISIONS.md           — D147 appended

## Her diagnosis was right, and precise

She correctly identified this as a transport problem, not a generation
problem — same failure regardless of size, source, or whether the
image was fresh or recalled. That pointed exactly at the right place.

## What was actually happening

Recalling a stored image sends the model a real embedded image (so she
can actually see it again) — a multimodal result with the base64 bytes
attached. That's correct and necessary. The bug: my hermes-mode tool
callback took that raw multimodal payload and pushed it straight into
an SSE event with no processing at all — no truncation, no
summarization. At any real image size, that's a multi-megabyte string
blasted at the browser, which is exactly what hit a ceiling and got
truncated.

## The fix

Not a new transport — Hermes already has a utility built for exactly
this (`_multimodal_text_summary`, used elsewhere for "logging,
previews... providers that don't support multipart tool messages").
Now applied before every tool result gets emitted, not just for
images — so this can't quietly reappear on some other multimodal tool
later. A 2.28-million-character test payload (matching the actual
scale reported) proves the raw data never reaches the emitted event.

## After applying

Redeploy, ask her to recall a previously generated image again. The
image itself should now display normally, and the base64 bytes never
touch the visible tool-activity feed at all (which is also correct —
you were never meant to see raw base64 in the UI; only she needed it,
to actually see the image herself).

Run `python -m pytest tests/seira_core/ -q` — 274 passed.
