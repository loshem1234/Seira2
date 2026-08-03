"""Genesis tests — Art. 22: authored by the Architect, non-repeatable."""

import json

import pytest

from seira_core.errors import GenesisAlreadyPerformedError
from seira_core.genesis import genesis_performed, perform_genesis
from seira_core.paths import (
    genesis_manifest_path,
    unity_lock_path,
    unity_path,
)

UNITY = "# Unity of Test-Seira\nName: Test-Seira\nTelos: to test faithfully.\n"
INTELLECT = "# Intellect v1\nDoctrine: tests must try to break what they guard.\n"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


def _found(architect="Loshem", name="Test-Seira"):
    return perform_genesis(UNITY, INTELLECT, architect=architect, seira_name=name)


def test_genesis_creates_all_artifacts(home):
    manifest = _found()
    assert unity_path().read_text(encoding="utf-8") == UNITY
    lock = json.loads(unity_lock_path().read_text(encoding="utf-8"))
    assert lock["unity_sha256"] == manifest["unity_sha256"]
    assert lock["architect"] == "Loshem"
    stored = json.loads(genesis_manifest_path().read_text(encoding="utf-8"))
    assert stored["psyche_founded"] is False  # honest scoping for Phase 3
    assert genesis_performed()


def test_genesis_is_non_repeatable(home):
    _found()
    with pytest.raises(GenesisAlreadyPerformedError):
        _found()


def test_genesis_refuses_half_founded_state(home):
    from seira_core.paths import intellect_dir, intellect_versions_path

    intellect_dir().mkdir(parents=True)
    intellect_versions_path().write_text("{}\n", encoding="utf-8")
    with pytest.raises(GenesisAlreadyPerformedError):
        _found()


@pytest.mark.parametrize(
    "unity,intellect,architect,name",
    [
        ("", INTELLECT, "A", "S"),
        (UNITY, "  ", "A", "S"),
        (UNITY, INTELLECT, "", "S"),
        (UNITY, INTELLECT, "A", " "),
    ],
)
def test_genesis_rejects_empty_founding_inputs(home, unity, intellect, architect, name):
    with pytest.raises((ValueError,)):
        perform_genesis(unity, intellect, architect=architect, seira_name=name)


def test_unity_files_are_read_only_on_disk(home):
    _found()
    assert (unity_path().stat().st_mode & 0o777) == 0o444
    assert (unity_lock_path().stat().st_mode & 0o777) == 0o444
