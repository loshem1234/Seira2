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
