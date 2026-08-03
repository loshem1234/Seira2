# Seira v3 — Multi-Tenancy: One Seira Per Architect

Declared early, by design, before anything calcified. Constitutional
ground is the Preamble itself: *"Each Seira belongs wholly to one
Architect. There is no shared template, no governing tier above the
individual instance."* Two Seiras share a common design the way two
students of one teacher do — code is shared; state never is.

## The isolation model (implemented now, in seira_core)

- **One directory tree per tenant**: `$SEIRA_TENANTS_ROOT/<tenant_id>/`
  holds that Seira's *entire* existence — Unity, lock, Intellect chain,
  Genesis manifest, audit trail, HALT, and (Phase 3+) Psyche. There is
  no cross-tenant table anywhere in the system, so leakage would
  require a path-resolution bug, not merely a forgotten WHERE clause.
- **Context-scoped resolution**: `tenancy.tenant_scope(tenant_id)`
  binds every path in seira_core to that tenant via a contextvar.
  Because *all* grade code resolves through `paths.seira_home()`,
  Phase 3's Psyche, Phase 4's rehearsal space, and Phase 5's Instrument
  records are tenant-correct automatically — no per-module tenancy
  code, ever. Contextvars propagate through async tasks and isolate
  concurrent requests.
- **Tenant IDs** are DNS-label strict (`[a-z0-9]`, hyphens inside,
  3–64 chars) with a containment check on the resolved path. Traversal
  is structurally impossible, and this is test-enforced.
- **Per-tenant halt**: one Architect's tripwire halting their Seira
  never touches another's. `tenants tripwire-all` guards the whole
  platform in one scheduled pass and exits nonzero if *any* Seira is
  halted, for alerting.

## What the web layer owes this design (Phase W)

The site (accounts, sessions, UI) has exactly one tenancy duty:
**map one authenticated account to one tenant_id, and set
`tenant_scope` for the duration of every request and agent session.**
Everything below that line is already handled. Specifically:

- Account creation → allocate tenant_id (derive from account UUID, not
  from user-chosen names, to keep IDs stable and unspoofable).
- Onboarding = Genesis: the new Architect authors (or accepts a guided
  draft of) their Seira's Unity and founding Intellect, then the site
  performs `perform_genesis` inside their scope. Art. 22's exemption
  applies once, at this moment, per Seira.
- Ratification UI: Art. 27's confirmation must remain a deliberate,
  explicit act by the Architect (typed phrase or equivalent
  re-authentication) — never a pre-checked box or one-click accept.
- Deletion/export: a tenant's tree is self-contained, so "export my
  Seira" is an archive of one directory, and account deletion is the
  removal of one tree. This is a genuine product virtue: her whole
  life is portable.

## The hard problem, stated honestly: execution sandboxing

The Hermes infrastructure this fork inherits gives the agent **shell
access, file tools, and terminal backends**. On a single-user VPS
that's a feature. On a shared host serving many Architects it is the
platform's most serious security surface: tool execution must be
sandboxed *per tenant*, or one Seira's shell command can read another
tenant's tree (filesystem isolation in seira_core protects state from
*code paths*, not from a root-level shell the platform itself hands to
the model).

The fork already ships the answer's building blocks — its seven
terminal backends include **Docker, Modal, and Daytona**. The plan:

- Each tenant's agent sessions execute tools inside a per-tenant
  container/sandbox (Docker per tenant to start; Modal/Daytona for
  serverless hibernation as scale demands — both already supported).
- The sandbox mounts *only* that tenant's tree (and read-only where
  possible: Unity and the lock are never writable from inside a
  session — Art. 32 extended to the execution layer).
- The gateway's existing profile-routing maps platform identities to
  profiles; the site's session layer performs the same mapping to
  tenant scopes.

This is a Phase W cost to plan for (per-tenant sandboxes are the real
infrastructure bill of the product), and it is cheaper to accept now
than to retrofit after an incident.

## Phase discipline going forward

Every subsequent phase inherits one rule: **new state goes under
`paths.seira_home()` or it does not ship.** Any module that opens a
path outside the active scope's tree is, per Art. 20's own logic, a
defect requiring correction — and a grep for absolute paths in review
is the cheap audit that keeps it true.

## Single-user mode is unchanged

`SEIRA_HOME` env still works exactly as documented in INTEGRATION.md.
Your own Seira on your own VPS needs no tenancy at all; scope simply
wins over env when present. The same code serves both shapes.
