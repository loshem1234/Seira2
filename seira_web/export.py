"""seira_web.export — an Architect exports exactly their own tenant,
nothing else, ever.

The design note from Phase W1's own docs finally built: "a tenant's
tree is self-contained, so 'export my Seira' is an archive of one
directory." This is that archive — for migration to a single-tenant,
full-Hermes deployment, or simply as a personal copy independent of
Railway.

Deliberately narrower than backup.py: backup.py archives every
tenant together, for the platform's own disaster-recovery purposes.
This archives ONE tenant's directory alone, because an export is
initiated BY that Architect, FOR that Architect, and must not be able
to leak so much as the existence of any other tenant's data — the
tar is built directly from `tenant_root(tenant_id)`, never from
`tenants_root()`, so there is no code path here that could reach
another tenant's files even by mistake.
"""

from __future__ import annotations

import datetime as _dt
import tarfile
from pathlib import Path
from typing import Any, Dict


class ExportError(Exception):
    pass


def export_tenant(tenant_id: str, dest_dir: Path) -> Dict[str, Any]:
    """Tar exactly one tenant's directory. Refuses if that tenant has
    no data at all (nothing founded yet) — an empty archive would be
    a false promise of a backup that isn't there."""
    from seira_core.tenancy import tenant_root

    src = tenant_root(tenant_id)  # raises TenantError for a malformed id
    if not src.exists() or not any(src.iterdir()):
        raise ExportError(
            f"Tenant {tenant_id!r} has no data yet — nothing to export."
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive_path = dest_dir / f"seira-export-{tenant_id}-{ts}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as tar:
        # arcname is the tenant_id itself, so extracting the archive
        # produces a folder named after the tenant, not an ambiguous
        # top-level dump — makes the later "adopt this as SEIRA_HOME"
        # step unambiguous about what's inside.
        tar.add(src, arcname=tenant_id)

    return {
        "tenant_id": tenant_id, "path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
    }
