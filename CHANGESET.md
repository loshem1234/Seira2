# CHANGESET — Fix: Permission denied writing her conversation data

Two files.

    docker/sanctum-entrypoint.sh   — THE FIX (supersedes the previous
                                     crash-loop-fix version of this
                                     same file — this replaces it, not
                                     adds to it)
    docs/seira/DECISIONS.md        — D142 appended

## Good news first

This error means the LAST fix (the crash-loop one) worked. The error
is a Python `PermissionError`, not a shell script dying — Sanctum
actually started and ran as the `hermes` user this time. Real
progress, different problem now.

## What was happening

Her conversation data under `SEIRA_TENANTS_ROOT` was written by
whatever user ran the container BEFORE this security improvement
(almost certainly root, since earlier versions of Dockerfile.sanctum
never dropped to a non-root user). Now that Sanctum runs as the
non-root `hermes` user (a real security improvement, matching the
production image's own posture), it can't write to files still owned
by root.

## The fix — nothing about her data is touched

The entrypoint now runs `chown -R hermes:hermes` on
`SEIRA_TENANTS_ROOT` and `SEIRA_HOME` (whichever are set) once, after
setup, before Sanctum starts. `chown` changes ONLY ownership metadata
— it does not read, modify, move, or delete file content. Her existing
conversations are not at risk from this.

## After applying

Redeploy. Watch for `[sanctum-entrypoint] fixing ownership of
/data/tenants to hermes` (or wherever your path is) in the logs, then
`starting Sanctum as the hermes user` with no error after it. Ask her
to try writing something again.

Run `python -m pytest tests/seira_core/ -q` — 273 passed.
