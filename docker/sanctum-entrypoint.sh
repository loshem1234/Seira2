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
# HOME comes through as /root (root's default, inherited from before
# s6-setuidgid drops privileges — that tool changes UID/GID only, never
# environment variables). Without this, anything resolving paths via
# $HOME (this specific failure: a Claude Code SDK path defaulting to
# ~/.claude/.credentials.json as one of several auth-source probes)
# tries to read/write under root-owned /root as the now-non-root
# hermes user and gets Permission denied. Real, live failure hit
# 2026-08-30. Same fix as docker/main-wrapper.sh and
# docker/hermes-exec-shim.sh already establish — but following
# $HERMES_HOME rather than hardcoding /opt/data like those two do,
# since this deployment deliberately overrides HERMES_HOME away from
# /opt/data (one shared Railway volume, mounted at /data, with
# HERMES_HOME=/data/hermes) — hardcoding /opt/data here would point
# HOME at a throwaway, non-persistent directory instead of the real
# volume. $HERMES_HOME already has the same "${HERMES_HOME:-/opt/data}"
# fallback as stage2-hook.sh itself uses, so this stays correct for a
# standard deployment too.
export HOME="${HERMES_HOME:-/opt/data}"

# Third instance of the same underlying gap (after PATH for
# s6-setuidgid and HOME itself): stage2-hook.sh writes some variables
# to /run/s6/container_environment/ (this one hit live, 2026-08-30:
# AGENT_BROWSER_EXECUTABLE_PATH, found while locating the Playwright
# Chromium binary for the browser toolset) expecting s6's own
# supervision to propagate them — a mechanism this entrypoint never
# runs. s6-overlay's own `with-contenv` is the general tool for this,
# but it reads the FULL container-environment snapshot, which could
# include the original (pre-fix) HOME and PATH values captured before
# this script changed them — wrapping the final exec with it risks
# silently re-introducing the exact two bugs already fixed above, and
# there's no way to verify with-contenv's override semantics without
# a real container to test against. Reading this one known file
# directly, after HOME/PATH are already set, is more code than
# reusing with-contenv generically, but it can't clobber anything.
if [ -f /run/s6/container_environment/AGENT_BROWSER_EXECUTABLE_PATH ]; then
    AGENT_BROWSER_EXECUTABLE_PATH="$(cat /run/s6/container_environment/AGENT_BROWSER_EXECUTABLE_PATH)"
    export AGENT_BROWSER_EXECUTABLE_PATH
    echo "[sanctum-entrypoint] browser executable: $AGENT_BROWSER_EXECUTABLE_PATH"
fi

exec s6-setuidgid hermes python -m seira_web
