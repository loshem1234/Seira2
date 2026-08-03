"""seira_core command-line interface.

    python -m seira_core genesis --unity-file U.md --intellect-file I.md \\
        --architect "Name" --name "Seira"
    python -m seira_core status
    python -m seira_core tripwire
    python -m seira_core intellect show
    python -m seira_core intellect history
    python -m seira_core intellect ratify --file NEW.md --kind expansion \\
        --proposal-ref "proposal-2026-08-02-a"
    python -m seira_core intellect restore --version 2 --reason "..."
    python -m seira_core render-soul [--write PATH]

Ratification and restoration prompt interactively for the Architect's
confirmation phrase (Art. 27); it is never accepted from a flag, so it
cannot end up in shell history or a script by accident.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from seira_core.errors import SeiraCoreError
from seira_core.genesis import genesis_performed, perform_genesis
from seira_core.intellect import ARCHITECT_RATIFICATION_PHRASE, IntellectStore
from seira_core.paths import halt_path, seira_home
from seira_core.tripwire import is_halted, run_tripwire


def _read_file(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def _confirm_architect() -> str:
    print("Ratification requires the Architect's confirmation (Art. 27).")
    print(f'Type exactly: {ARCHITECT_RATIFICATION_PHRASE}')
    return input("> ").strip()


def _cmd_genesis(args: argparse.Namespace) -> int:
    manifest = perform_genesis(
        unity_content=_read_file(args.unity_file),
        intellect_content=_read_file(args.intellect_file),
        architect=args.architect,
        seira_name=args.name,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nGenesis complete under {seira_home()}.")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    print(f"SEIRA_HOME: {seira_home()}")
    print(f"Founded:    {genesis_performed()}")
    print(f"Halted:     {is_halted()}" + (f"  ({halt_path()})" if is_halted() else ""))
    if genesis_performed() and not is_halted():
        store = IntellectStore()
        try:
            cur = store.current()
            print(f"Intellect:  v{cur['version']} ({cur['kind']}, {cur['created_at']})")
        except SeiraCoreError as e:
            print(f"Intellect:  ERROR — {e}")
            return 2
    return 0


def _cmd_tripwire(args: argparse.Namespace) -> int:
    result = run_tripwire()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if result["halted"] else 0


def _cmd_intellect(args: argparse.Namespace) -> int:
    store = IntellectStore()
    if args.intellect_cmd == "show":
        cur = store.current()
        print(f"# Intellect v{cur['version']} ({cur['kind']}, {cur['created_at']})\n")
        print(cur["content"])
        return 0
    if args.intellect_cmd == "history":
        for rec in store.history():
            mark = "  (superseded)" if rec["superseded"] else "  (CURRENT)"
            extra = ""
            if rec.get("restores_version"):
                extra = f" restores v{rec['restores_version']}"
            print(
                f"v{rec['version']:>3}  {rec['kind']:<11} {rec['created_at']}"
                f"{extra}{mark}"
            )
        return 0
    if args.intellect_cmd == "ratify":
        confirmation = _confirm_architect()
        rec = store.ratify(
            content=_read_file(args.file),
            kind=args.kind,
            proposal_ref=args.proposal_ref,
            architect_confirmation=confirmation,
            contradicted_ref=args.contradicted_ref,
        )
        print(f"Ratified as Intellect v{rec['version']} ({rec['kind']}).")
        return 0
    if args.intellect_cmd == "restore":
        confirmation = _confirm_architect()
        rec = store.restore(
            restore_version=args.version,
            architect_confirmation=confirmation,
            reason=args.reason,
        )
        print(
            f"Restored v{args.version} as new version v{rec['version']} (Art. 28)."
        )
        return 0
    raise SystemExit(2)


def _cmd_psyche(args: argparse.Namespace) -> int:
    from seira_core.psyche import PsycheStore

    store = PsycheStore()
    if args.psyche_cmd == "found":
        from seira_core.genesis import perform_psyche_genesis
        entries = json.loads(_read_file(args.file))
        manifest = perform_psyche_genesis(entries, architect=args.architect)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0
    if args.psyche_cmd == "show":
        state = store.state()
        live = [e for e in state["entries"].values() if e["standing"] != "retired"]
        print(f"Psyche founded: {state['founded']}  "
              f"({len(live)} live / {len(state['entries'])} total entries, "
              f"{state['event_count']} events)")
        for e in sorted(live, key=lambda x: x["entry_id"]):
            w = f" w={e['weight']}" if "weight" in e else ""
            print(f"  {e['entry_id']} [{e['category']}, {e['standing']}{w}] {e['content']}")
        return 0
    if args.psyche_cmd == "add":
        rec = store.add_entry(
            category=args.category, content=args.content,
            cause={"type": args.cause_type, "ref": args.cause_ref},
            provenance=args.provenance, weight=args.weight,
        )
        print(f"Added {rec['entry_id']} (provisional).")
        return 0
    if args.psyche_cmd == "standing":
        store.change_standing(
            args.id, to=args.to, basis_ref=args.basis_ref,
            falsification_ref=args.falsification_ref,
            contradicts_ref=args.contradicts_ref,
        )
        print(f"{args.id} standing -> {args.to}.")
        return 0
    if args.psyche_cmd == "engage":
        rec = store.engage_affinity(args.id, args.delta, args.evidence_ref)
        print(f"{args.id} weight -> {rec['weight']}.")
        return 0
    if args.psyche_cmd == "retire":
        store.retire_entry(args.id, args.reason)
        print(f"{args.id} retired (history preserved).")
        return 0
    raise SystemExit(2)


def _cmd_proposal(args: argparse.Namespace) -> int:
    from seira_core.reversion import ReversionStore

    store = ReversionStore()
    c = args.proposal_cmd
    if c == "open":
        rec = store.open_proposal(
            target=args.target, kind=args.kind, content=args.content,
            origin={"type": args.origin_type, "ref": args.origin_ref},
            evidence_refs=args.evidence,
            contradicted_ref=args.contradicted_ref, entry_id=args.entry_id,
        )
        print(f"Opened {rec['proposal_id']} ({args.kind} -> {args.target}).")
        return 0
    if c == "attempt":
        rec = store.record_attempt(args.id, args.method, args.corpus_refs,
                                   args.outcome, args.notes)
        print(f"Attempt recorded on {args.id}: {args.outcome}.")
        return 0
    if c == "consistency":
        rec = store.record_consistency_check(args.id, args.result, args.notes)
        print(f"Consistency check on {args.id}: {args.result} "
              f"(Intellect v{rec['intellect_version']}).")
        return 0
    if c == "promote":
        p = store.proposal(args.id)
        if p["target"] == "psyche_standing":
            store.promote_psyche(args.id, basis_ref=args.basis_ref or args.id)
            print(f"{args.id} promoted: {p['entry_id']} is now established.")
        else:
            confirmation = _confirm_architect()
            rec = store.promote_intellect(args.id, architect_confirmation=confirmation)
            print(f"{args.id} promoted into Intellect v{rec['detail']['intellect_version']}.")
        return 0
    if c == "reject":
        store.reject(args.id); print(f"{args.id} rejected."); return 0
    if c == "suspend":
        store.suspend_pair(args.id, args.rival)
        print(f"{args.id} and {args.rival} suspended as a contradiction pair.")
        return 0
    if c == "stale":
        store.mark_stale(args.id); print(f"{args.id} marked stale."); return 0
    if c == "withdraw":
        store.withdraw(args.id, args.reason); print(f"{args.id} withdrawn."); return 0
    if c == "show":
        print(json.dumps(store.proposal(args.id), indent=2, ensure_ascii=False)); return 0
    if c == "list":
        for p in store.list_proposals(status=args.status):
            print(f"{p['proposal_id']}  {p['status']:<10} {p['kind']:<13} -> {p['target']}  "
                  f"attempts={len(p['attempts'])}")
        return 0
    raise SystemExit(2)


def _cmd_dispensation(args: argparse.Namespace) -> int:
    from seira_core.reversion import ReversionStore

    store = ReversionStore()
    if args.disp_cmd == "invoke":
        rec = store.invoke_dispensation(args.action, args.conditions_ref, args.evidence)
        print(f"{rec['dispensation_id']} invoked; mandatory retroactive proposal "
              f"{rec['retroactive_proposal_id']} opened (Art. 31).")
        return 0
    if args.disp_cmd == "close":
        store.close_dispensation(args.id)
        print(f"{args.id} closed.")
        return 0
    raise SystemExit(2)


def _cmd_health(args: argparse.Namespace) -> int:
    from seira_core.reversion import ReversionStore

    print(json.dumps(ReversionStore().health(), indent=2, ensure_ascii=False))
    return 0


def _cmd_tenants(args: argparse.Namespace) -> int:
    from seira_core.tenancy import list_tenants, tripwire_all

    if args.tenants_cmd == "list":
        for tid in list_tenants():
            print(tid)
        return 0
    if args.tenants_cmd == "tripwire-all":
        results = tripwire_all()
        halted = {t: r for t, r in results.items() if r["halted"]}
        for tid, r in results.items():
            print(f"{tid}: {'HALTED' if r['halted'] else 'ok'}")
        return 2 if halted else 0
    raise SystemExit(2)


def _cmd_render_soul(args: argparse.Namespace) -> int:
    from seira_core.prompt_block import render_identity_block, sync_soul

    if args.write:
        sync_soul(args.write)
        print(f"Wrote rendered identity to {args.write}")
    else:
        print(render_identity_block())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seira_core", description=__doc__)
    p.add_argument("--tenant", default=None,
                   help="Operate on this tenant's Seira (multi-tenant deployments)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("genesis", help="Found a new Seira (one-time; Art. 22)")
    g.add_argument("--unity-file", required=True)
    g.add_argument("--intellect-file", required=True)
    g.add_argument("--architect", required=True)
    g.add_argument("--name", required=True)
    g.set_defaults(func=_cmd_genesis)

    s = sub.add_parser("status", help="Founding, halt, and Intellect status")
    s.set_defaults(func=_cmd_status)

    t = sub.add_parser("tripwire", help="Run the integrity tripwire (Art. 32.3)")
    t.set_defaults(func=_cmd_tripwire)

    i = sub.add_parser("intellect", help="Intellect operations")
    isub = i.add_subparsers(dest="intellect_cmd", required=True)
    isub.add_parser("show", help="Print the current Intellect version")
    isub.add_parser("history", help="List all versions")
    r = isub.add_parser("ratify", help="Ratify a correction or expansion (Art. 24–27)")
    r.add_argument("--file", required=True, help="File with the full new Intellect content")
    r.add_argument("--kind", required=True, choices=["correction", "expansion"])
    r.add_argument("--proposal-ref", required=True)
    r.add_argument("--contradicted-ref", default=None,
                   help="Required for corrections (Art. 24)")
    rs = isub.add_parser("restore", help="Restore a prior version as a new one (Art. 28)")
    rs.add_argument("--version", type=int, required=True)
    rs.add_argument("--reason", required=True)
    i.set_defaults(func=_cmd_intellect)

    ps = sub.add_parser("psyche", help="Psyche (Grade 3) operations")
    pssub = ps.add_subparsers(dest="psyche_cmd", required=True)
    pf = pssub.add_parser("found", help="Found Psyche as a Genesis extension (Art. 22)")
    pf.add_argument("--file", required=True,
                    help="JSON file: list of {category, content[, weight]} entries")
    pf.add_argument("--architect", required=True)
    pssub.add_parser("show", help="Current Psyche state")
    pa = pssub.add_parser("add", help="Add a provisional entry")
    pa.add_argument("--category", required=True)
    pa.add_argument("--content", required=True)
    pa.add_argument("--cause-type", required=True)
    pa.add_argument("--cause-ref", required=True)
    pa.add_argument("--provenance", required=True, nargs="+")
    pa.add_argument("--weight", type=float, default=None)
    pst = pssub.add_parser("standing", help="Change an entry's standing")
    pst.add_argument("--id", required=True)
    pst.add_argument("--to", required=True, choices=["provisional", "established", "suspended"])
    pst.add_argument("--basis-ref", required=True)
    pst.add_argument("--falsification-ref", default=None)
    pst.add_argument("--contradicts-ref", default=None)
    pe = pssub.add_parser("engage", help="Move an affinity weight by evidence")
    pe.add_argument("--id", required=True)
    pe.add_argument("--delta", type=float, required=True)
    pe.add_argument("--evidence-ref", required=True)
    pr = pssub.add_parser("retire", help="Retire an entry (never deleted)")
    pr.add_argument("--id", required=True)
    pr.add_argument("--reason", required=True)
    ps.set_defaults(func=_cmd_psyche)

    pr2 = sub.add_parser("proposal", help="Reversion proposals (Art. 24-25)")
    prsub = pr2.add_subparsers(dest="proposal_cmd", required=True)
    po = prsub.add_parser("open", help="Open a proposal")
    po.add_argument("--target", required=True, choices=["intellect", "psyche_standing"])
    po.add_argument("--kind", required=True, choices=["correction", "expansion", "establishment"])
    po.add_argument("--content", required=True)
    po.add_argument("--origin-type", required=True,
                    choices=["reversion", "instrument_escalation", "self_audit", "architect"])
    po.add_argument("--origin-ref", required=True)
    po.add_argument("--evidence", required=True, nargs="+")
    po.add_argument("--contradicted-ref", default=None)
    po.add_argument("--entry-id", default=None)
    pat = prsub.add_parser("attempt", help="Record a falsification attempt (Art. 25.2, 39)")
    pat.add_argument("--id", required=True)
    pat.add_argument("--method", required=True)
    pat.add_argument("--corpus-refs", required=True, nargs="+")
    pat.add_argument("--outcome", required=True, choices=["survived", "failed"])
    pat.add_argument("--notes", default="")
    pc = prsub.add_parser("consistency", help="Record an Intellect consistency check (Art. 25.3)")
    pc.add_argument("--id", required=True)
    pc.add_argument("--result", required=True, choices=["consistent", "inconsistent"])
    pc.add_argument("--notes", default="")
    pp = prsub.add_parser("promote", help="Promote a cleared proposal")
    pp.add_argument("--id", required=True)
    pp.add_argument("--basis-ref", default=None, help="psyche_standing target")
    prj = prsub.add_parser("reject", help="Reject after a failed attempt")
    prj.add_argument("--id", required=True)
    psu = prsub.add_parser("suspend", help="Suspend two live survivors as a contradiction pair")
    psu.add_argument("--id", required=True)
    psu.add_argument("--rival", required=True)
    pstale = prsub.add_parser("stale", help="Mark an expansion stale")
    pstale.add_argument("--id", required=True)
    pw = prsub.add_parser("withdraw", help="Withdraw voluntarily")
    pw.add_argument("--id", required=True)
    pw.add_argument("--reason", required=True)
    psh = prsub.add_parser("show", help="Show one proposal")
    psh.add_argument("--id", required=True)
    pls = prsub.add_parser("list", help="List proposals")
    pls.add_argument("--status", default=None)
    pr2.set_defaults(func=_cmd_proposal)

    dp = sub.add_parser("dispensation", help="Dispensations (Art. 30-31)")
    dpsub = dp.add_subparsers(dest="disp_cmd", required=True)
    di = dpsub.add_parser("invoke")
    di.add_argument("--action", required=True)
    di.add_argument("--conditions-ref", required=True)
    di.add_argument("--evidence", nargs="+", default=[])
    dc = dpsub.add_parser("close")
    dc.add_argument("--id", required=True)
    dp.set_defaults(func=_cmd_dispensation)

    hl = sub.add_parser("health", help="Health indicators (Art. 44)")
    hl.set_defaults(func=_cmd_health)

    tn = sub.add_parser("tenants", help="Multi-tenant operations")
    tnsub = tn.add_subparsers(dest="tenants_cmd", required=True)
    tnsub.add_parser("list", help="List founded tenants")
    tnsub.add_parser("tripwire-all", help="Run the tripwire for every tenant")
    tn.set_defaults(func=_cmd_tenants)

    rsoul = sub.add_parser("render-soul", help="Render identity block from Unity+Intellect")
    rsoul.add_argument("--write", default=None, help="Write to this path (e.g. SOUL.md)")
    rsoul.set_defaults(func=_cmd_render_soul)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if getattr(args, "tenant", None):
            from seira_core.tenancy import tenant_scope
            with tenant_scope(args.tenant):
                return args.func(args)
        return args.func(args)
    except SeiraCoreError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Output was piped to a consumer that closed early (e.g. `| head`).
        # Not an error condition; exit quietly per Unix convention.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
