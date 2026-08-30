# CHANGESET — Browser env-var fix + a real diagnostic step for you

Two files. Replaces the previous sanctum-entrypoint.sh again.

    docker/sanctum-entrypoint.sh   — THE FIX
    docs/seira/DECISIONS.md        — D144 appended (includes an
                                     approach I considered and
                                     rejected — worth reading, it's
                                     the reasoning, not just the code)

## Two things worth knowing before you apply this

**First — a correction, not a new bug.** "tool_search only shows 8
tools" was never actually evidence anything was missing.
`browser_navigate`, like `terminal` and `write_file`, is a core tool —
always directly available, never something you search for.
`tool_search` only ever lists the small set of optional plugin tools.
She caught this herself and corrected it; worth knowing so the same
false alarm doesn't come up again.

**Second — this fix addresses one real gap, but may not be the whole
picture.** Same root cause as the last two fixes: `stage2-hook.sh`
writes `AGENT_BROWSER_EXECUTABLE_PATH` expecting s6 supervision to
propagate it, which this entrypoint doesn't run. Fixed by reading that
one file directly (I deliberately did NOT use the more general
`with-contenv` wrapper here — it risked silently undoing the HOME/PATH
fixes from the last two rounds; see D144 for why).

## The diagnostic step — please run this before redeploying

The browser tool's PRIMARY Chromium detection doesn't depend on any of
the s6/entrypoint machinery at all — it just reads
`PLAYWRIGHT_BROWSERS_PATH`, a plain Docker environment variable that's
always inherited normally. If browser still fails after this fix,
that points somewhere different: Chromium may simply not be installed
in the built image at all (a build-time issue, not a runtime one).

Ask her to run, via her now-confirmed-working terminal:

    ls -la $PLAYWRIGHT_BROWSERS_PATH

If that lists real files (a `chromium-*` folder with a binary inside),
the image is fine and this entrypoint fix should resolve it. If the
directory is empty or doesn't exist, tell me that directly — it means
something about the Playwright install step in the build itself needs
a look, which is a different, more specific problem than anything
fixed so far.

Run `python -m pytest tests/seira_core/ -q` — 273 passed.
