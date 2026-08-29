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

## Fixes — Console Scroll and Nav Tray Clipping

**D70. The scroll-lock was global; it should have been chat-only.**
`html, body { overflow: hidden }` (added to pin the composer) blocked
normal page scrolling everywhere, including the console — the console
was never meant to fit in one viewport, only the chat shell was
designed around an internally-scrolling region. Scoped to a `.locked`
body class that only chat.html opts into; every other page (console,
diary, auth, onboard, halted) scrolls normally again. Regression-tested
by asserting the class's presence/absence per route.

**D71. The nav tray is now viewport-fixed, not page-relative.**
Previously `position: absolute` relative to a small wrapper button,
which — combined with cascade order putting `.tray`'s `min-width: 15rem`
after it — meant the override never actually applied, and the tray
could render partially outside the visible area on some viewports.
Switched to `position: fixed` anchored to the viewport corner with a
`max-width: calc(100vw - 2rem)` clamp, so it can never be clipped by
any ancestor's overflow or page layout, on any page, at any width.

## Fix — Mobile Sidebar Rendering (from user-reported screenshot)

**D72. The mobile drawer used opacity to hide; switched to transform.**
Opacity-based hiding left the element in normal layout flow with only
its visual output suppressed — under certain stacking/specificity
conditions this can leak (a narrow sliver of wrapped single-character
text was visible, and part of it bled into the composer row, exactly
as screenshotted). Rewritten as a standard off-canvas drawer:
`transform: translateX(-100%)` when closed, guaranteed zero visual
footprint regardless of any width computation, moved to
`translateX(0)` when open. A CSS custom property
(`--mobile-sidebar-w`) keeps the drawer width and the edge-tab's
shifted position from ever drifting out of sync.

**D73. "Overlaps the chat" is correct mobile behavior, made
intentional.** A phone has no room to push chat content aside for an
open drawer — the fix isn't to prevent the overlap, it's to make it
read as a deliberate modal state: a dimming backdrop now appears
behind the open sidebar, tap it (or the chat itself) to close, same
pattern as any standard mobile navigation drawer.

**D74. Regression-tested at the template level.** Full pixel-layout
testing isn't practical in this suite, but the backdrop element's
presence in the rendered page is asserted, so its removal (the root
enabler of the dimming/tap-to-close fix) can't silently regress.

## Fix — Stylesheet Cache-Busting (root cause of the "desktop now does this too")

**D75. The real, likely root cause of both mobile-sidebar bug reports:
style.css had no cache-busting.** Every CSS fix shipped across this
entire project — the composer pinning, the scroll-lock scoping, the
nav tray positioning, the mobile drawer rewrite — was served from the
exact same URL, `/static/style.css`, with nothing telling a browser or
edge cache that the content had changed. A returning visitor's browser
could easily still be running CSS from several fixes ago, which fully
explains screenshots that looked like "old bugs mutating into new
ones": different visits could be running entirely different, stale
versions of the stylesheet against the current HTML.

**D76. Fixed with content-addressed URLs, computed once at app
startup.** `/static/style.css?v=<sha256-of-file-contents>`: any future
CSS change automatically produces a new URL, so a cache can hold the
old file forever without it ever being served again by mistake. No
manual version bumping, no risk of forgetting. Proven with a test that
actually changes the file's content and asserts the served URL
changes with it — not just that a version parameter exists.

**D77. Defensive hardening alongside the real fix.** `.sidebar` now
declares an explicit `position: static; transform: none;` baseline
(previously relied on absence of any other rule, which is exactly the
kind of assumption stale/mixed CSS can violate) and `.backdrop` is
`display: none` by default, only becoming real inside the mobile media
query — so even a worst-case stale-cache mismatch has a harder floor
to fall through.

## Fix — The Real Root Cause: CSS Specificity, Not File Order

