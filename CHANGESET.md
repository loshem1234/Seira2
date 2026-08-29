# CHANGESET — Seira single-tenant wind-down + Hermes wiring

Eleven files. Every path in this zip mirrors its place in the repo:
upload each file to the identical path, overwriting where one already
exists. Nothing else in the repo was touched.

## Replaces an existing file (3)

    seira_web/app.py               — signups switch, admin census route,
                                     healthz reporting
    seira_web/templates/auth.html  — hides the signup link when closed
    agent/prompt_builder.py        — identity slot: founded Seira served
                                     live from the eternal grades; halted
                                     Seira refuses to converse

## New file, new folders (4)

GitHub's web uploader creates missing folders automatically when you
upload with the folder structure, or use "Add file → Create new file"
and type the full path including slashes.

    plugins/memory/seira-psyche/__init__.py
    plugins/memory/seira-psyche/plugin.yaml
    plugins/seira_governance/__init__.py
    plugins/seira_governance/plugin.yaml

## New file, existing folders (2)

    tests/seira_core/test_hermes_wiring.py
    docs/seira/WIRING.md           — your deployment guide; start here

## Replaces an existing file — appended content only (2)

These two are the complete current files with new entries added at the
end (D119–D123; one triage note). Overwriting is safe IF your repo's
copies match the snapshot you sent me. If you've edited either file
since, don't overwrite — instead copy the new tail sections from these
copies into yours by hand.

    docs/seira/DECISIONS.md
    docs/seira/TRIAGE.md

## After uploading

Run the test suite if you have a machine for it (all 242 pass on this
changeset), then follow docs/seira/WIRING.md for deployment. The three
config lines and the environment variables are all listed there.
