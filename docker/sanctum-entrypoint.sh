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

# stage2-hook.sh calls s6-setuidgid internally (line ~24) assuming it's
# on PATH — true only when invoked under s6-overlay's /init, which
# normally seeds PATH with s6's helpers. This entrypoint deliberately
# doesn't run /init (see the block comment above), so that seeding
# never happens and stage2-hook.sh fails immediately with
# "s6-setuidgid: not found", exit 127 — under `set -eu` that kills this
# script, which kills the container, which Railway restarts forever.
# Real, live crash-loop hit 2026-08-30; fixed by copying the exact
# precedent the project's own entrypoint-dispatch.sh already
# established for this identical situation (its non-PID-1 fallback
# path, when a platform wraps the image under its own init and s6
# can't take PID 1 either) rather than inventing a new pattern.
export PATH="/command:/package/admin/s6/command:${PATH}"

echo "[sanctum-entrypoint] running stage2 setup (shared with every Hermes deployment from this fork)"
/opt/hermes/docker/stage2-hook.sh

# stage2-hook.sh only fixes ownership of $HERMES_HOME — it has no
# knowledge of Sanctum-specific paths (SEIRA_TENANTS_ROOT, SEIRA_HOME),
# and reasonably shouldn't; embedding Sanctum specifics into the
# shared script would break that script's "one script, works for any
# deployment built from this fork" property. This is that same fix,
# scoped correctly to Sanctum's own entrypoint instead.
#
# Real, live failure hit 2026-08-30: her existing conversation data
# under SEIRA_TENANTS_ROOT predates this image running as a non-root
# user, so it's still owned by whatever UID ran the container before
# (almost certainly root) — Permission denied writing new turns as
# the now-non-root hermes user. This chown ONLY changes ownership
# metadata; it never touches file content, so no data is at risk.
# Runs after stage2-hook.sh (not before) so the "hermes" name is
# already correctly remapped if HERMES_UID overrides the default.
for _seira_path in "${SEIRA_TENANTS_ROOT:-}" "${SEIRA_HOME:-}"; do
    if [ -n "$_seira_path" ] && [ -d "$_seira_path" ]; then
        echo "[sanctum-entrypoint] fixing ownership of $_seira_path to hermes"
        chown -R hermes:hermes "$_seira_path" 2>/dev/null || \
            echo "[sanctum-entrypoint] Warning: chown $_seira_path failed (rootless container?) — continuing"
    fi
done

echo "[sanctum-entrypoint] starting Sanctum as the hermes user"
exec s6-setuidgid hermes python -m seira_web
