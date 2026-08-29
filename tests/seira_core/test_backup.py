"""Backup tests — daily/monthly creation, retention pruning, the
due-checking that makes the background loop idempotent, and restore."""

import tarfile
import time
from pathlib import Path

import pytest

from seira_web import backup


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_BACKUP_ROOT", str(tmp_path / "backups"))
    (tmp_path / "tenants" / "loshem").mkdir(parents=True)
    (tmp_path / "tenants" / "loshem" / "unity.txt").write_text("her unity")
    (tmp_path / "platform").mkdir(parents=True)
    (tmp_path / "platform" / "accounts.json").write_text("{}")
    return tmp_path


def test_create_backup_contains_real_data(env):
    rec = backup.create_backup("daily")
    path = Path(rec["path"])
    assert path.exists() and path.stat().st_size > 0
    with tarfile.open(path, "r:gz") as tar:
        names = tar.getnames()
    assert any("unity.txt" in n for n in names)
    assert any("accounts.json" in n for n in names)


def test_is_due_true_before_first_backup_false_immediately_after(env):
    assert backup.is_due("daily") is True
    backup.create_backup("daily")
    assert backup.is_due("daily") is False


def test_run_if_due_is_idempotent(env):
    r1 = backup.run_if_due("daily")
    assert r1 is not None
    r2 = backup.run_if_due("daily")
    assert r2 is None  # not due again immediately
    assert len(backup.list_backups("daily")) == 1  # no duplicate created


def test_retention_prunes_oldest_first(env, monkeypatch):
    monkeypatch.setenv("SEIRA_BACKUP_DAILY_RETENTION", "3")
    import importlib
    importlib.reload(backup)
    created_paths = []
    for i in range(5):
        rec = backup.create_backup("daily")
        created_paths.append(rec["path"])
        time.sleep(0.01)
    remaining = backup.list_backups("daily")
    assert len(remaining) == 3  # pruned down to retention limit
    remaining_paths = {r["path"] for r in remaining}
    # The 3 most recently created must be the ones kept; the 2 oldest gone.
    assert remaining_paths == set(created_paths[-3:])
    for old_path in created_paths[:2]:
        assert not Path(old_path).exists()
    importlib.reload(backup)  # restore default retention for other tests


def test_monthly_and_daily_are_independent(env):
    backup.create_backup("daily")
    assert len(backup.list_backups("daily")) == 1
    assert len(backup.list_backups("monthly")) == 0
    backup.create_backup("monthly")
    assert len(backup.list_backups("monthly")) == 1
    assert len(backup.list_backups("daily")) == 1  # untouched


def test_restore_extracts_real_content(env):
    rec = backup.create_backup("daily")
    result = backup.restore_backup(rec["path"])
    restored_dir = Path(result["restored_to"])
    found = list(restored_dir.rglob("unity.txt"))
    assert found and found[0].read_text() == "her unity"


def test_restore_refuses_to_overwrite_nonempty_target(env, tmp_path):
    rec = backup.create_backup("daily")
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "existing.txt").write_text("don't touch me")
    with pytest.raises(RuntimeError, match="not empty"):
        backup.restore_backup(rec["path"], target_root=str(target))


def test_backup_with_no_data_raises_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "nope-tenants"))
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "nope-platform"))
    monkeypatch.setenv("SEIRA_BACKUP_ROOT", str(tmp_path / "backups"))
    with pytest.raises(RuntimeError, match="Nothing to back up"):
        backup.create_backup("daily")


def test_background_tick_runs_backup_check_without_raising(env):
    from seira_web.tripwire_loop import _backup_tick
    _backup_tick()  # must not raise
    assert len(backup.list_backups("daily")) == 1


def test_healthz_reports_backup_status(env):
    import sys
    from pathlib import Path as P
    for c in [P(__file__).resolve().parents[2], P("/home/claude/repo/hermes-agent-main")]:
        if (c / "agent" / "memory_provider.py").exists():
            sys.path.insert(0, str(c))
            break
    pytest.importorskip("agent.memory_provider")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from seira_web.app import create_app

    backup.create_backup("daily")
    app = create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app)
    r = c.get("/healthz")
    body = r.json()
    assert body["backups"]["daily"]["count"] == 1
    assert body["backups"]["monthly"]["count"] == 0
