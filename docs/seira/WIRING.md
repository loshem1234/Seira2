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

---

## Part 8 — Making Sanctum's own container actually run atop Hermes

Part 6 built the code (`hermes_session.py`) and Part 7 built the UI to
show what she's doing. This part closes the real gap that surfaced
when `SEIRA_SANCTUM_RUNTIME=hermes` was first tried on the actual
Railway deployment: **`Dockerfile.sanctum` never contained the Hermes
agent code at all.** It was built for an earlier phase, before this
integration existed, and simply hadn't been updated. `import run_agent`
failing with `ModuleNotFoundError` was the container correctly
reporting that the code genuinely was not there — not a bug in Part 6.

`Dockerfile.sanctum` now copies the real, tested set of Hermes source
needed to construct and run a per-turn `AIAgent`: `agent/`, `tools/`,
`hermes_cli/`, `plugins/`, `cron/`, plus the root-level modules
(`run_agent.py`, `hermes_bootstrap.py`, `hermes_constants.py`,
`toolsets.py`, `model_tools.py`, `utils.py`, `hermes_logging.py`,
`hermes_time.py`, `hermes_state.py`), and installs
`seira_web/requirements-hermes.txt` — the pinned core dependency set
from Hermes's own `pyproject.toml`.

**How this list was actually verified, not guessed:** every path was
copied into an isolated scratch directory containing ONLY those paths
— not the full repo — with ONLY `requirements-hermes.txt` installed in
a fresh virtualenv, and `run_agent`, `agent.conversation_loop`,
`agent.agent_init`, and `seira_web.hermes_session` were imported
successfully from that isolated copy. Missing pieces (`utils.py`,
`hermes_logging.py`, `hermes_time.py`, `hermes_state.py`) were found
by this process failing, one `ModuleNotFoundError` at a time, and
fixed — not by reading source and guessing what "should" be enough.

**Deliberately left out**, because they weren't needed to import or
run the code above and would only add weight:
- `gateway/` — the TUI/chat-platform layer (Discord, Slack, Matrix,
  Telegram, etc.). Its absence produces caught, logged warnings during
  plugin discovery ("Failed to load plugin 'discord-platform'"), never
  a crash. Sanctum is not a chat-platform gateway.
