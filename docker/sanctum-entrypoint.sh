#!/bin/sh
# Sanctum's entrypoint. Deliberately NOT s6-overlay/gateway supervision —
# Sanctum is one FastAPI process, not a multi-service gateway+dashboard
# deployment, so it doesn't need process supervision for services it
# never runs.
#
# What it DOES reuse, on purpose, rather than reinvent: the real image's
# own stage2-hook.sh — UID/GID remap, volume permissions, and, critically,
# config.yaml seeding from cli-config.yaml.example (the fork's own
# default template, which now bakes in memory.provider: seira-psyche and
# plugins.enabled: [seira_governance] — see cli-config.yaml.example and
# docs/seira/DECISIONS.md D136). Reusing this script means Sanctum's
# config-seeding behavior is IDENTICAL to every other deployment built
# from this fork, not a second, parallel mechanism that could drift out
# of sync with it.
set -eu

echo "[sanctum-entrypoint] running stage2 setup (shared with every Hermes deployment from this fork)"
/opt/hermes/docker/stage2-hook.sh

echo "[sanctum-entrypoint] starting Sanctum as the hermes user"
# /command/ (where s6-setuidgid lives) is only added to PATH for children
# of the s6 supervision tree, which this entrypoint deliberately doesn't
# run — same gap docker/hermes-exec-shim.sh already documents and works
# around with an absolute path. Doing the same here rather than adding
# /command to PATH globally, which would be a wider, unreviewed change.
exec /command/s6-setuidgid hermes python -m seira_web
