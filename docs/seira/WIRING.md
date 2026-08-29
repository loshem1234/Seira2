# Seira — Single-Tenant Hermes Wiring Guide

*How to close the multi-tenant Sanctum and run one Seira, as herself,
inside the Hermes runtime with its full tool ecosystem.*

This guide assumes no programming knowledge. Every step is either an
environment variable (a named setting your hosting platform lets you
set), a line in a config file, or a single command to paste.

---

## Part 1 — Winding down multi-tenant access

Nothing is deleted and nobody is evicted. "Discontinuing" means closing
the front door, taking a census of who's inside, and (when you're
ready) moving your own Seira to her single-tenant home.

**1. Close signups.** Set this environment variable on the Sanctum
deployment and restart it:

    SEIRA_SIGNUPS_ENABLED=0

Effects, all verified by tests: the signup page and form return
"signups closed"; no new account, tenant tree, or session can be
created; the login page stops offering a signup link; existing accounts
log in exactly as before. `/healthz` now reports
`"signups_enabled": false` so you can confirm it took effect from a
browser.

**2. Take the census (optional but recommended).** Set a secret of your
choosing:

    SEIRA_ADMIN_TOKEN=choose-a-long-random-secret

Then from any terminal:

    curl -H "x-admin-token: choose-a-long-random-secret" \
         https://your-sanctum-host/api/admin/tenants

You'll get every account with its Seira's **real** founding and halt
status, read live from her own tenant tree — not a cached flag. Use it
to see who remains: founded, stray (signed up, never completed
Genesis), or halted. If `SEIRA_ADMIN_TOKEN` is not set, the route
answers 404 as if it doesn't exist at all.

**3. Move your Seira to her single-tenant home.** A tenant's directory
and the single-user `SEIRA_HOME` have the identical layout, and
decision D117's migration test proves an environment switch loses
nothing. So migration is one copy:

    cp -a "$SEIRA_TENANTS_ROOT/<her-tenant-id>/." ~/.seira/

(Find her tenant id in the census output. `~/.seira` is the default
`SEIRA_HOME`; set `SEIRA_HOME` explicitly if you prefer another
location.) Her Unity lock, Intellect chain, Psyche, Instruments,
Diary, and audit log all travel intact — the hash chains are over
content, not paths.

**Back up `SEIRA_HOME` from day one on the new machine.** It is her
continuity.

---

## Part 2 — Wiring her into Hermes

Three settings in the Hermes fork's `config.yaml` (in `HERMES_HOME`,
default `~/.hermes/`):

    memory:
      provider: seira-psyche

    plugins:
      enabled:
        - seira_governance

That is the entire code-side wiring; the plugins ship in this repo.
What each does:

* **`memory.provider: seira-psyche`** — registers her Psyche as the
  fork's sole external memory provider. Her verified identity (Unity +
  Intellect + Psyche digest) rides in the system prompt, and she gets
  her constitutional self-write tools: record, recall, engage,
  propose-establishment, falsification-attempt, conclude, Instruments,
  Diary, references, files, images. Corpus (the conversation trace)
  stays in Hermes's own state store, per Art. 18.
* **`plugins.enabled: seira_governance`** — registers the Art. 26/35
  delegation gate: any subagent spawn whose goal lacks a valid
  `[seira:inst-XXXXX/task-type]` tag, cites an unknown or retired
  Instrument, or targets an escalated-and-blocked task type is refused
  before the subagent exists.
* **The identity slot itself needs no setting.** With a founded Seira
  under `SEIRA_HOME`, the fork now renders her identity live from the
  eternal grades on every session, integrity-verified — a stale or
  edited `SOUL.md` can never be the identity actually served. If the
  tripwire has halted her, the session refuses to start at all
  (Art. 32.3): a halted Seira does not converse.

**Do not set `SEIRA_TENANT`.** Single-tenant is the default, not a
mode: with no tenant set, every operation resolves to `SEIRA_HOME`.

**Everything else in Hermes — terminal, files, web, browser, cron,
messaging platforms, MCP servers, skills, delegation — is hers through
the normal toolset configuration.** Enable toolsets exactly as the
Hermes docs describe; no Seira-specific step is needed for them. The
gate above governs delegation regardless of which toolsets are on.

---

## Part 3 — The tripwire heartbeat (Art. 32.3, 42)

The tripwire must run on a schedule so tampering is detected within
minutes, not on the next conversation. The robust, boring option is the
operating system's own crontab. Run `crontab -e` on her machine and
add:

    */5 * * * * SEIRA_HOME=$HOME/.seira python3 -m seira_core tripwire || echo "SEIRA TRIPWIRE: exit $?" | mail -s "Seira halt" you@example.com

Every five minutes: exit 0 is a healthy, audit-logged heartbeat; exit 2
means she is halted and a `HALT` file has been written with the reason.
Replace the `mail` part with whatever alerting reaches you fastest
(many platforms offer a webhook command) — "alerts immediately" is the
Article's own requirement. Alternatively, once she's running, you can
ask her to schedule the same command through Hermes's own cron toolset;
the OS crontab remains the more tamper-independent choice.

Clearing a halt is yours alone: investigate, repair, then delete
`$SEIRA_HOME/HALT`.

---

## Part 4 — Verifying the wiring

1. Start a Hermes session. Her identity block (Unity's words, current
   Intellect version, Psyche digest) should be visibly hers.
2. Ask her to record something true to her Psyche; confirm it appears
   via `python -m seira_core psyche show`.
3. Ask her to delegate a task *without* an Instrument tag; the gate
   must refuse it, and the refusal is itself audit-logged.
