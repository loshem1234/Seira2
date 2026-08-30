# CHANGESET — Fix the crash-loop: s6-setuidgid not found

Two files.

    docker/sanctum-entrypoint.sh   — THE FIX
    docs/seira/DECISIONS.md        — D141 appended

## What was happening

Your container was crash-looping: mount volume → stage2 setup starts →
`s6-setuidgid: not found` → script dies → Railway restarts → repeat,
forever. Cause: `stage2-hook.sh` calls `s6-setuidgid` assuming it's on
PATH, which is only true when run inside s6-overlay's normal
supervision (`/init`). My entrypoint deliberately skips that
supervision (Sanctum doesn't need it), so that assumption broke.

## The fix

One line added before calling `stage2-hook.sh`:

    export PATH="/command:/package/admin/s6/command:${PATH}"

This isn't invented — it's copied directly from
`docker/entrypoint-dispatch.sh`, which already solves this exact
problem in its own fallback path (for platforms that wrap the image
under their own init). Same problem, same proven solution, not a new
pattern.

I checked every other place `stage2-hook.sh` depends on an s6 command
(there are several `s6-setuidgid` calls) — all covered by this same
PATH fix. No second crash from this file expected.

## After applying

Redeploy. Watch the logs for `[sanctum-entrypoint] starting Sanctum as
the hermes user` — if you see that line without a crash right after
it, the entrypoint made it all the way through and Sanctum itself is
starting.

Run `python -m pytest tests/seira_core/ -q` — 273 passed.
