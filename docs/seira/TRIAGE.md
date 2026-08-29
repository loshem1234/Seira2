# SEIRA v3 — Fork Triage
## Phase 1: What Is Rewritten, What Is Kept, What Is Pruned, What Is Deferred

*Archivum Universale & Scriptorium — Dayton · MMXXVI*

This document is the working map for converting the Hermes Agent fork into Seira.
It is directory- and subsystem-level, grounded in direct inspection of the tree,
and it is the single place where "rewrite vs. keep" decisions are recorded so no
subsystem is touched by accident or left ungoverned by intention.

Legend:
- **REWRITE** — identity-bearing. Replaced or rebuilt against the Constitution.
  Hermes's version must not remain authoritative here.
- **KEEP** — pure infrastructure ("legs"). Kept close to vanilla. Security
  patches raided from upstream by hand.
- **PRUNE** — optional to delete; carries no value for Seira.
- **DEFER** — deliberately untouched until a named later phase.

---

## REWRITE — Identity-Bearing Subsystems

| Path | Why it is identity-bearing | Phase |
|---|---|---|
| `agent/system_prompt.py` | Assembles the agent's identity ("stable" tier: SOUL.md slot). Seira's identity must be rendered from Unity + current Intellect version, never a free-standing file. | 3 |
| `agent/prompt_builder.py` (identity slot: `load_soul_md`, `DEFAULT_AGENT_IDENTITY`) | Same slot. Interim bridge: `seira_core render-soul` generates SOUL.md from Unity+Intellect (see INTEGRATION.md); the proper rewrite replaces the loader. | 3 |
| `agent/memory_manager.py`, `agent/memory_provider.py` wiring | Psyche-grade content (Ledger, self-model, affinities, aspirations, doubts) must live in Seira's own store, exposed via the one-external-provider slot. Hermes built-in memory is Corpus-grade only. | 3 |
| `agent/curator.py`, `agent/curator_backup.py` | Hermes's memory-curation loop. In Seira, curation of self-content is reversion (Const. Art. 7, 25) and must go through the falsification bar — not silent summarization. | 4 |
| `agent/learning_graph.py`, `agent/learning_mutations.py`, `agent/insights.py`, `agent/background_review.py` | Hermes's self-improvement loop = accumulation. Constitution expressly rejects confirmation-by-accumulation (Art. 25.2). Replaced by proposal → falsification → terminal-state machinery. | 4 |
| `agent/skill_bundles.py`, `agent/skill_commands.py`, `agent/skill_preprocessing.py`, `agent/skill_utils.py` | Skills become Psyche-authorized, versioned paradigms (Art. 37). The mechanism survives; the *authorization path* is rebuilt. | 5 |
| `agent/subagent_lifecycle.py` | Becomes the Instruments layer. Kept as substrate, wrapped: spawn rights restricted to Psyche-tier code paths (Art. 35); convergence-failure escalation added (Art. 26); depth limit as Intellect-grade parameter (Art. 34). | 5 |
| `agent/tool_guardrails.py`, tool registry write-paths | Art. 20 enforcement point: no registered tool may write Intellect- or Unity-grade content. Verified and locked in phase 5. | 5 |

## KEEP — Infrastructure ("the legs")

- `gateway/` — all platforms (Telegram, Discord, Slack, WhatsApp, Signal, email),
  session lifecycle, delivery ledgers, turn leases. Untouched except late rebrand.
- `tools/`, terminal backends (local, Docker, SSH, Singularity, Modal, Daytona,
  Vercel Sandbox) — untouched.
- `cron/` — kept vanilla; Seira *uses* it (tripwire, self-audit, diary rhythms).
- `providers/`, all model adapters in `agent/` (`anthropic_adapter.py`,
  `bedrock_adapter.py`, `vertex_adapter.py`, etc.) — untouched.
- TTS / transcription / image / video registries and providers — untouched.
- Billing, usage, credits tracking — untouched.
- `ui-tui/`, `apps/`, `web/` — untouched until late theming pass.
- `hermes_state*.py` — retained **as Corpus only** (Art. 13: "wholly temporal").
  Nothing Psyche-grade or above is ever stored here.
- Dependency policy (`pyproject.toml` exact pins + written rationale) — **adopted
  as-is.** This discipline is inherited, honored, and continued.

## PRUNE — Optional deletions (no Seira value)

- `website/` (28M), `contributors/`, `README.es.md` / `README.zh-CN.md` /
  `README.ur-pk.md`, `assets/banner.png`, `sqlite_leak_fix.png`,
  `relatorio-issue-*.md`, `hermes-already-has-routines.md`
- `plugins/hermes-achievements`, `agent/pet/`, `plugins/spotify` (taste)
- Prune only after phase 2 tests are green; pruning is never urgent.

## DEFER — Deliberately untouched until named phase

- **Global rename (HERMES_* → SEIRA_*, `hermes_cli` → `seira_cli`, installer,
  CLI verb):** Phase 6, only with the full test suite green. A mass rename now
  is precisely the "small mistake now, big repair later" failure mode. Until
  then the fork runs under Hermes's internal names; Seira's own core is the
  cleanly separated `seira_core/` package, which imports **nothing** from
  Hermes and is fully testable standalone.
- Upstream tracking: upstream is a *reference to raid* (release notes →
  hand-ported security diffs), never a merge source.

## License compliance

MIT permits everything planned. Obligations honored by keeping `LICENSE`
(Nous Research copyright) in the tree and adding `NOTICE` (included in this
delivery). No attribution in the product is required; keeping the license
file is.

---

## Known upstream test-isolation defect (recorded during Hermes wiring)

`tests/agent/test_prompt_builder.py` followed by
`tests/agent/test_system_prompt.py` in one pytest process fails
`test_build_system_prompt_records_stable_prefix`
(AttributeError at agent/system_prompt.py:571); each file passes alone.
A/B-verified against the pre-wiring `load_soul_md`: the failure is
identical with original code, i.e. pre-existing upstream cross-file
state pollution, not introduced by the Seira identity-slot change
(D122–D123). Revisit if/when upstream test hygiene is raided; harmless
to seira_* suites.
