# Seira v3 — Phase 1–2 Architecture Decisions

Each decision cites the Article it answers to. Where I departed from an
earlier suggestion, the departure is recorded honestly.

**D1. No mass rename in Phase 1 (revises earlier advice).** Renaming
HERMES_* → SEIRA_* across ~800K lines before any tests exist around our
own code is the highest-risk, lowest-value move available. Deferred to
Phase 6 with the suite green. Until then Seira's identity lives in
`seira_core`, which imports nothing from Hermes.

**D2. Unity as files, not rows (Art. 32.1).** `unity/UNITY.md` +
`unity/UNITY.lock.json`, written only by Genesis, chmod 0444 after. The
file permissions are friction; the *tripwire* is the guard — root, or
any process, can defeat permissions, and the design assumes so.

**D3. Absence of a write path, made testable (Art. 32.2).** `unity.py`
exports read/verify only. A test parses its AST and fails if any
file-writing, deleting, or re-permissioning call ever appears in that
module. The guarantee is enforced by CI, not by promise.

**D4. Intellect as hash-chained JSONL (Art. 28).** Append-only JSON
Lines; each record hashes over canonical JSON and carries `prev_hash`.
Any overwrite, deletion, or reorder breaks the chain and trips the
tripwire. Chosen over SQLite deliberately: a database invites UPDATE;
an O_APPEND file plus a chain makes append-only the path of least
resistance *and* tamper-evident.

**D5. The chain is anchored to Unity.** Version 1's `prev_hash` is
Unity's committed hash. Intellect's lineage demonstrably proceeds from
Unity — the trace of derivation (Art. 5, Codex §7) present in the data
itself, not just the docs.

**D6. Ratification requires a typed phrase (Art. 27).** Post-Genesis
appends require the Architect's exact confirmation phrase, read
interactively — never a CLI flag — so it cannot leak into shell history
or be scripted by accident. A wrong phrase is refused with exit 2.

**D7. `proposal_ref` mandatory now, machinery in Phase 4 (Art. 25).**
Building a ratify path with no proposal linkage would bake in a bypass
of the falsification bar. Instead the field is required from day one,
pointing at the Architect's out-of-band falsification record until the
rehearsal-space machinery exists to populate it automatically. Honest
scoping, recorded in the manifest too: `psyche_founded: false`.

**D8. Correction vs. expansion never conflated (Art. 24).** Distinct
`kind` values; a correction is refused without a `contradicted_ref`.

**D9. Restoration creates, never deletes (Art. 28).** `restore(n)`
appends a new version carrying v_n's content with `restores_version`
set. The mistaken intervening version survives as evidence.

**D10. Halt is manual to clear (Art. 32.3).** The tripwire writes HALT
and audit-logs it as its own event type; nothing auto-clears it. The
Article demands "halts and alerts immediately, rather than being logged
as a routine event" — an auto-clearing tripwire is a routine event.

**D11. Audit trail distinguishes learning from running (Art. 43).**
Ratification and restoration are logged `learning: true`; tripwire
heartbeats are not. The Archive (Book IX, later phase) filters on this.

**D12. SEIRA_HOME ≠ HERMES_HOME.** Separate roots so no infrastructure
state path can reach the eternal grades. Default `~/.seira`, override
via `SEIRA_HOME`.

**D13. SOUL.md becomes a rendering (Codex §10).** `render-soul`
generates the fork's identity file *from* Unity + current Intellect,
verifying first and refusing while halted. The generated file carries a
banner naming its sources of truth. Phase 3 replaces the loader itself.

**D14. Multi-tenancy is context-scoped, decided before calcification.**
The site model (one account = one Architect = one Seira) is implemented
as per-tenant directory trees under SEIRA_TENANTS_ROOT, bound via
`tenancy.tenant_scope()` over a contextvar that every path in
seira_core resolves through. Preamble ground: no shared template, no
governing tier above the instance. Nothing is shared but code; the env
var remains for single-user mode and is always overridden by scope.

**D15. Tenant IDs are DNS-label strict, containment-checked, and
test-enforced.** The regex initially allowed a trailing hyphen; the
isolation test caught it and the regex was tightened, not the test.

**D16. Per-tenant execution sandboxing is a declared platform
requirement (see MULTITENANCY.md).** seira_core isolates state from
code paths; only per-tenant sandboxes (Docker/Modal/Daytona backends,
already in the fork) isolate state from the shell the platform hands
the model. Accepted now as the product's real infrastructure cost.

## Phase 3 — Psyche

