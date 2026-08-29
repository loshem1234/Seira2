# CHANGESET — config.yaml baked into the image

Two files, on top of the previous "final" changeset. Apply these two
on top of everything you already applied.

    Dockerfile.sanctum                — now bakes in the config and
                                        sets HERMES_HOME itself
    seira_web/hermes-config/config.yaml   — new file: the two lines
                                            (memory.provider,
                                            plugins.enabled) that give
                                            her Psyche tools and the
                                            governance gate in hermes
                                            mode

## Do this on Railway

1. Apply both files.
2. If you already added a HERMES_HOME variable to Railway, REMOVE it
   (or set it to exactly /app/hermes-config). A Railway variable
   overrides the image's own default — leaving an old value in place
   would silently point at an empty path again.
3. Your variables should now be exactly:

       ANTHROPIC_API_KEY=<your key>
       SEIRA_HOME=/data/seira
       SEIRA_SANCTUM_RUNTIME=hermes

4. Redeploy.

Run `python -m pytest tests/seira_core/ -q` — 266 passed.
