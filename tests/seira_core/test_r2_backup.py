"""R2 shipping tests. A fake client is used everywhere — no real
network call, no real Cloudflare account, ever touched by this suite.
"""

from pathlib import Path

import pytest

from seira_web import backup, r2


class FakeR2Client:
    """An in-memory stand-in implementing exactly the R2Client protocol,
    so tests exercise the real upload/list/delete call shapes without
    any network."""

    def __init__(self):
        self.objects = {}  # key -> {size, local_path}
        self.upload_calls = []
        self.delete_calls = []

    def upload(self, local_path: Path, key: str) -> None:
        self.upload_calls.append((str(local_path), key))
        self.objects[key] = {"size": local_path.stat().st_size,
                             "local_path": str(local_path)}

    def list_keys(self, prefix):
        return [{"key": k, "size": v["size"], "last_modified": "2026-01-01T00:00:00"}
                for k, v in self.objects.items() if k.startswith(prefix)]

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.objects.pop(key, None)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_BACKUP_ROOT", str(tmp_path / "backups"))
    (tmp_path / "tenants" / "loshem").mkdir(parents=True)
    (tmp_path / "tenants" / "loshem" / "unity.txt").write_text("her unity")
    (tmp_path / "platform").mkdir(parents=True)
    return tmp_path


def test_r2_not_configured_by_default(env, monkeypatch):
    for var in ("SEIRA_R2_ACCOUNT_ID", "SEIRA_R2_ACCESS_KEY_ID",
               "SEIRA_R2_SECRET_ACCESS_KEY", "SEIRA_R2_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    assert r2.r2_configured() is False


def test_r2_configured_requires_all_four_vars(env, monkeypatch):
    monkeypatch.setenv("SEIRA_R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("SEIRA_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SEIRA_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("SEIRA_R2_BUCKET", raising=False)
    assert r2.r2_configured() is False
    monkeypatch.setenv("SEIRA_R2_BUCKET", "my-bucket")
    assert r2.r2_configured() is True


def test_ship_uploads_the_real_archive(env):
    rec = backup.create_backup("daily")
    fake = FakeR2Client()
    result = r2.ship(Path(rec["path"]), "daily", client=fake)
    assert len(fake.upload_calls) == 1
    local_path, key = fake.upload_calls[0]
    assert local_path == rec["path"]
    assert key == f"seira-backups/daily/{Path(rec['path']).name}"
    assert result["uploaded_key"] == key


def test_remote_retention_prunes_oldest_first(env, monkeypatch):
    monkeypatch.setenv("SEIRA_BACKUP_DAILY_RETENTION", "2")
    import importlib
    importlib.reload(backup)
    fake = FakeR2Client()
    paths = []
    for i in range(4):
        rec = backup.create_backup("daily")
        paths.append(Path(rec["path"]))
        r2.ship(Path(rec["path"]), "daily", client=fake)
    remaining_keys = set(fake.objects.keys())
    assert len(remaining_keys) == 2
    # the two most recently created must be the ones remaining
    expected_keys = {f"seira-backups/daily/{p.name}" for p in paths[-2:]}
    assert remaining_keys == expected_keys
    importlib.reload(backup)


def test_local_backup_succeeds_even_if_r2_ships_fails(env, monkeypatch):
    """The core guarantee: a network/credential failure in R2 must never
    make create_backup() look like it failed — local safety comes first."""
    monkeypatch.setenv("SEIRA_R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("SEIRA_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SEIRA_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SEIRA_R2_BUCKET", "bucket")

    class BrokenClient:
        def upload(self, *a, **k):
            raise r2.R2Error("simulated network failure")

    import seira_web.r2 as r2_mod
    monkeypatch.setattr(r2_mod, "BotoR2Client", lambda: BrokenClient())

    rec = backup.create_backup("daily")  # must not raise
    assert Path(rec["path"]).exists()  # local backup genuinely succeeded
    assert rec["r2"]["shipped"] is False
    assert "simulated network failure" in rec["r2"]["error"]


def test_unconfigured_r2_is_reported_honestly_not_silently(env, monkeypatch):
    for var in ("SEIRA_R2_ACCOUNT_ID", "SEIRA_R2_ACCESS_KEY_ID",
               "SEIRA_R2_SECRET_ACCESS_KEY", "SEIRA_R2_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    rec = backup.create_backup("daily")
    assert rec["r2"] == {"shipped": False, "reason": "not configured"}


def test_boto_client_refuses_cleanly_without_full_config(env, monkeypatch):
    monkeypatch.delenv("SEIRA_R2_BUCKET", raising=False)
    with pytest.raises(r2.R2Error, match="not fully configured"):
        r2.BotoR2Client(account_id="a", access_key_id="b", secret_access_key="c")


def test_background_tick_ships_when_configured(env, monkeypatch):
    monkeypatch.setenv("SEIRA_R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("SEIRA_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SEIRA_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SEIRA_R2_BUCKET", "bucket")

    fake = FakeR2Client()
    import seira_web.r2 as r2_mod
    monkeypatch.setattr(r2_mod, "BotoR2Client", lambda: fake)

    from seira_web.tripwire_loop import _backup_tick
    _backup_tick()  # must not raise
    # Both daily and monthly are due on a first run — both correctly ship.
    assert len(fake.upload_calls) == 2
    shipped_kinds = {key.split("/")[1] for _, key in fake.upload_calls}
    assert shipped_kinds == {"daily", "monthly"}


def test_healthz_reports_r2_configured_status(env, monkeypatch):
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

    for var in ("SEIRA_R2_ACCOUNT_ID", "SEIRA_R2_ACCESS_KEY_ID",
               "SEIRA_R2_SECRET_ACCESS_KEY", "SEIRA_R2_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    app = create_app(llm_client_factory=lambda model=None: None)
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.json()["backups"]["r2_configured"] is False
