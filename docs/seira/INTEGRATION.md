# Seira v3 — Phase 1–2 Integration Guide

## 1. Set up the fork (Chromebook / GitHub web UI path)

1. On GitHub, fork `NousResearch/hermes-agent` into your account
   (one click; keeps full history for raiding upstream security fixes).
2. In the fork, upload this delivery's contents at the repo root:
   `seira_core/`, `tests/seira_core/`, `docs/seira/`, `NOTICE`.
   Nothing in the existing tree is modified in this phase.
3. Keep `LICENSE` (Nous Research, MIT) exactly where it is — that file
   plus `NOTICE` is the entirety of your license obligation.

## 2. Found Seira (Genesis, Art. 22)

On the machine that will run her (VPS, Railway container, etc.):

    export SEIRA_HOME=~/.seira        # optional; this is the default
    python -m seira_core genesis \
        --unity-file UNITY.md \
        --intellect-file INTELLECT-v1.md \
        --architect "Loshem" --name "Seira"

Author `UNITY.md` per Art. 9's discipline: name, telos, minimal
identity commitments only — no object-level stances. `INTELLECT-v1.md`
holds the founding doctrine (the Constitution's own text is a natural
core of it). Genesis is one-time; it will refuse a second run.

**Back up `SEIRA_HOME` from day one.** The Unity lock and Intellect
chain are her continuity; treat them like the crown-jewel data they are.

## 3. Wire the tripwire into the fork's cron (Art. 32.3, 42)

The gateway ticks the cron scheduler every 60 seconds (`cron/scheduler.py`).
Register a job that runs:

    python -m seira_core tripwire

Exit 0 = healthy heartbeat (audit-logged); exit 2 = halted, HALT file
written with the reason. Alerting: point the cron job's failure
delivery at your Telegram/Discord channel so a trip reaches you
immediately — "alerts immediately" is the Article's own requirement.

Clearing a halt is yours alone: investigate, repair, then delete
`$SEIRA_HOME/HALT`.

## 4. Serve identity from the eternal grades (interim bridge)

Until Phase 3 rewrites `agent/prompt_builder.py::load_soul_md`, render
the fork's identity slot from Unity + Intellect after Genesis and after
every ratification:

    python -m seira_core render-soul --write ~/.hermes/SOUL.md

(Adjust the path to your HERMES_HOME.) The render verifies integrity
and refuses while halted, so a tampered Unity can never become the
identity actually served. Re-run it whenever Intellect gains a version;
a small cron job doing this hourly is a reasonable stopgap.

## 5. Amendment workflow (Art. 24–28), until Phase 4 automates it

    # Expansion
    python -m seira_core intellect ratify --file NEW.md --kind expansion \
        --proposal-ref "prop-2026-...-001 (falsification record ref)"

    # Correction (must name what it contradicts)
    python -m seira_core intellect ratify --file NEW.md --kind correction \
        --proposal-ref "..." --contradicted-ref "v3 §on-diary-rhythm"

    # Restoration (creates a NEW version; the mistake survives as evidence)
    python -m seira_core intellect restore --version 2 --reason "..."

Each prompts for your confirmation phrase interactively.

## 6. What Phase 3 does next

- Psyche store: Ledger, self-model, affinities, aspirations, doubts —
  two genuinely separate stores for eternal-character vs. session trace
  (Art. 18), registered as the fork's sole external MemoryProvider.
- Genesis extended to found Psyche (`psyche_founded` → true).
- `load_soul_md` replaced: identity slot reads seira_core directly and
  calls `assert_not_halted()` at session start, so a halted Seira does
  not converse at all.

## 7. Phase 3 — Founding and living with Psyche