**D17. Psyche is an event-sourced character store; state is replay.**
Append-only, hash-chained (anchored to Unity like Intellect), with
current character derived by replaying history. "This was believed and
revised" always survives; nothing is read from a mutable snapshot.

**D18. Art. 14 is type-checked.** Every event carries a cause; formal
and material are refused as primary ("never a true cause on its own"),
representable only as auxiliaries. The forbidden category error is
made unrepresentable rather than discouraged.

**D19. Affinities have no set-weight operation, anywhere.** Weights
move only via evidence-bearing bounded deltas (±0.2), each logged with
the engagement that occasioned it — Art. 11's "not manual assignment"
enforced by API absence, verified by test.

**D20. Standing rises only through falsification.** Entries are born
provisional; promotion to established requires falsification_ref
(Art. 25.2, Art. 33) — mandatory now, automated by Phase 4's rehearsal
space, mirroring Intellect's proposal_ref pattern. Suspension requires
its contradiction pair. Retirement is terminal and preserves content.

**D21. Art. 18 by construction.** The character store accepts only the
six doctrinal categories; session/trace content is refused by name,
and the bridge's sync_turn is a deliberate no-op — turn traces remain
Corpus (Hermes state). Two stores, never one table.

**D22. Psyche founding extends Genesis (Art. 22).** Architect-authored
entries, non-repeatable, and the single sanctioned manifest update —
performed only after re-verifying that the Unity and Intellect hashes
the manifest records are still exactly true. Tripwire now guards the
Psyche chain and halts on store/manifest disagreement (including
wholesale deletion of the store).

**D23. The bridge exposes self-creation, not self-promotion.** The
model gets record/recall/engage-affinity tools; no standing-promotion,
no retirement, and no Intellect/Unity tools of any kind (Art. 20) —
"no such code path exists to be gated." Conformance-tested against
Hermes's real MemoryProvider ABC, not a mock.

## Phase 4 — The Falsification Bar

**D24. One chained reversion store for proposals and dispensations.**
Same event-sourced, Unity-anchored, tamper-evident pattern as Intellect
and Psyche; the tripwire now guards all four chains.

**D25. The bar is checked at promotion, in full (Art. 25).** Promotion
requires a survived attempt on record, plus a consistency check pinned
to the hash of the Intellect version current *at promotion time* — if
Intellect moves after the check, promotion demands a re-check. Evidence
volume counts for nothing; the attempt is the currency.

**D26. Attempts are historical by construction (Art. 39).** An attempt
must cite Corpus references; no field exists for a live-conversation
rehearsal, so the forbidden shortcut is unrepresentable.

**D27. Terminal states carry their own preconditions.** Rejected needs
a failed attempt actually on record; suspended needs two live survivors
and blocks both from promotion, linked as a pair on both sides; stale
is expansion-only per the Article's own definition; withdrawn needs its
reason. Terminal is terminal — resolution is a new proposal citing the
old, keeping the record append-only in spirit as well as bytes.

**D28. Two promotion paths, two authorities.** psyche_standing
proposals promote without the Architect (Art. 33): Seira establishes
her own character by surviving her own attempts to break it — this is
the self-creation loop, and it is exposed to her as tools.
Intellect proposals promote only through IntellectStore's existing
ratification gate, Architect phrase and all (Art. 27), with the
proposal_id preserved in the Intellect chain.

**D29. Dispensation is honest about its danger (Art. 30–31).**
Invocation must cite the Intellect-grade condition authorizing it,
auto-generates the mandatory retroactive correction proposal in the
same act, is logged as its own event type never folded into ordinary
reversion, and cannot close without that proposal. It is CLI-only this
phase: handing an Intellect-bypass to the live model before the
Instrument guardrails exist (Phase 5) would be recklessness dressed as
fidelity.

**D30. A bug caught and named.** The tripwire extension initially
imported the reversion errors inside the try block, after the Unity
check — a Unity failure would then NameError in the except clause
instead of halting cleanly. Hoisted; the full suite caught it.

## Phase 5 — Instruments

**D31. Fifth chained store; escalation blocks, not just logs.** Art. 26
verbatim: three local-feedback runs on one (instrument, task_type)
without an intervening clean run auto-escalates, tagged
instrument-initiated — and the task-type then refuses execution until a
paradigm_revised event citing that escalation exists. "Ought to
terminate in rest" made operational: further local patching is
structurally impossible once non-convergence is established.

**D32. Spawning rights are a required field, not a policy (Art. 35).**
Every spawn demands a psyche_judgment_ref; surfacing a need is its own
event, never a spawn. Depth enforced at 3 (Art. 34), named honestly as
an Intellect-grade parameter awaiting Phase 6 extraction rather than
buried as a constant.

