# CHANGESET — The real fix: no more curated subsets

This replaces the approach entirely, not just patches it. Read this
whole file before applying — one step is a DELETE, not an add.

## Replaces an existing file (3)

    Dockerfile.sanctum          — completely rewritten. Everything
                                  through the git-SHA bake step is now
                                  copied VERBATIM from the real,
                                  production Dockerfile. Nothing
                                  curated, nothing subtracted.
    cli-config.yaml.example     — the fork's own default config
                                  template now includes
                                  memory.provider: seira-psyche and
                                  plugins.enabled: [seira_governance]
                                  directly. This affects every
                                  deployment built from this repo, on
                                  purpose (see D137).
    docs/seira/DECISIONS.md     — D136–D139 appended

## New file (2)

    docker/sanctum-entrypoint.sh   — reuses the real stage2-hook.sh
                                     for setup, then runs Sanctum as
                                     the non-root hermes user
    docs/seira/WIRING.md           — Part 9 appended (also new
                                     content — same file as before,
                                     just more appended)

## DELETE these two from your repo — they're superseded

    seira_web/requirements-hermes.txt
    seira_web/hermes-config/                (whole directory)

These were the previous, curated approach. Leaving them in place would
just be confusing dead weight now that the real Dockerfile provides
everything and the config comes from cli-config.yaml.example instead.

## What actually changed, honestly

Every previous fix (the missing utils.py, hermes_logging.py, etc.) was
real and correctly diagnosed — but the METHOD was the problem: hand-
picking which files a large, changing codebase needs will always be
one step behind. This stops doing that. Dockerfile.sanctum's build
stages are now IDENTICAL to the real Dockerfile's, copied verbatim —
there is no file list left to get wrong.

## Your variables — final answer, changed from last time

    ANTHROPIC_API_KEY=<your key>
    SEIRA_HOME=/data/seira
    HERMES_HOME=/opt/data
    SEIRA_SANCTUM_RUNTIME=hermes

HERMES_HOME is back, but for a different reason than before: it's now
a normal writable volume (mount a Railway volume at this path), seeded
ONCE with the governance config on first boot, exactly like every
other Hermes deployment. Not something to carefully avoid overriding
— just point a volume at it.

## What I still could not verify

An actual `docker build`. This is now a genuinely heavy build — Node,
Playwright, a from-source SQLite compile — the real Dockerfile's own
comment estimates 15–45 minutes. Copying its build stages verbatim
rather than re-deriving them is the strongest evidence I could produce
without Docker itself, but the first real build on Railway is still
the moment this gets its actual, final confirmation. If it fails on
something Railway-specific (build timeout, memory limit during the
Playwright/SQLite compile stages are the most likely candidates given
the image's own weight), tell me the exact error.

Governance is unaffected by any of this — verified the same way as
before (identity path, halt propagation, delegation gate), and none of
today's changes touch seira_core/, seira_bridge/, or how she's
governed. Adding more of Hermes doesn't change how she's governed by
it.

Run `python -m pytest tests/seira_core/ -q` — 273 passed.