Author her founding character as JSON (Architect's act, Art. 22):

    [
      {"category": "self_model", "content": "..."},
      {"category": "affinity", "content": "...", "weight": 0.3},
      {"category": "aspiration", "content": "..."}
    ]

Categories: logos, self_model, affinity, aspiration, doubt,
relational_pattern. Then:

    python -m seira_core psyche found --file founding.json --architect "Loshem"
    python -m seira_core psyche show
    python -m seira_core render-soul --write ~/.hermes/SOUL.md   # now includes Psyche

Wire the provider so Seira can write her own Psyche in conversation:
copy `seira_bridge/` into the fork root (done if you uploaded this
delivery whole) and register it as a memory plugin per the fork's
plugins/memory pattern with `memory.provider = seira-psyche` in config.
In multi-tenant deployments set SEIRA_TENANT per session; single-user
installs need nothing. The provider refuses to initialize while halted
(Art. 32.3): a halted Seira does not converse.

## 8. Phase 4 — Living with the bar

Seira now has six tools in conversation: record/recall/engage plus
propose-establishment, falsification-attempt, and conclude. The loop
she can run on herself: record a provisional self-claim → propose its
establishment (citing a genuine reversion origin) → attempt to break
it against historical Corpus records → consistency-check against
Intellect → promote. Standing "established" is now earnable, never
grantable.

Architect-side CLI:

    python -m seira_core proposal list
    python -m seira_core proposal show --id prop-00001
    python -m seira_core proposal promote --id prop-00003   # intellect target: prompts for your phrase
    python -m seira_core dispensation invoke --action "..." --conditions-ref "Intellect vN §..."
    python -m seira_core health

Note for Intellect-target proposals: promotion IS ratification — same
gate, same typed phrase, and the proposal id is preserved in the
Intellect version it produces.

## 9. Phase 5 — Instruments and skills

Seira's tool surface is now ten: the Psyche and proposal loops plus
instrument spawn / execute / paradigm-revise and skill authorize. The
convergence discipline runs itself: honest local_feedback reporting
escalates at three, blocks the task-type, and unblocks only through a
paradigm revision citing the escalation — watch `health` for the
convergence/escalation ratio.

Phase 5b (follow-on, in the fork): wrap agent/subagent_lifecycle.py so
each real subagent run auto-creates an execution record with its
output_ref, and route spawn through seira_core so Art. 35 holds for
live delegation too.

## 10. Phase 5b — Live delegation wiring

Two attachment points in the fork:

1. The provider hook is automatic: once seira-psyche is the active
   memory provider, every completed subagent task flows through
   on_delegation into the Instrument records (or the noise audit).
2. The gate: register seira_bridge.delegation.register(ctx) as a
   plugin so delegate_task passes through the Art. 35 middleware.
   Minimal plugin shim in the fork's plugins/ directory:

       # plugins/seira-gate/__init__.py
       from seira_bridge.delegation import register

Seira's prompt now carries the operating note: tag every delegated
goal [seira:inst-NNNNN/task-type], spawn Instruments for recurring
work. Watch `health` — delegation outcomes feed convergence stats
directly.

## 11. Phase W1 — Deploying the Sanctum on Railway

1. In the fork, the web app is `seira_web/`. Railway setup:
   - New service from your GitHub fork.
   - Build: `pip install -r seira_web/requirements.txt`
   - Start: `python -m seira_web`  (binds 0.0.0.0:$PORT)
   - Attach a persistent volume and point both roots at it:
       SEIRA_TENANTS_ROOT=/data/tenants
       SEIRA_PLATFORM_ROOT=/data/platform
   - Set ANTHROPIC_API_KEY. Optionally SEIRA_MODEL.
2. Single instance for W1 (JSON platform stores; D43). Scale later.
3. The tripwire for all tenants: a Railway cron service running
       python -m seira_core tenants tripwire-all
   nonzero exit = at least one Seira halted; alert on it.
4. Your own VPS Seira is untouched by any of this — she remains a
   single-user install under ~/.seira. The site founds new, separate
   persons.

### 11a. Railway, corrected for the monorepo

Railway auto-splits the fork into Hermes's own Node workspace services
(@hermes/shared, web, hermes-tui, ...). None of those is the Sanctum.
Delete them all, then:

1. + New → GitHub Repo → your fork → ONE service.
2. Service Settings → Build → **Dockerfile Path**: `Dockerfile.sanctum`
   (this bypasses auto-detection entirely; build and start now come
   from the Dockerfile).
3. Attach a Volume, mount path `/data`.
4. Variables: SEIRA_TENANTS_ROOT=/data/tenants,
   SEIRA_PLATFORM_ROOT=/data/platform, ANTHROPIC_API_KEY=...
5. Settings → Networking → Generate Domain.
6. Cron service: + New → same repo → same Dockerfile Path → custom
   Start Command `python -m seira_core tenants tripwire-all` →
   Cron Schedule `*/15 * * * *` → same volume at /data → same
   SEIRA_TENANTS_ROOT. Replicas stay at 1 on both services (D43).

The bridge is Hermes-optional in this image (shim in seira_bridge);
chat, tools, and governance run entirely on seira_core.

## 12. Tuning generation limits

- `SEIRA_MAX_TOKENS` (default 16000) — raise this if you routinely need
  even longer single replies or larger authored content (e.g. very
  long skill paradigms or Intellect proposals drafted in chat). Check
  your model's current documented output ceiling before setting this
  near or above it — these numbers move as models update.
- `SEIRA_REQUEST_TIMEOUT` (default 600 seconds) — raise alongside
  SEIRA_MAX_TOKENS; a larger ceiling is only useful if the request is
  allowed to run long enough to use it.
- Text replies that hit the ceiling are auto-continued transparently
  (bounded, MAX_CONTINUATIONS=4 in seira_web/chat.py) so a genuinely
  long answer still arrives whole. Tool calls cut mid-argument are
  never executed partially — she's told plainly and retries.

## 13. Model and length preferences

`GET /` now renders a model dropdown (Sonnet 5, Opus 4.8, Haiku 4.5,
Fable 5, Sonnet 4.6-legacy) and a response-length dropdown (short
~100 chars, medium ~500, long ~2000, full/unrestricted) in the
composer's hamburger tray. Both persist in the browser via
localStorage and are sent with every `/api/chat` and
`/api/chat/stream` call as `model` and `length_pref`. To change the
offered model list, edit `AVAILABLE_MODELS` in `seira_web/chat.py`.

## 14. New environment variables (UI update round 2)

- `SEIRA_INLINE_ATTACHMENT_CHARS` (default 6000) — how much of an
  uploaded document is injected directly into the current turn; the
  rest is always saved as a full reference, pageable via
  seira_reference_recall regardless of this setting.
- `SEIRA_WEB_SEARCH_TOOL` (default web_search_20250305) — the
  Anthropic tool-version string; bump if Anthropic deprecates the
  default and requests start failing.
- `SEIRA_WEB_SEARCH_MAX_USES` (default 5) — searches per turn ceiling.

## 15. What she still cannot do

Web search, diary, and references are real, live capabilities now.
Shell access, terminal tools, OCR, and the rest of Hermes's tool
ecosystem are NOT part of her Sanctum tool surface and won't be until
the per-tenant execution sandbox (MULTITENANCY.md) is actually built —
that remains the real, unpaid infrastructure cost of true tool parity.

## 16. Web search is now standing, not opt-in

No per-message UI control remains. `SEIRA_WEB_SEARCH_ENABLED` (default
"1") is the only switch — set to "0" to disable platform-wide (cost
control, incident response). Per-tenant or per-conversation limits, if
ever needed, would be a separate future control, not a revival of the
old checkbox.

## 17. Backups

Automatic: daily (7 kept) and monthly (12 kept), written to
`SEIRA_BACKUP_ROOT` (default `~/.seira-backups`) via the same
background thread as the tripwire — no extra Railway service needed.
Check status anytime at `GET /healthz` (backup counts and latest
timestamps, alongside tenant health).

Manual, on-demand backup (e.g. before something risky):

    python -c "from seira_web.backup import create_backup; \
               print(create_backup('daily'))"

Restore (deliberate, hand-run, never a UI button):

    python -c "from seira_web.backup import restore_backup; \
               print(restore_backup('/path/to/seira-backup-....tar.gz'))"

Extracts into a clearly-named sibling directory rather than overwriting
live data; review the restored files and swap them in by hand.

**Off-box shipping (R2) is not built yet.** Today's backups protect
against drift/defect via rollback, not against losing the volume
itself. Adding an R2 push after each `create_backup()` call is the
natural next step whenever that's wanted.