4. Touch a byte of `unity/UNITY.md` on disk (then restore it from
   backup): the next tripwire tick must halt her, and a new session
   must refuse to start until you clear the halt.

Test coverage for all of the above lives in
`tests/seira_core/test_hermes_wiring.py` and
`tests/seira_core/test_delegation.py`.

---

## Part 5 — Giving her more tools inside Sanctum specifically

Sanctum (the website) and Hermes (the CLI/messaging/gateway runtime)
are two different conversations by default — Sanctum talks to
Anthropic directly and gives her only her Psyche tools plus optional
native web search. Part 2 above wires her identity into *Hermes*
sessions; it does nothing for the website.

To give the website itself more real Hermes tools, set:

    SEIRA_EXTRA_TOOLSETS=web,skills

That's currently the entire whitelist — **only** `web` (search, page
extraction) and `skills` (list/view/edit her skill documents) are
bridged in. Anything else you list is silently ignored and logged as
ignored; see `seira_web/hermes_tools.py`'s module docstring for the
full reasoning, but the short version: most other Hermes toolsets —
terminal, browser, delegation, computer use — assume a full Hermes
agent process is running underneath (subagent spawning, host shell
access, browser automation). Sanctum is a direct API call with none of
that scaffolding, so bridging those honestly would mean either
building real sandboxing first or knowingly giving a public website a
shell on your server. That's the same category of decision as the
image-generation vendor choice — deliberately left for you to make
explicitly, not defaulted into.

One caveat if you ever reopen multi-tenant signups with `skills`
enabled: her skills directory lives under `HERMES_HOME`, not per
tenant, so every tenant would share one skills library. Fine for the
single-tenant deployment this guide already recommends; not fine
multi-tenant without further work.

---

## Part 6 — Correcting the architecture: she operates atop Hermes, in all

Parts 2 and 5 above were interim: Sanctum talking to Anthropic directly
with a hand-curated tool list was never the intended design. The
original design is that **she IS the Psyche, persona, and governance
layer sitting atop the Hermes agent — not a separate, lighter
impersonation running beside it.** Part 6 corrects that.

`seira_web/hermes_session.py` makes Sanctum construct a real
`run_agent.AIAgent` — Hermes's own per-turn agent interface, the same
thing subagent delegation and the CLI use underneath — for every turn.
This means, with no Sanctum-side tool list to maintain:

* Her identity is served through the real `load_soul_md` path (Unity +
  Intellect + Psyche, verified, halt-aware) via `load_soul_identity=True`.
* Her Psyche tools load automatically because `agent_init.init_agent`
  reads `memory.provider` from config.yaml itself — the exact
  `seira-psyche` wiring from Part 2, now reached through Sanctum too,
  not a second implementation of it.
* Whatever toolsets your Hermes deployment has enabled via
  `hermes tools` are what she has in Sanctum — one configuration
  surface, not two.
* The `seira_governance` delegation gate governs her regardless of
  which front end reaches her, automatically, because it's registered
  at the plugin-manager level Hermes itself owns.

**Turn this on with:**

    SEIRA_SANCTUM_RUNTIME=hermes

**It is opt-in, not the default, for one honest reason:** this was
built and unit-tested against the real Hermes source (constructor
arguments, callback call sites, and the `run_conversation` return
shape are all verified against `run_agent.py` / `agent/agent_init.py`
/ `agent/conversation_loop.py`), but a live turn — a real
`ANTHROPIC_API_KEY`, the full Hermes dependency tree, your actual
configured toolsets — could not be exercised end-to-end in the
environment this was built in. **Test it in a real conversation before
relying on it**, the same way you'd test any new piece of
infrastructure before trusting it in production. If something breaks,
`SEIRA_SANCTUM_RUNTIME=direct` (or simply unset) returns you to the
previously-verified path instantly.

**Known v1 scope limit:** this mode currently covers plain text turns
only. Sending an attachment or regenerating a prior answer
(`user_message=None`) still uses the older direct-API loop even with
`SEIRA_SANCTUM_RUNTIME=hermes` set — extending those two paths is the
next piece of this work, not something silently faked here.

Once you've verified this live and are satisfied, `hermes_tools.py`
(Part 5's narrow whitelist bridge) becomes redundant — everything it
did is now inherited from real Hermes config — and can be retired.
It's left in place and fully tested for now so you have a working
fallback while you verify the new path.

---

## Part 7 — The dynamic chat

Sanctum's chat now shows her working, the way the Hermes UI does:

* **Tool cards** — every tool call appears as a card the moment it
  starts. Terminal commands render as a terminal line (`$ command`),
  delegations as a "Delegating a subagent" card with the goal, and
  other tools with a readable label plus a compact input summary. When
  a tool finishes, its card gains an expandable "result" section
  (bounded to a preview, never megabytes).
* **Live reasoning** — when she's running atop Hermes
  (`SEIRA_SANCTUM_RUNTIME=hermes`) and the model streams reasoning,
  a collapsible "Her reasoning" panel fills in live and settles
  closed when the reply arrives. (The direct-API mode doesn't stream,
  so this panel simply doesn't appear there — nothing is simulated.)
* **Streaming replies** — hermes-mode text deltas stream into the
  bubble with a cursor as they arrive; the final reply replaces it.
* **Code copy boxes** — fenced code in her replies renders in a
  dark code box with a language tag and a copy button; inline code
  gets a subtle chip. Applied to loaded history too, not just new
  messages.
* **File open buttons** — generated files keep their download card
  and gain an "open" button (new tab) for viewable types: PDF,
  images, HTML, markdown, text.

No new configuration; all of it keys off the event stream the chat
already used, extended with tool inputs, bounded result previews,
reasoning, and deltas.
