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