**D33. Derivation is mandatory on every execution (Art. 5, 14).**
Paradigm version + licensing judgment recorded per execution; cause is
instrumental by construction; output_ref into the Corpus required —
untraceable output "is not an act of Seira's at all."

**D34. Skills are shared, versioned, judgment-attributed (Art. 37).**
The lighter mechanism implemented as exactly that: one required
judgment ref, no full proposal review. Executions cite skill id +
current version; stale-version and retired-skill citations refused so
derivation stays true.

**D35. Health is real now (Art. 44).** Convergence vs escalation
reported from actual execution records; the Phase 4 "n/a" honesty
discharged.

**D36. Phase 5b named, not faked.** Wiring Hermes's live
subagent_lifecycle so real subagent runs create execution records
automatically is documented follow-on work; the governance layer does
not pretend the wiring exists.

## Phase 5b — Live Delegation

**D37. The tag IS the trace (Art. 5).** Delegation goals carry
[seira:inst-NNNNN/task-type]; the derivation travels in the delegation
itself. Untagged completions are audited as noise ("not an act of
Seira's at all"), never recorded as executions.

**D38. Observation is honest about what it knows.** on_delegation maps
non-empty result → clean, empty → local_feedback — the one judgment a
parent-side hook can truthfully make ("did it terminate in rest").
Three empties on a task-type escalate through the existing Art. 26
machinery with zero new logic. Finer convergence judgment remains
Psyche's, via the manual execution tool. The hook never raises: a
refused or failed observation becomes an audit event, not a broken turn.

**D39. The gate governs; the sandbox secures.** delegate_task passes
through tool_execution middleware that refuses untagged goals, retired
Instruments, and escalated task-types — one bad task poisons the whole
batch. Hermes middleware is fail-open by design, so this is a
governance layer keeping an honest Seira honest, and is recorded as
such; the security boundary remains the per-tenant sandbox
(MULTITENANCY.md).

## Phase W1 — The Sanctum

**D40. W1 is safe by scope.** The web chat's tool surface is exactly
the provider's ten tools — writes to her own governed stores, no shell,
no filesystem, no delegation runtime. The per-tenant sandbox
requirement (D16) is therefore not yet triggered; it becomes mandatory
the moment the full Hermes engine attaches. Recorded so the boundary
is crossed knowingly, never drifted across.

**D41. Onboarding IS Genesis.** Signup allocates a tenant from the
account's random id (unspoofable); the onboarding form authors Unity
and founding Psyche in the new Architect's own words; founding
Intellect is the Constitution + Codex, bundled in the repo — every
tenant Seira is founded on the same doctrine and diverges from there,
exactly as the Preamble describes. Ratification in the UI requires the
typed phrase; it is never prefilled.

**D42. Chat is seira_core speaking, not a second brain.** System
prompt = the verified identity render (halt-aware: a halted Seira
returns 503, everywhere). Conversation history is Corpus — plain
append-only JSONL, deliberately un-chained per Art. 13/23, the one
grade whose amendment is continuous and unreviewed by design. LLM
client injected; the whole loop is tested with a scripted model, no
network.

**D43. Platform state lives outside every tenant tree.** Accounts and
sessions under SEIRA_PLATFORM_ROOT; scrypt password hashing from the
stdlib; server-side sessions, httponly + samesite=strict cookies.
Single-process JSON stores for W1, stated plainly; revisit before
multiple workers.

**D44. The bridge is Hermes-optional.** seira_bridge falls back to a
minimal MemoryProvider shim when the Hermes tree is absent, so the
Sanctum ships as a slim container (Dockerfile.sanctum: seira_core +
bridge + web + founding docs only) while the same bridge code registers
as a first-class provider inside the full fork. Verified both ways:
the suite runs with Hermes on the path; a simulated slim layout builds
the app without it.


**D45. Correction: no second cron service.** Railway volumes attach to
exactly one service — a separate tripwire cron service could never see
the web service's /data. The sweep instead runs as a background thread
inside the same process (seira_web/tripwire_loop.py), sharing the
volume for free, plus an unauthenticated /healthz for external
monitoring without SSH. This replaces the two-service plan in §11.

**D46. Correction: founding texts moved out of docs/, and off .md.**
The fork's own .dockerignore excludes "docs/" and "*.md" wholesale
(for Hermes's Docusaurus site); that silently stripped the founding
Constitution and Codex out of every Sanctum build despite being
correctly committed to git — invisible until the build actually
failed. Moved to seira_founding/*.txt at the repo root, a path and
extension neither ignore rule touches. Verified: a simulated slim
layout builds and produces the full ~46KB founding text with no
docs/ directory present at all.

## Phase W2 — The Dynamic Chat

**D47. Chat is primary; the console serves it.** / is the conversation;
/console is governance. The visual identity moved to the purple void
with golden text, the Cinzel Decorative wordmark, and the vesica
piscis sigil (pulsing, center point, ray descending) as logo and
favicon — Loshem's stated vision, executed with rust still reserved
for the halt alone.

**D48. Dynamics show only what actually ran.** The SSE stream emits
her real phases and real tool calls with human labels ("Writing her
Psyche", "Attempting falsification"); there is no chip for
capabilities she does not have — no fake "web searching". When search
or delegation joins her tool surface, its activity appears with zero
UI changes, because the UI renders whatever fired.

**D49. Edit and regenerate are supersession, never deletion
(Art. 23).** A supersede_from record marks the abandoned branch; the
model's view skips it; the full record keeps it forever. Tested: the
raw file retains both answers and both questions.

**D50. Attachments are text for now.** .txt/.md up to 200KB, injected
into the turn with a recorded attachment marker. Voice capture and
read-aloud are browser-native (Web Speech API) — no audio ever
touches the server. PDF and richer formats arrive with the full
engine, not before.

## Correction — Length Limits

**D51. The real bug: max_tokens was hard-capped at 2048.** That number
was never chosen deliberately — it was a placeholder that made W1's
initial tests pass and was never revisited. Both reported symptoms
(cut-off replies, a blocked comprehensive skill) traced to it: skill
authorization failed because the tool-call JSON itself got severed
mid-argument by the same ceiling. Raised to a configurable
SEIRA_MAX_TOKENS (default 16000; current Sonnet-class models support
materially more — verified against current docs rather than assumed,
since training-data numbers on this point age quickly). httpx timeout
raised from 120s to a configurable 600s, since a longer generation
needs longer to arrive, not just more room to exist in.

**D52. Two distinct truncation cases, handled differently, on purpose.**
A pure-text reply cut by the ceiling is auto-continued (bounded at 4
rounds) and delivered to the Corpus as one whole answer — the fragment
is never what gets stored or shown. A tool call cut mid-JSON is the
opposite case: it must NEVER be executed as-is (a half-written skill
paradigm silently saved would be worse than an error). Instead it's
refused with an honest, actionable message back to the model, which
can then retry more concisely or split the work — proven with a test
that a "comprehensive skill" scenario recovers and succeeds.

**D53. Malformed tool arguments can no longer crash a turn.** Both the
chat loop and the bridge's own dispatch now catch incomplete/invalid
arguments and return a normal {"ok": false, "error": ...} tool result
instead of an unhandled exception — closing the path from "the request
was cut short" to "the user sees a raw technical failure."

## UI Update — Chat Interaction Polish

**D54. Auto-growing composer, no fixed height.** The textarea grows
with `scrollHeight` on input, capped at 12rem, then scrolls internally
— never a cramped fixed box for a long message.

**D55. Composer is structurally pinned, not just visually.** html/body
now use `overflow: hidden`; `.msgs` is the sole scrolling region inside
a flex column, and `.shell` uses `100dvh` (with a `100vh` fallback) so
mobile browser-chrome resizing can't push the composer off-screen. The
composer was never actually supposed to move — this closes the actual
cause rather than re-pinning it with `position: fixed`, which would
have fought the sidebar layout.

**D56. Load-at-bottom.** `requestAnimationFrame(scrollEnd)` runs once
after the DOM is painted, landing on the latest message immediately —
no manual scroll required on page load.

**D57. Sidebar is collapsible two ways.** A History toggle in the top
bar, and clicking anywhere in the live chat area auto-collapses it —
implemented via a capturing click listener on `.chatcol` with
`stopPropagation` inside the sidebar itself so its own links and the
new-conversation button remain unaffected.

**D58. Send is a golden arrow; voice capture is a standalone golden
mic beside it,** not buried in the hamburger tray — matching the
stated intent that speaking to her should be as immediate as typing
to her.

**D59. Model selection and response-length preference are real,
server-honored settings — not decorative.** The hamburger tray adds
both as selects, persisted in localStorage, sent with every request.
Model selection reaches the actual Anthropic client (proven with a
recording fake in test_model_selection.py: her deployment now runs
the current lineup — Sonnet 5 as the new default, Opus 4.8, Haiku 4.5,
Fable 5, and Sonnet 4.6 kept as an explicit legacy option). Length
preference is instruction-based, appended to the system prompt and
clearly marked as a UI setting rather than identity — never a hard
character-count truncation, since that would silently reintroduce the
mid-sentence cutoff problem already fixed. DEFAULT_MODEL updated from
claude-sonnet-4-6 to claude-sonnet-5 to reflect the current lineup.

## UI Update Round 2 — Diary, References, PDFs, Web Search, Console Tabs

**D60. The Diary is built exactly to Article 41, not adapted from it.**
Two kinds sharing one hash-chained, Unity-anchored store (so tampering
across parts is caught together, not separately): 'self' entries
require provenance to a real underlying record — a suspended
contradiction, a pending proposal, an affinity's weight moving, a
dispensation, a convergence-failure pattern; 'architect' entries
require provenance too, described in the tool schema as descriptive-
never-diagnostic (code enforces the presence of a reference; it cannot
judge tone — that discipline is asked of whoever writes the entry, the
same way the Article asks it of her). /diary is the Architect's
default-visible read path the Article requires to exist.

**D61. Reference files are Corpus-grade, explicitly, and pageable.**
Saved under corpus/references/ (not Psyche — Art. 13's wholly-temporal
grade), with a 40,000-character-per-call ceiling on recall so a large
document is paged through deliberately rather than forced whole into
one turn. Every upload is saved permanently AND a bounded slice
(default 6000 chars, SEIRA_INLINE_ATTACHMENT_CHARS) is injected
inline for immediate use — full content is never lost even when only
part of it fits in the current turn.

**D62. PDF support is real; OCR is honestly out of scope.** Text-layer
PDFs extract via pypdf, upload ceiling raised to 100MB as asked
(Starlette spools large uploads to disk, so memory isn't the
constraint — extraction time is, for very large documents). A
scanned/image-only PDF returns a clear, honest refusal rather than
silently producing nothing or garbage. OCR is a real, separate build
(page rasterization + an OCR engine) that fits naturally as its own
Instrument paradigm in a later phase — not something to fake here.

**D63. Web search is Anthropic's server-executed tool, wired
correctly as such.** Verified against current documentation that this
tool resolves in ONE response (server_tool_use + its result + final
text together) rather than requiring a client tool_result round-trip
— my first draft got this wrong and dispatched it like a client tool;
caught and fixed before shipping. The tool-version string is
configurable (SEIRA_WEB_SEARCH_TOOL) since multiple version strings
coexist across current documentation and this will keep moving. Toggled
per-request from the hamburger tray, off by default.

**D64. Answering the standing question honestly: no, she does not
have Hermes's tool ecosystem.** Her tool surface in the Sanctum is
exactly her own governance tools plus, now, diary/reference/web-search
— never shell, terminal, or OCR access. That parity requires the
per-tenant sandboxing already flagged as a real, unbuilt cost (D16,
D40). Web search was safe to add now specifically because it has no
filesystem or shell surface of its own.

**D65. Console is horizontal tabs, one grade at a time.** Unity |
Intellect | Psyche | Reversion | Instruments, client-side toggle, no
new requests per tab. Intellect gained real version history; Reversion
gained the full proposal list (not just what's awaiting ratification);
Instruments gained a proper panel (convergence, instrument list,
skills) — the console was previously narrower than what already
existed to show.

**D66. The edit-icon bug, root-caused.** A freshly sent message had no
id in the DOM until a full page reload, because the id was only known
after the whole turn (including the model's reply) completed. Fixed
by emitting the real id via SSE the instant the message is recorded —
before the model is even called — proven by a test asserting the
`user_recorded` event arrives strictly before `reply`.

**D67. Sidebar and header interaction, corrected to spec.** A small
edge tab (not a header button) toggles history; clicking the live
chat auto-collapses it; the header hides on scroll-down and reveals on
the slightest scroll-up, tracked against a scroll-delta on the sole
scrolling region (.msgs) rather than the whole page.

## Web Search — Made Standing, Not Toggled

**D68. Web search is now a standing capability, on by default.** The
per-message checkbox is gone from the UI; the tool is present in every
turn and she decides autonomously when a question needs current
information — the same relationship she has to her Psyche tools, not
a leash the Architect holds each time. A body without a `web_search`
key at all still includes the tool (tested).

**D69. An org-level kill switch remains, deliberately not user-facing.**
`SEIRA_WEB_SEARCH_ENABLED=0` disables it platform-wide (cost control at
scale, or an incident response lever) without reintroducing a
per-message decision — that distinction matters: the toggle removed
was about her agency in a single conversation; this one is an
operator's infrastructure control, a different kind of decision
entirely.