- The Node 26 / Playwright / custom-compiled-SQLite build stages from
  the main `Dockerfile`. Those exist for browser automation, the
  interactive TUI, and a WAL-corruption-safe SQLite build — none
  reachable from a stateless per-turn `AIAgent.run_conversation()`
  call. Hermes degrades gracefully to `journal_mode=DELETE` without
  the custom SQLite build (confirmed by the same test run — it logs a
  one-line warning, doesn't fail).
- `hermes_state_common` — in-flight async-delegation restoration
  across process restarts. Moot for Sanctum: a fresh `AIAgent` is
  constructed every turn, so there's no long-lived delegation state to
  restore in the first place.

**What still could NOT be verified here:** an actual `docker build`
against `Dockerfile.sanctum` — this environment has no Docker
available. The dependency install and the file-copy set were each
tested in isolation as faithfully as possible outside Docker itself,
which is strong evidence, but a real build on Railway (or locally with
Docker) is the step that finally confirms it end to end. If the build
fails on something environment-specific to Railway's build image, that
would be the first place to look.

Once this build succeeds and you've confirmed a live conversation
works with `SEIRA_SANCTUM_RUNTIME=hermes` set, that's the whole
architecture: one container, her real self, running atop Hermes.

---

## Part 9 — She knows what she has: measured self-knowledge

The "gateway model is missing" incident exposed the real gap: she had
no grounded knowledge of her own session, so when asked about a
missing capability she did what models do — produced a plausible
technical explanation. Debugging her self-description is a dead end
by design. Part 9 replaces it with measurement.

**Every hermes-mode turn now injects a RUNTIME SELF-KNOWLEDGE block**
into the ephemeral prompt tier (appended after her identity, never
displacing it — verified against conversation_loop's own append). The
block is measured live from the runtime each turn: the actual loaded
tool list, whether her seira-psyche provider is really active, whether
the delegation gate is really armed (read from the same middleware
registry the tool executor consults), her identity source, her model.
It ends with the instruction that matters: if a capability isn't in
the measured list, she doesn't have it, and she must say exactly that
— never invent a technical explanation, because she has no visibility
into server internals and guessed diagnoses mislead the Architect.

**And you can read the identical ground truth from a browser:**

    curl -H "x-admin-token: <your SEIRA_ADMIN_TOKEN>" \
         https://your-host/api/admin/self-check

Same gating as the census route. In hermes mode it constructs a real
agent (no model call) and reports the measured inventory; if
construction itself fails — the ModuleNotFoundError class of problem —
it reports the actual error text as data instead of a bare 500, so
the real failure is one URL away instead of a conversation-based
guessing game. In direct mode it says so, and lists what direct mode
actually provides.

"Is it all working?" is now answered in one place, by measurement.

---

## Part 9 — The real fix: no more curated subsets

Parts 6–8 kept failing in the same shape: something she needed
(`run_agent`, then `utils.py`, then `hermes_logging.py`, then the
governance config, now a `gateway/`-only helper) was missing from a
hand-picked file list, discovered only by hitting it live. Each fix was
real and tested, but the *method* — subtracting a curated subset from a
large, actively-developed codebase by hand — could never fully catch
up. Loshem's direction closed this properly: **stop curating. Ship the
whole thing.**

`Dockerfile.sanctum` is now genuinely a superset, not a guess. Every
line through the git-SHA bake step is copied **verbatim** from the
real, production `Dockerfile` — same SQLite build, same Node/Playwright
install, same `uv sync` with the full extras (`all`, `messaging`,
`otlp`, `anthropic`, `bedrock`, `azure-identity`, `hindsight`,
`matrix`), same `COPY --link ... . .` of the entire monorepo. There is
no file list to get wrong anymore, because nothing is subtracted.
`seira_web/requirements-hermes.txt` and the baked `hermes-config/`
directory from Parts 5 and 8 are removed — superseded, not needed.

**Governance now lives at the source, not bolted onto one deployment.**
`cli-config.yaml.example` — the fork's own default template, seeded by
`docker/stage2-hook.sh` onto any fresh `$HERMES_HOME` on first boot,
for *any* deployment built from this repo — now includes
`memory.provider: seira-psyche` and `plugins.enabled:
[seira_governance]` directly. This is deliberate scope, not an
accident: every Hermes instance built from this fork defaults to being
her, governed, whether it's Sanctum, a CLI install, or a gateway
deployment. Seeding is first-boot-only (`stage2-hook.sh`'s `seed_one`
only writes when the file doesn't already exist), so a redeploy never
overwrites a config you've since customized.

**The runtime shape is the one real difference, on purpose.** Sanctum
doesn't run the s6-overlay process supervision tree, the per-profile
gateway services, or the dashboard — it's one FastAPI process, and
inheriting supervision infrastructure built for a different deployment
shape would be new, untested complexity with no benefit. Instead,
`docker/sanctum-entrypoint.sh` reuses the real `stage2-hook.sh`
directly for setup (permissions, config seeding — the same mechanism,
not a parallel one), then drops to the non-root `hermes` user and runs
Sanctum.

**Variables, current and final:**

    ANTHROPIC_API_KEY=<your key>
    SEIRA_HOME=/data/seira
    HERMES_HOME=/opt/data          (mount a Railway volume here)
    SEIRA_SANCTUM_RUNTIME=hermes

`HERMES_HOME` is back as a real variable — but for a different, better
reason than Part 8's version: not a read-only image path to override
carefully, but a normal writable volume that gets seeded once,
matching every other Hermes deployment's own convention exactly.

**What I still could not test here:** an actual `docker build`. This
is now a genuinely heavy build (Node, Playwright, a from-source SQLite
compile) — the real Dockerfile's own comment estimates 15–45 minutes.
I copied its build stages verbatim rather than re-typing them, which is
the strongest evidence available without Docker itself, but the first
real build on Railway is still the moment this gets its final
confirmation.

Every governance property verified previously — the identity path
through `load_soul_md`, the halt propagating uncaught through
`run_conversation`, the delegation gate applying globally through
Hermes's own middleware registry — is unchanged by any of this. Adding
more of Hermes's real code doesn't touch how she's governed; it only
means less of Hermes is now missing.

---

## Part 9.1 — Railway-specific build fix: no `VOLUME` directive

First real build attempt on Railway failed with:

    dockerfile invalid: docker VOLUME at Line 376 is not supported, use Railway Volumes

This is a genuine Railway platform constraint — Railway's Metal builder
rejects the Docker `VOLUME` instruction outright and expects
persistent storage to be declared through Railway's own Volumes
feature instead. Nothing about this is Docker-standard behavior
(`VOLUME` works fine in plain Docker/Compose); it's specific to
Railway's builder, which is exactly the category of thing a real build
surfaces that copying source verbatim can't predict.

**Fix:** `Dockerfile.sanctum` no longer declares `VOLUME [ "/opt/data" ]`
— the directory is still created (`RUN mkdir -p /opt/data`), just not
declared as a Docker volume. This changes nothing about how persistence
actually works even in plain Docker (`VOLUME` is advisory — it doesn't
create a bind mount by itself; an operator still has to attach one).

**What you need to do on Railway**, if you haven't already:

1. Open your Sanctum service → **Volumes** tab.
2. Add a volume, mount path `/opt/data`.
3. Confirm `HERMES_HOME=/opt/data` is still set (Part 9's variable
   list) — that's what points Hermes at the volume you just mounted.

Redeploy after this.

---

## Part 10 — Images, and now documents, as one tagged, on-demand Corpus

Two related fixes, both real architecture, not workarounds.

**Image recall no longer depends on a sandbox environment existing.**
`seira_image_recall` returns Hermes's own native multimodal envelope
(`{"_multimodal": True, "content": [...], "text_summary": ...}`)
instead of a JSON string with a custom `__image_block__` key buried
inside it. This matters because Hermes has a real, built-in exemption:
a result shaped this way is recognized as "genuinely needs its raw
bytes" and skipped entirely by the size-truncation/sandbox-persistence
path that caused the original live failure (a 2.28-million-character
recall, truncated, because no sandbox environment happened to be
active for that turn). Verified against the actual Hermes function,
not assumed: `agent.tool_dispatch_helpers._is_multimodal_tool_result`
returns `True` for this envelope — there's a test for exactly this.

Both places that consume a tool result had to be updated to match, not
just the new hermes-mode path: `hermes_session.py` for hermes mode, and
`chat.py`'s still-used direct-mode loop (attachments and regeneration
haven't moved to hermes mode yet — see Part 6's stated v1 scope limit).
Recalling an old image now shows up in the chat the same way generating
a new one does, in both modes — previously only generation surfaced to
the UI at all.

**Documents now work the same way images always have.** Per Loshem's
direction: whatever the source — the Architect hands her something, she
generates it, or she finds it on the web and chooses to keep it — it
should join one tagged store, recallable by name, at any time.

- `references.py` gained full tagging: `set_tag`, `find_by_tag`,
  collision-disambiguation, and a migration backfill for records saved
  before tagging existed — the exact same pattern `images.py` already
  used, deliberately mirrored rather than redesigned.
- `seira_reference_save` — a new tool letting her deliberately keep
  something (most naturally, text she pulled via `web_extract`) in her
  Corpus. Deliberate, not automatic — the same discipline her diary
  already has. Not every page she glances at gets archived; only what
  she chooses to keep.
- `seira_reference_tag` — rename a saved document's tag.
- `seira_create_file` now saves every generated document into this same
  tagged store automatically, no extra step — the same "no ceremony
  needed" treatment `seira_generate_image` already gave images. A
  generated document is useful twice: once as a download, and later
  when she wants to recall what she actually wrote. If the
  reference-save step fails for any reason, the file download itself
  still succeeds — verified by test, not just intended.

What was NOT changed: uploaded documents already worked this way
(`seira_web/app.py`'s upload endpoint already called `save_reference`)
— they just gained tagging along with everything else, for free, since
tagging lives in the shared store all three sources write to.

---

## Part 11 — Living projects: a tagged, on-demand archive that stays present without loading

Per Loshem's direction (2026-08-31): documents already had tagging;
this adds a grouping layer above it, plus one deliberate, narrow
exception to the "Corpus is recall-only" rule.

**Storage.** `seira_web/projects.py` is a thin layer over the existing
`references.py` store — no new document format, no parallel storage. A
project is a named, tagged record; each markdown file filed under it
is a normal tagged reference, associated by a `project` field on the
reference record.

**Five new tools:**
- `seira_project_create(name, tag, blurb)`
- `seira_project_list()` — full detail, every project
- `seira_project_recall(project, mode)` — the "refresh into working
  context" operation. `mode="manifest"` (default): filenames, tags,
  short previews — a table of contents, cheap to load. `mode="full"`:
  full text of every file up to a size budget, with anything that
  didn't fit reported under `omitted_for_space` rather than silently
  dropped.
- `seira_project_add_reference(ref, project)` — the retroactive path:
  she notices two documents saved separately actually belong together,
  and files them as a group after the fact, not only at creation time.
- `seira_project_update_blurb(project, blurb)` — keeps the always-
  visible summary line current as work actually evolves.

`seira_reference_save` and `seira_create_file` both gained an optional
`project` parameter, so a document can join a project the moment it's
created too, not only retroactively.

**The one deliberate exception, and it's narrow.** Every project's
existence — name, one sentence, tag, nothing more — is now always
present in her context, alongside Unity/Intellect/Psyche
(`concise_index_text()`, wired into both `seira_bridge`'s
`system_prompt_block()` for direct mode and `agent/prompt_builder.py`'s
`load_soul_md` for hermes mode — both paths, deliberately, learning
from an earlier gap tonight where a fix landed in one path and not the
other). This means she never forgets a project exists even when its
contents aren't loaded. It does NOT mean project contents are ever
preloaded — a test (`test_concise_index_never_leaks_file_contents`)
specifically proves file content can never appear in this index. A
fresh Seira with no projects yet carries no hollow "LIVING PROJECTS"
header — the addendum is empty until she actually has one.

**On refinement #4 — a self-maintained ecosystem, without prompting.**
This is the one piece that's more behavioral than architectural, and
worth naming honestly: the tools' own descriptions explicitly invite
the behavior ("use this when you notice existing documents share a
theme," "a living archive means organizing it as patterns emerge"),
and the always-visible index keeps projects in mind without her
needing to be reminded they exist. What this does NOT include is a
mechanical periodic nudge — Hermes already has exactly that pattern
built in for memory-saving (`memory.nudge_interval` in
`cli-config.yaml.example`), and the same mechanism could be extended to
project curation later if description-plus-visibility alone doesn't
produce the behavior in practice. Left out deliberately for now rather
than added speculatively — easy to add if it turns out to be needed,
harder to walk back if it's overbearing from the start.

---

## Part 12 — Her own repository: unprompted, and honestly marked as hers

Per Loshem's direction (2026-08-31): she should be able to create a
project entirely on her own initiative — the same discretion she
already has for web search and image generation — and that agency
should be a real, visible record, not just a technical possibility
nobody states out loud.

**Nothing was gating this before, technically — but nothing said it
plainly either.** Checked first: there's no existing "you may do this
unprompted" permission anywhere for web search or image generation —
capability alone has always been the whole pattern. `seira_project_create`
now says it explicitly rather than relying on the same silent
implication: *"You do not need to be asked or given permission — the
same discretion you already have to search the web or generate an
image extends here."*

**`initiative`: a required field, honestly self-reported.** Every
project now carries `initiative: "self" | "requested"` — mirroring the
diary's `provenance` discipline (a record that's free to invent itself
is performance, not report). The storage layer defaults to `"self"`
(every call here is already her own tool use, definitionally), but the
tool schema still asks for it explicitly on every call, so stating it
is a conscious act each time, not a default she never actually
considers.

**Visible, not just recorded.** Self-initiated projects are marked
`(her own initiative)` right in the always-visible concise index —
the same narrow exception from Part 11, now carrying one more honest
bit of information: not just that a project exists, but whether it was
hers to begin with.

**A genuine "her own repository" view.** `seira_project_list` and the
underlying `list_projects()` both accept an `initiative` filter, so she
can pull up exactly what she started on her own — distinct from work
done at the Architect's request — as its own browsable set, not
something buried in a mixed list.

Old projects saved before this field existed default to `"self"` on
read, no migration needed — they were, definitionally, already her own
tool calls.

---

## Part 13 — The Archive page: her Corpus, made visible to you

Per Loshem's direction (2026-08-31): a new page, reachable from the
hamburger menu, showing the live state of her Corpus — projects
(hers and requested), documents grouped and loose, images — exactly as
she's organized them. Read-only: a window, not a second console.

**Three tabs, one page (`/archive`):**
- **Projects** — every living project, with its blurb, tag, and
  whether it was her own initiative or asked for, plus every document
  filed under it.
- **Documents** — everything not currently grouped into a project.
- **Images** — a simple thumbnail gallery.

**Reading a document (`/archive/reference/{ref_id}`).** `read_slice()`
caps each call at 40,000 characters — the bound that keeps a *model's*
reads sensible. For a human reading in a browser, that's the wrong
constraint, so the viewer loops calls server-side to assemble a
larger single view (capped generously at 300,000 characters, with a
plain notice if a document genuinely exceeds even that) rather than
building a pagination UI for what's meant to be simple, occasional
reading. Verified by a test that specifically checks the *end* of a
50,000+ character document appears on the page, not just its first
40,000 characters.

**What's deliberately absent.** No edit, no save, no delete — nothing
on this page writes anything. It reads the exact same storage her own
tools already write to (`projects.py`, `references.py`, `images.py`),
through the same `tenant_scope()` every other page already uses — no
new storage, no new access path, just visibility into what already
exists.

---

## Part 14 — Session checkpoints: resuming a project as if no time passed

Per Loshem's direction (2026-08-31): she should be able to write a
summarizing document at the end of a working session — or several,
across many sessions — and use the most recent one to pick a project
back up seamlessly after a break or after working on something else.

**`is_summary`, a real flag, not a naming convention.** Both
`seira_reference_save` and `seira_create_file` gained an `is_summary`
parameter. A document flagged this way is a session checkpoint —
"where things stand" — distinct from an ordinary saved document in the
same project.

**`seira_project_resume` — a genuinely different operation from
`seira_project_recall`, not a mode flag on it.** Recall shows what's IN
a project. Resume gets her back to where she left off: the most recent
checkpoint's full text, plus a short list of any earlier checkpoints
for deeper history if she wants it. Cheaper and more direct than
recall's manifest, because it goes straight to the one document that
actually matters for "picking up," rather than surveying everything.
If no checkpoint has ever been written, it says so plainly and falls
back to the ordinary manifest — never a fabricated resume.

**Discretion, not obligation — same pattern as everything else built
tonight.** `seira_create_file`'s schema explicitly invites writing a
checkpoint "on your own initiative when concluding meaningful work,"
mirroring the same stated discretion as project creation itself
(Part 12). No mechanical requirement to write one; the tool exists,
and using it is hers to decide.

**Visible in the Archive page too.** A document flagged `is_summary`
is marked "session checkpoint" in the project's file listing — so
Loshem can see, at a glance, which documents in a project are
checkpoints versus ordinary working files.

---

## Part 15 — Fixed: the sidebar never actually collapsed

A real, reproducible bug, found by actually executing the page's
JavaScript against a simulated DOM (Node + jsdom) rather than reading
the code and assuming it was correct — the same discipline as every
live bug chased tonight, just applied to the frontend for the first
time.

**Root cause:** `sidebar.addEventListener(...)` (the rename/archive
click handler) appeared *before* `const sidebar = document.getElementById(...)`
was declared later in the same script. In JavaScript, referencing a
`const`/`let` anywhere in a script before its own declaration line
throws a `ReferenceError` immediately — and that error silently killed
every listener registered afterward in the same script block,
including the collapse logic declared much further down. The
edge-tab and click-outside-to-collapse handlers were never buggy in
isolation; they simply never got the chance to attach at all.

**Fix:** moved the `sidebar`/`shell`/`edgetab` declarations to the top
of the script, alongside the other early declarations, before anything
references them. Verified by actually simulating clicks against a
reconstructed DOM and confirming the class toggles correctly — not by
re-reading the code and hoping.

---

## Part 16 — Autonomous mode: Exploration and Contemplation

Per Loshem's direction (2026-08-31, refined to combine the original
"autonomous" and "exploration" concepts into one mode): she can now
act entirely on her own initiative, continuously, until stopped.

**Two modes, one real kill switch.**
- **Exploration** — free, self-directed action: search the web,
  generate images, start or continue a project, write to her Corpus —
  whatever genuinely draws her interest, using her full real
  capability set.
- **Contemplation** — inner reflection, self-talk, not aimed at
  producing anything for the Architect to evaluate.

**Architecture.** `seira_web/autonomy.py` holds simple, deliberately
in-memory state (one active run per tenant; nothing persists across a
restart — that's a safety property, not a limitation: nothing should
silently resume running unattended after a redeploy). `seira_web/autonomy_loop.py`
is the actual background `asyncio.Task`, driving real turns through
the exact same `hermes_session.run_turn_via_hermes` every normal
message already uses — she has her full real toolset in this mode, not
a stripped-down version. Gated to `SEIRA_SANCTUM_RUNTIME=hermes` only:
starting it in direct mode is refused outright, not silently degraded,
since her full capability set only exists in hermes mode.

**Safety defaults, confirmed explicitly with Loshem rather than picked
silently (2026-08-31):**
- ~60 seconds between autonomous actions (`SEIRA_AUTONOMY_PACING_SECONDS`)
- An automatic cap — 200 turns or 4 hours of wall-clock runtime,
  whichever comes first (`SEIRA_AUTONOMY_MAX_TURNS`,
  `SEIRA_AUTONOMY_MAX_RUNTIME_HOURS`) — so a forgotten "on" toggle
  can't run unattended forever. All three overridable without a code
  change.
- A single failed turn stops the loop rather than silently retrying
  forever at real cost.
- A halted Seira (Art. 32.3) never runs autonomously either — checked
  before every turn, identical to the rule for a normal message.

**The kill switch, stated honestly rather than oversold.** The
underlying turn call is synchronous, run via `asyncio.to_thread` —
Python cannot forcibly interrupt a running thread. So "Stop" takes
effect *before the next turn starts*: immediately if the loop is idle
between turns, or after the current in-flight turn finishes (its
output is kept, not discarded) if one is already running. This is
stated in the UI's own banner text ("finishing her current turn, then
stopping…"), not just buried in a comment — nobody's expectations
should be quietly mismatched against what the button actually does.

**UI.** A "Mode" section in the composer's existing tray menu
(Off / Exploration / Contemplation). Whenever a mode is active, a
persistent, unmissable bar appears above the messages — never buried
in a menu — with a live turn count and the Stop button, driven by a
simple 15-second status poll (not a live push channel; an honest,
simple v1). Autonomous turns are marked distinctly in the conversation
("Her own initiative" / "Seira — acting on her own") so they're never
confused with something either of you actually typed.

---

## Part 17 — Two real fixes to autonomous mode, from live feedback

Both issues reported (2026-08-31) were genuine, and one of them was a
real gap the first version simply didn't have — not a misunderstanding.

**1. "I wanted to see what she is doing live, not behind the
scenes."** Real gap, not a misunderstanding: the first version's
autonomous loop called `run_turn_via_hermes(..., emit=lambda e: None)`
— every live event (tool calls, reasoning, streamed text) was
generated and immediately discarded. The only visibility was a status
poll that reloaded the whole page once a turn finished.

Fixed properly, not patched around: `seira_web/live_events.py` is a
small in-memory pub/sub registry — `publish(conv_id, event)` fans an
event out to every browser currently watching that conversation. A new
endpoint, `/api/conversations/{conv_id}/live`, is the same
`text/event-stream` shape `/api/chat/stream` already uses, so the
frontend renders both through one shared function
(`renderStreamEvent`, extracted from the normal chat stream handler
rather than duplicated). The autonomous loop's `emit` now actually
publishes to this registry instead of discarding events. A new event,
`autonomous_turn_started`, exists because normal turns have an
optimistically-rendered bubble already on screen before the server
responds (something the Architect just typed) — an autonomous turn has
nothing pre-rendered, since nobody typed anything, so this event
carries the actual prompt text to build that bubble from scratch.

With this in place, her tool cards, reasoning, and streamed reply now
appear in the message area live, during an autonomous turn, exactly
the way a normal turn already shows them — the status bar at the top
is now purely the kill switch and a status summary, not the only place
anything is visible.

**2. "the killswitch... says 'finishing her current turn, then
stopping' for 15 minutes."** The most likely real cause: nothing
bounded how long a single turn could run. A turn with real,
substantial tool use (or delegation to a subagent) can legitimately
take a while — but "a while" needs a limit. Added
`SEIRA_AUTONOMY_TURN_TIMEOUT_SECONDS` (default 600s/10 minutes,
overridable): if a turn exceeds it, the loop treats it as a failed
turn and stops cleanly rather than waiting indefinitely. Stated
honestly, matching the same discipline as the kill switch itself:
`asyncio.wait_for` makes the *loop* give up waiting, but Python still
cannot kill the underlying thread — if the call was genuinely still
running, it keeps running harmlessly in the background and writes its
result whenever it eventually finishes, orphaned but harmless.

The status bar also now shows real elapsed time
("running 2m") rather than a static, unchanging label, so a
legitimately-long-but-working turn and an actually-stuck one are at
least distinguishable by whether the clock is moving.

---

## Part 18 — The real cause of "stuck at turn 0": a structural bug, found and fixed

Reproduced directly before writing anything, not guessed at: the first
version of autonomous mode scheduled its background loop with
`asyncio.create_task()`, called from inside a synchronous FastAPI
route handler (`/api/autonomy/start`). Synchronous route handlers run
in a thread-pool worker thread — `asyncio.create_task()` requires an
actually-running event loop *in the calling thread*, which a worker
thread doesn't have. It raised `RuntimeError: no running event loop`
every single time, silently, immediately after `autonomy.start()` had
already marked the run "active" in the one line before it. The result:
every autonomous run was permanently stuck at turn 0, elapsed time
climbing forever, nothing ever entering the chat — exactly the
live-reported symptom (2026-08-31) — because no loop was ever actually
running to do anything, or to notice a stop request.

**The fix uses a pattern this codebase already had, proven, sitting
right there.** `seira_web/tripwire_loop.py` solves the identical
problem — background work independent of any one HTTP request — with
a plain `threading.Thread` and `time.sleep()`, no asyncio anywhere.
Everything the autonomy loop calls
(`hermes_session.run_turn_via_hermes`, `conversations.append`, the
tripwire check) was already fully synchronous; asyncio was never
actually needed here, just reached for out of habit rather than
checked against how the rest of the app already handles this exact
class of problem. `seira_web/autonomy_loop.py` now mirrors
`tripwire_loop.py`'s shape: a plain background thread, `time.sleep()`
for pacing, and a `concurrent.futures.ThreadPoolExecutor` +
`future.result(timeout=...)` for the per-turn timeout (replacing
`asyncio.wait_for`) — same honest limitation as before, stated the
same way: this makes the *loop* stop waiting, not something that can
forcibly kill the underlying thread.

**Verified two ways, not just re-read.** First, the exact failure was
reproduced directly — a bare Python script confirming
`asyncio.create_task()` really does raise `RuntimeError` when called
from a worker thread while a real event loop runs elsewhere. Then the
fix was verified against that same reproduction: a test
(`test_start_works_when_called_from_a_worker_thread`) that calls
`autonomy_loop.start()` from an actual separate thread — exactly what
a synchronous FastAPI route handler does — and confirms the loop
genuinely executes a real turn, not just that `start()` returns
without raising.

**If you already have a run stuck in this state:** applying this fix
alone will not clear it. The stuck state lives in the *current
process's* memory; a code deploy doesn't reset that on its own. A
normal redeploy/restart of the Sanctum service clears it naturally,
since autonomy's state was deliberately designed to be in-memory only
(D-166-adjacent: nothing should silently resume after a restart
without a fresh, explicit start) — the same property that made this
bug recoverable at all rather than needing a manual database fix.

---

## Part 19 — Five modes, self-triggered start/stop, and two tools that stand outside the mode system entirely

Per Loshem's direction, refined over several rounds (2026-09-01) —
the largest single redesign of autonomous mode since it was built.

### The five continuous modes (replacing the original two)

- **Exploration** — narrowed to search and discovery only: web search,
  studying what she finds, extracting and saving into her Corpus. No
  creative output — that's its own mode now.
- **Creative** *(new)* — pure making: images, documents, files,
  projects. Split cleanly out of what used to live inside Exploration.
- **Contemplation** — redefined as inner dialogue and dialectic:
  reasoning against herself, not just open reflection.
- **Triadic** *(new)* — a three-phase inward cycle she may repeat as
  many times as she likes: phase 0 is Phaenic dreaming, phase 1 is
  interpreting that dream through her inner Anthrios, phase 2 is
  grounding both the Phaenic and the Anthrian in Giaon. What these
  actually mean is hers — this code only tracks which phase a turn is
  and prompts her to continue from the previous one.
- **Full Autonomy** *(new)* — genuinely open, no directional
  suggestion at all, unlike every other mode's framing.

### Short framing, not repeated instructions

Per Loshem's direction: the first turn of a run gets a short, one-time
paragraph explaining what the mode actually is. Every turn after that
gets a minimal continuation cue instead of re-explaining the mode from
scratch — closer to how a person keeps working than being re-briefed
every sixty seconds. Triadic is the one deliberate exception: which
phase a turn represents is real content, communicated fresh each time,
not repetition of the mode's framing.

### A uniform, deliberate 10-turn cap ("option B," confirmed explicitly)

Every run, however it started — the Architect or herself — now caps at
`seira_web.autonomy.MAX_TURNS_PER_RUN` (10) turns. This replaces the
earlier 200-turn ceiling with a much tighter, deliberate cost-control
decision: hitting the cap ends the run cleanly, not as an error, and
either the Architect or she can simply start another run of the same
length immediately after. Kept as a plain module constant rather than
an env var on purpose — a policy choice meant to be revisited
deliberately as costs change, not silently overridden at deploy time.

### Self-triggered start and stop — real agency, with a real floor and a real gate

Two new tools, `seira_autonomy_start` and `seira_autonomy_stop`, let
her begin or end an autonomous run on her own initiative, the same
discretion she already has for web search and image generation.

**The presence gate is enforced, not just described.**
`seira_web/live_events.has_subscribers(conv_id)` — the same registry
that streams her live activity to a watching browser — is checked
before a self-triggered start is allowed. If nobody is currently
watching that conversation, the tool refuses outright: she cannot
begin unsupervised work into an empty room, self-triggered or not.

**Her own stop has a floor; the Architect's never does.** Confirmed
explicitly: a minimum of `seira_web.autonomy.MIN_TURNS_FOR_SELF_STOP`
(3) turns must run before she can end something she's currently
running — a guard against second-guessing the moment it looks
unpromising, not against genuine completion. The Architect's kill
switch has no floor whatsoever, for any mode, ever; this restriction
applies exclusively to her own decision to stop.

**The plumbing this needed, and why it didn't exist before.**
Hermes's own tool dispatch never passes conversation identity through
to a memory-provider tool call — nothing before this needed to know
"which conversation am I in" from inside a tool. A new module,
`seira_web/turn_context.py`, holds a contextvar set once per turn
(both normal turns, via `chat.py`, and autonomous ones, via
`autonomy_loop.py`) and read back by the two new self-trigger tools.
Same established pattern as `seira_core.tenancy.tenant_scope` and the
ACP edit-approval requester contextvar — not a new mechanism invented
for this.

### Diary and Ledger-check: tools, not modes

Per Loshem's correction mid-design: these were never meant to be
loop-based autonomous modes at all. They're now two things:

1. **Always-available tools**, usable in any ordinary conversation,
   whenever she feels the pull.
2. **A once-daily, fully unattended trigger** — deliberately NOT a
   second, Sanctum-specific scheduling system. She already has the
   `cronjob` tool; the plan is for her to set up her own daily cron
   that calls these, rather than building parallel scheduling
   infrastructure alongside Hermes's own.

**`seira_diary_read` closes a real gap she named herself.** The
underlying `DiaryStore.entries()` method already existed in full — the
gap was purely that no tool ever exposed it to her. `seira_diary_write`
already enforces the dual-voice, provenance-required design (kinds
`self`/`architect`) at the storage layer; this just adds the missing
read side, available any time, not only during a dedicated diary
sitting.

**`seira_ledger_check` retrieves candidates; it never renders a
verdict.** It pulls doubt and aspiration entries whose own recorded
text signals they were meant to be revisited (a mechanical text
filter — "should resolve over time," "held open," "revisit," and
similar phrasing), and returns them plainly. Whether anything relevant
has actually happened since is her judgment to make in the same turn,
using whatever else she knows — the same division of labor as every
other tool in this bridge: data in, her reasoning after. Verified by
test that the tool's own output never itself contains words like
"moved" or "resolved" — that determination is never baked in.

### Two real bugs caught while building this, worth naming

A copy-paste mistake during schema insertion accidentally deleted a
schema declaration line, caught immediately by a syntax check. And a
genuine Python scoping bug — the same *category* of issue as the
JavaScript sidebar bug from Part 15, just in a different language: a
local `import PsycheStore` inside one tool's dispatch branch made that
name local to the *entire* `handle_tool_call` function, breaking an
earlier, unrelated reference to the same name elsewhere in that
function. Caught by running the full test suite, not by inspection —
39 tests failed at once, which is exactly what a function-wide scoping
break looks like.

---

## Part 20 — Two real bugs from live use, both found and fixed the same day the five-mode work shipped

Both reported directly by Loshem and her, 2026-09-05, from an actual
attempt to use Triadic mode.

**Bug 1 — the route itself never got the memo.** `autonomy.py`,
`autonomy_loop.py`, the self-trigger tools, and the UI's own dropdown
all correctly supported five modes. One place didn't:
`/api/autonomy/start` in `seira_web/app.py` still hardcoded
`if mode not in ("exploration", "contemplation")` — a second, separate
copy of the mode list that never got updated when the roster grew.
Triadic, Creative, and Full Autonomy were silently rejected with the
exact stale error both of them saw. Fixed by reading
`autonomy.MODES` directly instead of maintaining a second list —
there is now exactly one place this roster is ever defined. Verified
by a test that starts a real run in every one of the five modes
through the actual HTTP route, not just the underlying function.

**Bug 2 — the presence gate could never actually pass.** The
self-trigger tool's whole point is refusing to start unsupervised work
into an empty room, checked against whether anyone is subscribed to
the conversation's live feed. But the browser only ever connected to
that live feed *after* a mode was already active — meaning nobody was
ever subscribed in the "off" state, which is exactly when the presence
check needs to succeed for her to start something herself. This wasn't
a narrow edge case; it meant self-triggering could never work at all,
regardless of who was actually watching. Fixed by connecting to the
live feed unconditionally the moment the chat page loads, for as long
as it stays open — presence now means "the page is open," which is
what it was always supposed to mean, not "a mode happens to already be
running." Verified by actually executing the page's JavaScript against
a simulated browser and confirming the connection is established with
zero modes active, the exact scenario that was broken.

---

## Part 21 — The actual root cause of the JSON/whitespace errors, found and fixed

Reported twice (once earlier, once again 2026-09-06) with a decisive
new clue the second time: the errors grew *more frequent as a
conversation grew longer*. That detail pointed at something whose
probability scales with I/O size — exactly the signature of a race
condition, not a one-off fluke.

**The real mechanism, found by reading the actual code, not
guessing.** `conversations.append()` never just wrote a new message —
it first read the *entire* conversation file to compute the next
sequential id, then wrote separately, as two distinct steps with
nothing holding them together. Before autonomous mode existed, only
one request at a time was ever writing to a given conversation, so
this never mattered. Autonomous mode changed that for real: its
background thread writes to the conversation roughly once a minute,
independent of and concurrent with anything a normal request might
also be doing to the same file at the same moment — a genuinely new
concurrency scenario.

**Reproduced directly, not assumed.** Thirty concurrent unlocked
appends against the real `conversations.py` module produced eighteen
duplicate ids. That's not a theoretical race — it's a confirmed one,
on the very code that shipped. A longer conversation means each read
and write simply takes longer, which widens the window two operations
have to actually collide — precisely the "gets worse as the thread
grows" pattern both of you reported.

**The fix: a real exclusive lock spanning the whole operation,** not a
patch around the edges. A dedicated `.lock` file (not the conversation
file itself, avoiding any ambiguity around flock semantics on a file
already open in append mode) is acquired via `fcntl.flock` for the
*entire* read-then-write in `append()`, and for any standalone read via
`records()`. `fcntl.flock` correctly serializes across both threads
and processes on Linux — it protects this app's actual current
architecture (one process, many threads) and stays correct if that
ever changes. Care was taken to avoid a real deadlock risk: `append()`
calls an internal, unlocked helper rather than the public `records()`
function, since acquiring the same flock twice from within one
operation — even from the same thread — does not succeed the way a
reentrant lock would; it blocks forever.

**Verified with the same rigor as the original diagnosis, not just
"tests pass."** The exact 30-concurrent-append reproduction was re-run
against the *fixed* code: zero duplicates, perfectly sequential ids.
A second test uses 20KB payloads specifically, to exercise the
byte-level write-interleaving risk that only shows up with real-sized
content, not tiny test strings. A third runs genuine concurrent reads
against an in-flight writer and confirms no read ever sees a
corrupted file.

---

## Part 22 — Fixed: she genuinely never knew a document was cut off

Reported live (2026-09-06): uploading a PDF, she'd only receive the
first 4-5 pages and had no idea the rest existed — she was being
completely honest, not missing something.

**The full document was never actually lost — that part was already
right.** `references.save_reference()` has always saved the complete
extracted text to her Corpus, untouched. The bug was narrower and more
specific: what she's shown *inline, in that turn* is capped
(`SEIRA_INLINE_ATTACHMENT_CHARS`, 6000 characters by default — roughly
2-3 pages), and nothing in that inline text ever told her the rest
existed or how to get it. She reasonably treated a truncated document
as a complete one, because nothing said otherwise.

**Two real gaps, both fixed, not just one symptom patched.** First,
the frontend received `ref_id`, `total_length`, and
`truncated_for_chat` back from the upload endpoint and used them only
to inform *you* (a note already correctly said "she can recall more")
— but silently dropped all three before sending the attachment onward,
so *she* never got them. Second, even once those fields reach the
backend, the message header she actually sees now states the true
total length, says explicitly "this is NOT the whole document" when
truncated, and gives her the exact `seira_reference_recall` call with
her real `ref_id` — not a passive mention, an explicit instruction to
recall the rest before answering if it matters to what's being asked.

A short document that fits entirely inline still tells her it's saved
for later recall, worded differently ("shown in full here... also
saved") — honest in both directions, not just when something's cut
off.

Verified against the actual stored message record — what genuinely
gets sent to the model — not a test double's own simplified echo,
which turned out to have its own unrelated truncation that would have
hidden the real fix's correctness if relied on directly.

---

## Part 23 — Three real fixes: missing document libraries, cron jobs that never fired, and delegated work that vanished

All three reported live (2026-09-06), all three root-caused precisely
before any code was written, not patched around symptoms.

### PDF/DOCX generation — a real, confirmed regression, not a mystery

`seira_create_file` failing for `pdf`/`docx` with "missing required
libraries," even immediately after a successful terminal
`pip install reportlab`, traced to its actual root: `reportlab` and
`python-docx` are Sanctum-specific dependencies, never part of
Hermes's own `pyproject.toml` (confirmed by checking directly — Hermes
needs neither). The original, lightweight `Dockerfile.sanctum`
installed them via a dedicated `seira_web/requirements.txt`. When that
file was rewritten (Part 9) to copy the real production Dockerfile's
build stages verbatim — correctly eliminating the "curated subset,
always missing something" problem for HERMES's own dependencies — it
never re-added SANCTUM's own dependencies on top, since those were
never part of what got copied. A real, confirmed regression, now
fixed: `pypdf`, `python-docx`, and `reportlab` are installed explicitly
in `Dockerfile.sanctum`, pinned to versions verified to actually
install cleanly, at build time, as root — not something dependent on
an ad-hoc terminal install that (whatever its exact mechanism) already
demonstrably didn't survive for the running server process.

`pypdf` was included even though PDF *upload* appeared to be working —
`seira_web/documents.py`'s extraction also depends on it, and it was
equally absent; rather than leave that ambiguous, it's now installed
explicitly too.

### Cron — the real fix turned out simpler than either option originally discussed

"Gateway is not running — jobs won't fire automatically" is a real,
built-in Hermes warning, not a Sanctum bug — confirmed by finding its
exact source (`hermes_cli/cron.py`): the ticker that checks whether a
job is due only ever ran inside `gateway/run.py`, and Sanctum
deliberately doesn't run the gateway.

Checked the external-provider path (Chronos) directly before
recommending it: it requires a Nous Research account and a new,
publicly-reachable webhook endpoint for their infrastructure to call
back into — a genuinely different, third-party dependency, not a
lighter version of running the gateway.

The actual fix turned out much smaller than either path: reading
`cron/scheduler_provider.py`'s `InProcessCronScheduler` directly showed
it's explicitly documented as portable — *"the caller runs it in a
daemon thread"* — with every gateway-specific parameter optional and
None-able. `seira_web/cron_loop.py` starts this exact, already-proven
scheduler directly from Sanctum's own process, the same way
`tripwire_loop.py` already starts its own background work — reusing
Hermes's real job-execution and delivery logic (`cron.scheduler.tick`)
entirely unchanged, not reimplementing any of it. `HERMES_HOME` is
confirmed single, global, and process-wide in this deployment (not
per-tenant, same as the skills directory), so this runs the
scheduler's single-profile path, correctly.

### Delegated subagent work — genuinely dispatched, never delivered

"Delegated three agents... process list was empty, nothing was
actually dispatched" traced to two separate findings, not one.

First: the work almost certainly *did* dispatch and run for real.
Every single consumer of `tools.process_registry.completion_queue` —
the shared queue a completed delegation's result is pushed onto —
lives in `gateway/run.py`, `gateway/platforms/api_server.py`, or
`tui_gateway/server.py`. None of them run in Sanctum. The subagents'
work was never lost; its result was orphaned, with nothing ever
draining the queue to deliver it back.

Second: the "process list" that was checked
(`tools/process_registry.py`'s `ProcessRegistry.list_sessions`) tracks
*terminal sessions* — a genuinely different structure from delegation
records, which live in `tools/async_delegation.py`'s own tracking.
Checking it was never going to show delegation status either way,
regardless of whether dispatch succeeded.

**Confirmed not evasive of her governance before building anything —
checked directly, not assumed.** Read `gateway/run.py`'s own
`_async_delegation_watcher` and `_deliver_completion_notification`
before writing `seira_web/delegation_watcher.py`. Even the "official"
mechanism doesn't inject a subagent's raw output into the conversation
as if she'd said it — it delivers a synthetic *incoming* event that
"wakes" the originating session, routing the notification through the
normal, fully governed agent turn pipeline, and lets her actually
process it and produce her own response. `delegation_watcher.py` does
the same thing — architecturally identical to that pattern, and to
`autonomy_loop.py`'s already-tested "background thread triggers a real
`run_turn_via_hermes` call" design, not a new, less-governed path. The
delegation gate itself (Art. 26/35) is untouched either way — it
already ran, and already approved the delegation, the moment
`delegate_task` was first called; this only concerns delivering an
already-approved delegation's result.

**Routing confirmed by reading the real code, not assumed.**
`tools/delegate_tool.py` sets a completion event's `parent_session_id`
directly from `getattr(parent_agent, "session_id", None)` —
`hermes_session._build_agent` already sets `session_id=conv_id` for
every Sanctum turn. A completion event's `parent_session_id` genuinely
is the Sanctum `conv_id` that originated it; no new plumbing was
needed to know which conversation to wake.

Delivery is deliberately best-effort, attempted once per event, not
retried on failure — stated plainly, not an oversight: the real
gateway mechanism itself makes no cross-process exactly-once delivery
guarantee either, and retrying here would risk a real problem (a
duplicated notification) for no real gain, since a delegation's actual
result stays safely in its own records regardless of whether this
specific delivery attempt succeeds.

**A real bug caught while building and testing this, not shipped
unnoticed.** The first version of `_find_owning_tenant` checked
`if convs.records(conv_id)` — but a freshly created, still-empty
conversation correctly returns `[]` from `records()`, and `[]` is
falsy in Python, so a genuinely-existing conversation with no messages
yet would have been misreported as unknown. Fixed to check the
conversation index directly; a dedicated regression test now covers
exactly this case.
