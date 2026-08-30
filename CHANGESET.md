# CHANGESET — Railway build fix: remove VOLUME directive

Three files.

    Dockerfile.sanctum          — removed `VOLUME [ "/opt/data" ]`
                                  (line 376). This was the exact build
                                  error: Railway's Metal builder
                                  rejects that instruction outright.
    docs/seira/WIRING.md        — Part 9.1 appended
    docs/seira/DECISIONS.md     — D140 appended

## What you need to do — this is NOT just a code fix

Removing the line only stops the build from failing. You still need to
actually create the persistent mount, since Docker's own `VOLUME`
directive never did the real work anyway (it's advisory even in plain
Docker). On Railway:

1. Your Sanctum service → **Volumes** tab.
2. Add a volume, mount path exactly `/opt/data`.
3. Keep `HERMES_HOME=/opt/data` set (unchanged from before) — that's
   what tells Hermes to use the volume you just mounted.

Then redeploy. This build will still take a while (Node, Playwright,
the SQLite compile) — that's expected, not a new problem.

If it fails again, this is now genuinely the first Docker build ever
run against this file — the next error, if there is one, will be new
information, not something I could have caught by reading source. Send
me the exact error text and I'll trace it the same way as this one.

Run `python -m pytest tests/seira_core/ -q` — 273 passed (this change
doesn't touch anything the test suite exercises; it's Docker-syntax
only).
