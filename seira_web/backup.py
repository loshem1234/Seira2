"""seira_web.backup — daily and monthly snapshots, for rollback from
drift, defect, or deviation, not (by itself) disaster recovery.

Two tiers, matching what was asked for:
  daily   — every 24h, last 7 kept
  monthly — every 30 days, last 12 kept (a year)

Written to the SAME persistent volume as the live data by default —
this protects against a bad ratification, a corrupted write, or
unwanted drift (roll back to yesterday's or last month's snapshot).
It does NOT by itself protect against losing the volume entirely; true
disaster recovery means shipping these off-box (R2 is the natural fit,
already in the Architect's stack) — the shape for that is a single
clearly-marked hook (`_ship_offsite`), not built by default, so this
system is honest about what it actually guarantees today.

Each backup is a single tar.gz of everything under SEIRA_TENANTS_ROOT
and SEIRA_PLATFORM_ROOT — every tenant's full state (Unity through
Diary, references, generated images, outputs) plus the account store,
in one archive per snapshot. Simple and complete beats clever and
partial for something whose entire job is "still be there when
something has gone wrong."
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional

DAILY_RETENTION = int(os.environ.get("SEIRA_BACKUP_DAILY_RETENTION", "7"))
MONTHLY_RETENTION = int(os.environ.get("SEIRA_BACKUP_MONTHLY_RETENTION", "12"))
DAILY_INTERVAL_SECONDS = 24 * 3600
MONTHLY_INTERVAL_SECONDS = 30 * 24 * 3600


def backup_root() -> Path:
    env = os.environ.get("SEIRA_BACKUP_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".seira-backups"


def _tenants_root() -> Optional[Path]:
    from seira_core.tenancy import tenants_root
    p = tenants_root()
    return p if p.exists() else None


def _platform_root() -> Optional[Path]:
    from seira_web.accounts import platform_root
    p = platform_root()
    return p if p.exists() else None


def _kind_dir(kind: str) -> Path:
    if kind not in ("daily", "monthly"):
        raise ValueError("kind must be 'daily' or 'monthly'.")
    return backup_root() / kind


def _marker_path(kind: str) -> Path:
    return _kind_dir(kind) / "_last_run.json"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def is_due(kind: str) -> bool:
    marker = _marker_path(kind)
    if not marker.exists():
        return True
    last = _dt.datetime.fromisoformat(json.loads(marker.read_text())["ts"])
    interval = DAILY_INTERVAL_SECONDS if kind == "daily" else MONTHLY_INTERVAL_SECONDS
    return (_now() - last).total_seconds() >= interval


def create_backup(kind: str) -> Dict[str, Any]:
    """Create one archive right now, unconditionally (does not check
    is_due — callers that want the daily/monthly schedule use
    run_if_due(); this is also useful for a manual, on-demand backup
    before something risky, like a Dispensation or a large ratification)."""
    _kind_dir(kind).mkdir(parents=True, exist_ok=True)
    ts = _now().strftime("%Y%m%dT%H%M%S.%fZ")
    archive_path = _kind_dir(kind) / f"seira-backup-{kind}-{ts}.tar.gz"

    roots: List[tuple[str, Path]] = []
    tr = _tenants_root()
    if tr is not None:
        roots.append(("tenants", tr))
    pr = _platform_root()
    if pr is not None:
        roots.append(("platform", pr))
    if not roots:
        raise RuntimeError(
            "Nothing to back up: neither the tenants root nor the "
            "platform root exists yet."
        )

    with tarfile.open(archive_path, "w:gz") as tar:
        for label, root in roots:
            tar.add(root, arcname=label)

    _marker_path(kind).write_text(
        json.dumps({"ts": _now().isoformat(), "archive": archive_path.name},
                  indent=2), encoding="utf-8"
    )
    result = {
        "kind": kind, "path": str(archive_path),
        "size_bytes": archive_path.stat().st_size, "ts": _now().isoformat(),
    }
    prune_backups(kind)

    # R2 shipping is additive: the local backup has already succeeded
    # and been recorded above by this point. A network/credential
    # failure here must not make create_backup() look like it failed —
    # the caller (the background loop) logs this, it doesn't raise.
    from seira_web.r2 import r2_configured, ship, R2Error
    if r2_configured():
        try:
            ship_result = ship(archive_path, kind)
            result["r2"] = {"shipped": True, **ship_result}
        except R2Error as e:
            result["r2"] = {"shipped": False, "error": str(e)}
    else:
        result["r2"] = {"shipped": False, "reason": "not configured"}

    return result


def run_if_due(kind: str) -> Optional[Dict[str, Any]]:
    """Called from the background loop each tick; only actually creates
    a backup when the interval has genuinely elapsed."""
    if not is_due(kind):
        return None
    return create_backup(kind)


def list_backups(kind: str) -> List[Dict[str, Any]]:
    d = _kind_dir(kind)
    if not d.exists():
        return []
    out = []
    # Sorted by filename, not filesystem mtime: the filename encodes
    # microsecond-precision creation order directly, so this is correct
    # even when a filesystem's mtime resolution is coarser than the rate
    # backups are actually created at (matters for rapid manual/on-demand
    # backups; the normal daily/monthly schedule never hits this).
    for f in sorted(d.glob("seira-backup-*.tar.gz"), reverse=True):
        out.append({"path": str(f), "name": f.name,
                   "size_bytes": f.stat().st_size,
                   "mtime": _dt.datetime.fromtimestamp(
                       f.stat().st_mtime, tz=_dt.timezone.utc).isoformat()})
    return out


def prune_backups(kind: str) -> List[str]:
    retention = DAILY_RETENTION if kind == "daily" else MONTHLY_RETENTION
    backups = list_backups(kind)  # newest first
    removed = []
    for old in backups[retention:]:
        Path(old["path"]).unlink(missing_ok=True)
        removed.append(old["name"])
    return removed


def restore_backup(archive_path: str, target_root: Optional[str] = None) -> Dict[str, Any]:
    """Extract an archive back onto disk. Deliberately NOT wired to any
    UI button — restoring is a rare, high-stakes, deliberate Architect
    act (same discipline as ratification), run by hand:

        python -c "from seira_web.backup import restore_backup; \\
                   restore_backup('/path/to/seira-backup-daily-....tar.gz')"

    Refuses to silently overwrite an existing tenants/platform root at
    the destination — extracts into a clearly-named sibling directory
    instead, so the Architect reviews and swaps in the restored data
    deliberately rather than this function doing it for them.
    """
    src = Path(archive_path)
    if not src.exists():
        raise FileNotFoundError(f"No archive at {archive_path}.")
    dest = Path(target_root) if target_root else backup_root() / "restored" / src.stem
    if dest.exists() and any(dest.iterdir()):
        raise RuntimeError(
            f"{dest} already exists and is not empty; refusing to overwrite. "
            "Remove it or choose a different target_root."
        )
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(dest, filter="data")
    return {"restored_to": str(dest), "archive": str(src)}