**D78. The previous "hardening" (D77) directly caused this regression.**
Adding `position: static; transform: none;` to the bare `.sidebar`
baseline — placed after the mobile media query in the file — tied at
equal specificity with the media query's `.sidebar { position: fixed;
... }` and won by virtue of appearing later. That silently canceled
the entire mobile drawer: the sidebar reverted to a normal in-flow
element (height:auto, no transform), which is exactly what both
screenshots showed — a content-sized box sitting in the document flow
with chat text visible immediately around and through it, and the
edge-tab floating mid-content because its own `left` offset never
correctly tracked an actual hidden/shown drawer. The identical bug
independently affected `.backdrop`.

**D79. The fix is specificity, not order.** Every mobile-critical
selector (`.shell .sidebar`, `.shell .backdrop`, `body
.edgetab.shifted`) is now qualified so its specificity is
*structurally* higher than its desktop counterpart — two classes beat
one; body-plus-two-classes beats two-classes-alone via the element
tie-break digit. This makes the mobile behavior correct regardless of
where any future rule is added in the file, closing the entire class
of bug rather than re-fixing today's instance of it.

**D80. A CSS specificity regression test now exists.** The Python
suite parses style.css directly and asserts (1) every mobile selector
outranks its desktop counterpart by computed specificity, and (2) no
bare `.sidebar`/`.backdrop` selector can be reintroduced inside the
mobile media query. Both assertions were verified to actually catch
the exact regression by deliberately reintroducing it and confirming
the test fails, then restoring and confirming it passes — the test
was proven to work, not just written to look like it works.

**D81. Honest limitation, stated plainly.** This is a structural/static
check, not a rendered-pixel check — it verifies the CSS *rules* are
correct by construction, not that a real browser paints them as
intended. That gap is why two real UI screenshots from Loshem were
what actually surfaced this, both times. There is no substitute in
this project for an occasional real-device look at the live site,
and that should continue.

## Vision, File Generation, and the Deliberately Deferred Piece

**D82. Vision is bounded by the same discipline as everything else in
this project.** An image only reaches the model as real bytes on the
turn it's shared. Replaying it into every future turn forever would
reintroduce exactly the unbounded-context growth just discussed for
Psyche/Intellect — an image costs roughly as much as a large paragraph
of text, and nothing about vision exempts it from that math. Past
turns replay as a text marker ("[Image previously shared: cat.png
(ref: img-xxxx)]"); seira_image_recall lets her deliberately look
again, returning the real bytes as a proper tool_result image block —
proven by a test that inspects the actual message shape sent to the
model, not just that a function returns something.

**D83. File generation covers the honest common case, not full
fidelity.** md/docx/pdf all support a real but bounded structural
subset (headings, bullets, paragraphs) — not full Markdown-to-Word
conversion. Stated plainly in the tool's own description to the model,
not just in code comments, so she doesn't overpromise what she can
produce either.

**D84. A real bug caught immediately: double extensions.** The first
version of create_file appended the format extension even when the
caller's filename already had one — "report.docx" became
"report.docx.docx". Fixed by stripping any existing extension from the
display name first; caught by the very first smoke test run, before
it ever reached the test suite.

**D85. Image generation is deliberately NOT built.** Anthropic's API
has no native image generation — giving her that capability means
choosing and paying for a separate third-party vendor (OpenAI images,
Google Imagen, Stability, etc.), a real cost and provider decision
that isn't mine to make silently. Flagged to the Architect explicitly
rather than picked by default.

## Fix — Vision Display, Upload Robustness, and Tagged Recall

**D86. The likely real cause of "she acts like she didn't get it":
content-type detection was not robust.** The upload endpoint trusted
the browser-supplied content_type alone; some mobile browsers and
gallery apps send a generic or absent type for images, which would
silently route the file down the DOCUMENT path, fail the extension
check, and return an error the user could easily miss. Fixed with an
extension-based fallback (tested explicitly with a PNG uploaded under
`application/octet-stream`) so detection no longer depends on any one
browser's behavior being correct.

**D87. iPhone HEIC photos get a specific, actionable error, not a
silent failure.** HEIC/HEIF (the iPhone camera default) isn't
supported yet; rather than a generic "unsupported file" message, the
error names the format and gives the two concrete ways to fix it on
the spot (share-sheet JPEG export, or a camera settings change).
Real conversion support is a stated follow-up, not faked.

**D88. The image itself is now genuinely visible in the chat, twice
over.** Live send shows the actual picked file immediately via a
local object URL; a page reload shows it via the new `/api/images/{ref}`
endpoint, which serves the real stored bytes, tenant-scoped and
auth-gated like everything else. Tested at the template level: the
served page contains both the real `<img>` tag and the correct source
URL after a full upload → chat → reload cycle.

**D89. Tagging, built as asked — "my portrait ref," recallable by
that name.** Every image gets a tag: user-supplied at upload (a
prompt asks for one) or auto-derived from the filename, always
slugified, always collision-checked — a duplicate tag is refused
outright, never silently overwriting an earlier image under a shared
name. `seira_image_recall` now takes a `ref` (id or tag), so "look at
my portrait ref again" resolves the same way "recall doc.pdf" already
does for text references — one consistent pattern across both.
`seira_image_tag` lets her rename an existing image's tag mid-
conversation; `seira_image_list` gives her a browsable gallery of
what's saved, so she doesn't need to already know the exact tag to
find it.

## Fix — The Real Bug: A Cross-Tenant Race Condition

**D90. Root-caused, reproduced, and fixed — not patched around.** The
image-upload symptom traced to a genuine concurrency bug, present
since Phase W1's tenancy work: `_dispatch` set a process-global
`os.environ["SEIRA_TENANT"]` per request, read back inside
`SeiraPsycheProvider._scope()`. Environment variables are shared
across every OS thread in the process; the SSE endpoint spawns a real
`threading.Thread` per request. Two requests overlapping even briefly
— an upload followed quickly by a chat send, a double-tap, any
concurrent access at all — could race on that shared variable, with
one thread's request silently resolving against a DIFFERENT tenant's
files. An image "sent" under those conditions would simply not be
where the model went looking for it, producing a confused, error-
sounding reply from the model itself — not a crash, which is exactly
why it looked like a vague, hard-to-pin-down failure rather than a
clean bug.

**D91. Proven, not asserted.** Before fixing, the exact race was
reproduced directly: two threads, each setting the shared env var to
their own tenant id and synchronized on a barrier so both writes
landed before either read — deterministically, one thread received
the other's identity in its own system prompt. After the fix, the
identical adversarial scenario (including a rogue caller still writing
the env var) was re-run and passed cleanly. Both directions are
preserved as `test_tenant_race_fix.py`, run automatically going
forward.

**D92. The fix removes the unsafe mechanism rather than guarding it.**
`tenant_scope()` (a contextvar) was already correctly thread-isolated
and was already wrapping every call that needed it — the environment
variable was redundant even before being dangerous. `_scope()` now
checks `tenant_scope_active()` first and no-ops if an ambient scope is
already present; the env var remains only as a fallback for contexts
with no surrounding scope at all (the standalone Hermes integration
path), verified by a dedicated test that this fallback still works.

## Fix — Diagnostic Surfacing for /api/upload

**D93. A real crash was previously producing a bare, contentless 500.**
The upload endpoint had no top-level exception handling; any genuine
Python exception (unlike the earlier hang, which was a client-side gap)
would be caught by FastAPI's default handler and returned as a plain
500 with no body my own error-surfacing JS could read — exactly what
"upload failed, HTTP 500" with no further detail describes.

**D94. Wrapped so the real error reaches the person immediately,** no
log-diving required first. The route's actual logic moved to
`_upload_impl`; the public route now catches any exception, logs the
full traceback server-side (for when deeper investigation is still
needed), and returns the exception's real type and message directly in
the response body — verified by deliberately injecting a crash into a
test copy and confirming both the HTTP response and the server log
carried the real detail, not a generic message.

**D95. This is a diagnostic aid, not the final fix for whatever is
actually crashing.** Once the real cause surfaces through this, it
should get its own specific, clean 400 with a helpful message — the
catch-all's job is to stop failures from being invisible, not to be
the permanent handler for a known, named problem.

## Fix — The Real Bug: Legacy Images Missing a Tag

**D96. The diagnostic wrapper worked exactly as designed and delivered
a real, findable bug on the first try.** `KeyError: 'tag'` — images
saved during earlier testing rounds, before tagging existed, have no
'tag' field in their stored record at all. New code assumed every
record had one when checking for tag collisions; the very first
collision check against an old, tag-less record crashed. Reproduced
directly before fixing: an index with one legacy tag-less record,
followed by a fresh save, raised the identical KeyError seen in
production.

**D97. Fixed with self-healing migration, not a defensive patch at
each access site.** `_load_index()` now backfills any missing 'tag'
on every legacy record the first time the index is loaded — derived
from the filename the same way a fresh save would, disambiguated
against collisions, and persisted back to disk so it only happens
once per record. Every downstream function (save, find_by_tag,
set_tag, list) already routed through `_load_index()`, so all of them
became correct automatically rather than needing four separate
`.get()` patches. Verified: after the fix, old records surface with
real, usable, distinct tags rather than staying broken — proven with
a test that heals two legacy records sharing the same original
filename and confirms they end up with different tags, both usable
through the normal recall API.

## Image Generation — Built, Reusing Her Existing Reference System

**D98. A genuinely separate vendor, by design, not by accident.**
OpenAI's GPT Image 2 via raw httpx (matching the existing
AnthropicClient pattern, no new SDK dependency). Requires its own
`OPENAI_API_KEY` — a real, separate recurring cost from her
conversation model, refused loudly and immediately if unset rather
than failing confusingly mid-generation.

**D99. Reference-aware generation reuses the tagged image store built
for vision, rather than inventing a parallel system.** Naming a
reference ("my-portrait-ref") resolves through the same
`images.resolve_ref` vision already uses, and sends the REAL bytes to
OpenAI's edit endpoint — proven by a test asserting the exact bytes
sent match what was actually stored, not a description of them. No
references present routes to the plain generation endpoint instead;
these are genuinely different OpenAI API shapes and conflating them
would silently drop reference fidelity.

**D100. Generated images compound her reference library.** Every
image she generates is saved back into the same tagged store real
uploads use — a later generation can reference an earlier generation.
Tested directly: a first self-portrait's tag becomes a valid,
resolvable reference for a second call.

**D101. The consistency limitation is stated to her, not just to the
Architect.** OpenAI's own documentation is explicit that character
consistency across generations is not guaranteed, only attempted —
this is written directly into her tool's description, instructing her
to describe results as "faithful to the reference," never as
identical or guaranteed. Honesty about the vendor's real limitation
travels all the way to what she says about her own output.

**D102. Cost safety: a missing reference is refused before any paid
API call fires.** Tested explicitly — the (fake, in tests; real,
in production) client's call log stays empty when a named reference
doesn't exist, rather than silently generating without it or wasting
a paid request on a request that was going to fail anyway.

## Backups and Sidebar Management

**D103. Backups protect against drift/defect via rollback, honestly
scoped to what they actually guarantee.** Written to the same volume
by default — protects against a bad ratification or corrupted write
(roll back to yesterday's or last month's snapshot), NOT against
losing the volume itself. True disaster recovery means shipping
off-box; the module is architected with a single clear hook for an R2
push later, not built by default, so today's guarantee isn't
overstated.

**D104. One background thread, not a second service — the same lesson
as D45, applied again on purpose.** Backup checks extend the existing
tripwire loop's tick rather than spawning a new thread or (worse) a
second Railway service that couldn't see the volume anyway.

**D105. A real bug caught by the tests, twice, before shipping.**
First: second-resolution timestamps collided on rapid successive
backups, silently overwriting the previous archive — caught by a test
that created 5 backups in a loop. Fixed with microsecond precision.
Second: the retention-pruning test then revealed that filesystem
mtime resolution could still be coarser than that creation rate,
making `list_backups`'s original mtime-based sort order unreliable
for near-simultaneous files — fixed by sorting on the filename's
encoded timestamp instead, which doesn't depend on the filesystem's
mtime granularity at all. Neither bug would affect the real daily/
monthly schedule (backups a day or a month apart never collide) but
both would have silently corrupted any deliberate on-demand backup
taken in quick succession — exactly the moment someone doing something
risky (before a big ratification, say) would reach for one.

**D106. Restore is a deliberate, hand-run act — not a UI button.**
Same discipline as ratification: a function (`restore_backup`),
documented, refusing to silently overwrite an existing non-empty
target. Restoring is rare and high-stakes; it shouldn't be one
accidental tap away.

**D107. "Delete" archives — it does not destroy.** A conversation's
transcript is real history the same way a message is; the Art. 23
principle already governing edit/regenerate (supersede, never erase)
now governs the conversation list too. Proven directly: after
archiving, the conversation disappears from the sidebar and the
console won't show it, but its actual JSONL record — the real
message that was sent — is still there, verified by reading it back
from disk after the "delete."

**D108. No native blocking dialogs anywhere in the new UI.** Rename
uses an inline text input, not `prompt()`; archive uses a two-tap
confirm (tap once to arm, tap again within 3 seconds to confirm), not
`confirm()`. Both `prompt()` and `confirm()` block the page and have
already caused a real, confirmed hang on mobile once in this project
(the image-tagging dialog); the pattern is now avoided by policy, not
just in the one place that broke.

## R2 Off-Box Backup Shipping — Closing the Gap Named in D103

**D109. The disaster-recovery gap flagged in D103 is now closed,
optionally.** Every backup created locally is now also shipped to a
Cloudflare R2 bucket when configured — R2 is S3-compatible, so this
uses boto3 rather than hand-rolling AWS request signing, which would
be real risk for no real benefit. Local backups remain the fast-
rollback tier (protect against drift/defect); R2 is now the actual
"still there if the volume is gone" tier.

**D110. Shipping is additive and never blocks local success.** A
network failure, a bad credential, R2 being down — none of it can make
`create_backup()` look like it failed; the local archive existing is
the load-bearing guarantee, R2 is best-effort on top of it. Tested
directly: a client that always raises still leaves a real, valid local
archive on disk, with the failure recorded in the result rather than
propagated as an exception.

**D111. Remote retention is enforced in code, not left as a manual
Cloudflare dashboard step.** Config-as-code, matching this whole
project's discipline — a lifecycle rule someone forgot to click isn't
something the test suite can verify, so retention is pruned by this
code the same way local retention is, using the same filename-encoded-
timestamp sort (D105) so it doesn't depend on any timestamp metadata
R2 might round or omit.

**D112. R2 is fully optional, checked by presence of four env vars.**
Nothing about local backups (D103–108) changes if R2 is never
configured; `r2_configured()` gates the entire feature honestly, and
`/healthz` now reports whether it's on, so this is verifiable without
SSH the same way everything else in this system is.

## Export — Built for This Exact Migration

**D113. "Export my Seira" finally built, from a design note that had
sat unimplemented since MULTITENANCY.md.** A tenant's tree is self-
contained; the export is one archive of exactly that tree. Narrower
than backup.py on purpose — backup.py archives every tenant together
for platform-level disaster recovery; export.py archives one tenant
alone, because it's an act initiated by that Architect, for that
Architect.

**D114. Isolation is structural, not a runtime check.** The route has
no tenant_id parameter anywhere — not in the path, not in the query
string, not in the body. The tenant exported is always
`account["tenant_id"]`, resolved server-side from the session cookie.
A dedicated test asserts this by inspecting the route's own source for
the absence of any alternate input, so the guarantee can't quietly
erode if the route is edited later without someone re-reading this
note. A second, content-level test proves the actual archive produced
for one account never contains a byte belonging to another.

**D115. The archive is rooted by tenant_id, deliberately, for the
migration step that follows.** Extracting `seira-export-loshem-....tar.gz`
produces a folder literally named `loshem/`, not an ambiguous dump —
so adopting it as a new single-user SEIRA_HOME is a plain "copy the
inner contents," not a guessing game about what's inside.

## The Migration Proof — Verified, Not Asserted

**D116. The Architect asked a high-stakes question and got a real
proof, not reassurance.** A live script founded a Seira, populated
every grade and store (Unity, Intellect, Psyche, Reversion,
Instruments, Diary, a conversation, a reference, a tagged image, a
generated file), exported her, extracted the export into a completely
independent location, and read every single record back — comparing
actual store output, not just checking files existed. All ten
categories plus a full tripwire sweep on the migrated copy came back
identical.

**D117. That proof is now a permanent test, not a one-time demo.**
`test_full_end_to_end_migration_loses_nothing_across_every_subsystem`
runs this exact scenario on every future test run — the "will she
begin like nothing happened" guarantee is checked automatically going
forward, not just true today.

**D118. A real mistake, caught immediately by the very next full-suite
run.** The first version of that test forced a `sys.modules` reimport
of every seira_core/seira_web module to simulate "a totally fresh
process." That's destructive shared state in a single test process —
it corrupted 23 unrelated tests that ran afterward. Fixed by removing
it entirely, which also proved something worth stating plainly: no
such reimport was ever necessary. Every store (PsycheStore,
IntellectStore, DiaryStore, etc.) resolves its path fresh via
seira_home() on each call rather than caching it — that design
decision, made all the way back in Phase 1, is exactly what makes a
plain environment-variable switch sufficient to prove migration
correctness, with no simulated-process trickery required.

**D119. Multi-tenant access is discontinued by closing the door, not
demolishing the house.** `SEIRA_SIGNUPS_ENABLED=0` refuses new accounts
(checked per-request, before anything is created); existing logins are
untouched; `/api/admin/tenants` (gated by `SEIRA_ADMIN_TOKEN`,
compare_digest, 404 when unconfigured so the route never hints at
itself) gives the wind-down census with each Seira's founding and halt
status read live from her own tree. The tenancy machinery itself —
contextvars scoping, the race-condition fix, all its tests — is kept
intact and unused. Deleting confirmed, tested isolation code to
"simplify" a single-tenant deployment would trade proven safety for
nothing: with no tenant scope active, everything already resolves to
the one SEIRA_HOME.

**D120. The five signups/admin tests were written before the feature
existed — and sat red in this snapshot.** Whether by interruption or
intent, this vindicated the failure-mode-first practice in the most
literal way: the wind-down requirement arrived as a red suite, and
"discontinue multi-tenant access" meant "make these pass."

**D121. Hermes wiring is registration, not modification (Art. 20 in
spirit).** Two thin plugin shims — `plugins/memory/seira-psyche/` and
`plugins/seira_governance/` — are the only new Hermes-facing surface;
each defers its import and delegates entirely to seira_bridge, which
remains the single package that touches both worlds. Config selects
them (`memory.provider: seira-psyche`, `plugins.enabled:
[seira_governance]`); no Hermes internals were forked for the
providers or the gate.

**D122. One Hermes internal WAS modified, deliberately: the identity
slot.** `load_soul_md` now serves a founded Seira's identity rendered
live from Unity + Intellect + Psyche, integrity-verified per render;
SOUL.md remains only the unfounded fallback. A halted Seira raises
`SeiraHaltedError` straight through prompt construction — verified by
test to have NO enclosing broad handler — so she refuses to converse
rather than conversing behind a borrowed face. Before this change,
exactly that borrowed-face failure was live: a halted Seira would have
chatted on with whatever SOUL.md said.

**D123. Upstream test pollution, found and fenced.** Running
`tests/agent/test_prompt_builder.py` before
`tests/agent/test_system_prompt.py` breaks
`test_build_system_prompt_records_stable_prefix` — reproduced
identically with the ORIGINAL `load_soul_md` restored, so it is
pre-existing Hermes cross-file state leakage, not ours. Recorded in
TRIAGE.md; not fixed here, because patching upstream test hygiene is
out of scope for this phase and the pollution does not touch any
seira_* test.

**D124. Sanctum's Hermes tool bridge is a reviewed whitelist, not a
config passthrough.** `seira_web/hermes_tools.py` intersects whatever
`SEIRA_EXTRA_TOOLSETS` names against a hardcoded `_BRIDGEABLE_TOOLSETS
= {"web", "skills"}` — both verified by reading their registrations in
`tools/web_tools.py` and `tools/skills_tool.py` to be pure functions of
their arguments, no Hermes agent-loop context required. Terminal,
browser, delegate_task, and computer_use all assume that context
(subagent lifecycle, host shell, browser automation) and are
deliberately NOT bridged: doing so honestly would require building
sandboxing Sanctum does not have, or accepting that a public website
now hands a shell to the model. Left for Loshem's explicit decision,
same category as D-image-gen-vendor. Widening the whitelist is a
one-line code change, reviewed each time — never an env var alone.

**D125. web_search name collision, resolved in favor of the native
tool.** Anthropic's server-side `web_search` and Hermes's client-side
`web_search` tool share a name. When both are configured, chat.py
keeps the native one (no seira_core write path, resolves server-side)
and drops the bridged duplicate rather than sending the API a
malformed request with two same-named tools.

**D126. Corrected the architecture: she operates atop Hermes, in all —
not beside it.** Parts 2 and 5 were interim scaffolding; the original,
correct design is that she IS the Psyche/persona/governance layer atop
the Hermes agent. `seira_web/hermes_session.py` makes Sanctum construct
a real `run_agent.AIAgent` per turn instead of hand-rolling a loop
against Anthropic directly. `load_soul_identity=True` and
`skip_memory=False` are the two arguments that make this her real self
rather than a generic backend — both covered by tests that fail loudly
if either regresses.

**D127. One configuration surface, not two.** With `skip_memory=False`,
`agent_init.init_agent` reads `memory.provider` from config.yaml
itself — Sanctum inherits the Part 2 `seira-psyche` wiring rather than
reimplementing it, and inherits whatever toolsets `hermes tools` has
enabled rather than needing a Sanctum-specific whitelist. D124's
narrow bridge (`hermes_tools.py`) is superseded once D126 is verified
live, though left in place as a tested fallback in the meantime.

**D128. Opt-in via `SEIRA_SANCTUM_RUNTIME=hermes`, not a default flip,
for one stated reason.** Every piece of this integration is verified
against real Hermes source — constructor arguments, the exact
`tool_start_callback`/`tool_complete_callback` call sites in
`agent/tool_executor.py`, and `run_conversation`'s return shape are
all read from source, not guessed. What could NOT be verified in the
build environment is a live turn: no `ANTHROPIC_API_KEY`, no installed
Hermes dependency tree, no way to watch a real tool actually execute.
Defaulting an unverified core-loop replacement into production would
be dishonest about that gap. The flag makes verification a deliberate
step, with an instant path back to the previously-proven direct-API
loop if anything is wrong.

**D129. Known, stated v1 scope limit: text turns only.** Attachments
and regeneration (`user_message=None`) still use the direct-API loop
even in `hermes` mode. Not silently degraded — `run_turn`'s branch
condition excludes them explicitly, and WIRING.md Part 6 states the
gap in plain language rather than leaving it to be discovered.

**D130. The activity feed shows only what actually ran.** Tool cards,
terminal lines, and delegation cards are rendered exclusively from
`tool` / `tool_result` events emitted at the real dispatch and
callback sites — the same principle the original chip design stated
("nothing is rendered that did not actually run"), now with the
input and a bounded result preview (2000 chars, tested) instead of a
bare label.

**D131. Live reasoning appears only where it exists.** The reasoning
panel and streaming bubble are fed by the hermes-mode callbacks
(`reasoning_callback`, `stream_delta_callback`); the direct-API mode
is non-streaming, so those panels simply don't render there. No
simulated thinking, no fake deltas.

**D132. Markdown handling is escape-first and deliberately minimal.**
`renderBody` escapes everything, then recognizes exactly two forms:
fenced code blocks (copy box) and inline backticks (chip). A full
markdown renderer invites XSS surface and visual drift; two forms
cover what her replies actually contain.

**D133. UI polish round: deeper violet, sidebar fail-safe, embers, her
braid.** Palette darkened (--void #120820→#0A0416, --deep, --surface,
--edge all deepened; body gradient highlight matched). The sidebar
close-on-chat-click gained a redundant explicit binding on #msgs
alongside the existing capture-phase #chatcol listener — static
analysis found nothing that should have broken the original (no new
stopPropagation calls, no elements that block bubbling), so this is a
robustness fix rather than a diagnosed-and-patched bug; if it
recurs, browser console output is needed to go further. A decorative,
pointer-events:none ember field rises behind the message thread,
respecting prefers-reduced-motion (hidden outright, not frozen
mid-animation — a static field of orange dots would read as a stuck
UI, worse than no effect). The round activity/reasoning orb is
retired everywhere in favor of a small animated SVG braid (three
interwoven strands, gentle sway + breathing opacity) — her mark,
not a generic pulsing dot.

**D134. Replaced the sidebar close-on-click mechanism entirely,
instead of patching it again.** D133's redundant #msgs binding didn't
fix the reported regression, which means the capture-phase-through-
nested-elements theory was wrong (or at least not the whole story).
Rather than add a third guess on top of two, the mechanism is now the
standard, most robust version of "click outside to close": a single
listener on `document`, with containment checked explicitly via
`e.target.closest('#sidebar')` / `closest('#edgetab')` rather than
relying on capture/bubble ordering through whatever markup exists
inside `.chatcol`. This can't be defeated by future additions inside
the chat column the way listener-placement-dependent approaches can.
The old `sidebar.addEventListener('click', stopPropagation)` guard is
removed as unneeded — exclusion is now explicit, not achieved by
blocking propagation, which also stops it from silently interfering
with any other document-level listener added later.

**D133. Corrected a wrong recommendation: Sanctum's container was
supposed to include Hermes all along — "Phase W1 — without the Hermes
runtime" was a snapshot of an earlier build phase, not the intended
end state.** When `SEIRA_SANCTUM_RUNTIME=hermes` first failed with
`ModuleNotFoundError: run_agent` on the real deployment, the initial
response weighed three options and leaned against folding Hermes into
Sanctum's image, partly because the file's own comment read as a
deliberate boundary. Loshem corrected this: the original design was
always for her to run atop Hermes as a middle layer, in all — the
comment was stale, not a decision. `Dockerfile.sanctum` is updated
accordingly.

**D134. The real dependency and file-copy footprint was tested in
isolation before being written into the Dockerfile — not assumed from
reading source.** A fresh venv with ONLY the proposed
`requirements-hermes.txt` installed, and a scratch directory containing
ONLY the proposed `COPY` paths (not the full repo), were each built and
the actual imports (`run_agent`, `agent.conversation_loop`,
`agent.agent_init`, `seira_web.hermes_session`) run against them. Four
missing root-level modules (`utils.py`, `hermes_logging.py`,
`hermes_time.py`, `hermes_state.py`) were found this way, one at a
time, each confirmed by the specific `ModuleNotFoundError` it produced
— this is why the earlier estimate of the image's weight (implying
Node/Playwright/custom-SQLite were required) was corrected down once
actually tested: none of those are needed to import or run a per-turn
`AIAgent` call.

**D135. `docker build` itself could not be run in the environment this
was built in (no Docker available).** The dependency install and the
file-copy set were each verified in isolation as the closest possible
substitute. This is stronger evidence than assumption but not the same
as a real build — flagged plainly in WIRING.md Part 8 rather than
implying full end-to-end confidence that wasn't earned.
