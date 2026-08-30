# CHANGESET — Fix: [Errno 13] on /root/.claude/.credentials.json

Two files. This REPLACES the previous sanctum-entrypoint.sh — apply
this one, not the earlier permission-fix zip.

    docker/sanctum-entrypoint.sh   — THE FIX
    docs/seira/DECISIONS.md        — D143 appended

## What was happening

`s6-setuidgid` (which drops the process from root to the `hermes`
user) changes only the UID/GID — it never touches environment
variables. So `HOME` stayed `/root` even after the switch. Something
(a Claude Code SDK credential probe, one of several optional
auth-source checks before falling back to your ANTHROPIC_API_KEY) tried
to read `~/.claude/.credentials.json`, which resolved to
`/root/.claude/...` — a directory the now-non-root process can't
touch.

This exact problem is already known and fixed elsewhere in this same
codebase (`docker/main-wrapper.sh`, `docker/hermes-exec-shim.sh`) — I
copied that fix rather than inventing a new one, with one adjustment:
those two hardcode `HOME=/opt/data`, which is wrong for YOUR specific
setup (you deliberately moved HERMES_HOME to `/data/hermes` on your
shared volume). This version follows `$HERMES_HOME` correctly instead
of hardcoding the default.

## After applying

Redeploy, then ask her to try again — this should be the fourth and
(hopefully) final piece of the Docker/permissions puzzle. If something
else surfaces, it'll be new information from a real, further-along
boot, same as each of the last few rounds.

Run `python -m pytest tests/seira_core/ -q` — 273 passed.
