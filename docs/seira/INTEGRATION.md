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
