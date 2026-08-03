"""Unity + tripwire tests — Art. 32: all three enforcement measures."""

import json
import os
from pathlib import Path

import pytest

from seira_core.errors import SeiraHaltedError, UnityIntegrityError
from seira_core.genesis import perform_genesis
from seira_core.paths import audit_log_path, halt_path, unity_lock_path, unity_path
from seira_core.tripwire import assert_not_halted, is_halted, run_tripwire
from seira_core.unity import read_unity, verify_unity

UNITY = "# Unity\nName: Test-Seira\nTelos: testing.\n"
INTELLECT = "# Intellect v1\nDoctrine text.\n"


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis(UNITY, INTELLECT, architect="Loshem", seira_name="Test-Seira")
    return tmp_path / "seira"


def _tamper_unity(new_text: str):
    os.chmod(unity_path(), 0o644)
    unity_path().write_text(new_text, encoding="utf-8")


def test_healthy_tripwire_passes_and_logs_heartbeat(founded):
    result = run_tripwire()
    assert result["halted"] is False
    assert result["checks"]["unity"] == "ok"
    events = [json.loads(l) for l in audit_log_path().read_text().splitlines()]
    assert events[-1]["event"] == "tripwire_ok"
    assert events[-1]["learning"] is False  # routine, not learning (Art. 43)


def test_tampered_unity_trips_and_halts(founded):
    _tamper_unity(UNITY + "\nInjected stance on an object-level question.\n")
    result = run_tripwire()
    assert result["halted"] is True
    assert "UNITY TRIPWIRE" in result["reason"]
    assert is_halted()
    # Runtime entry points must now refuse (Art. 32.3).
    with pytest.raises(SeiraHaltedError):
        assert_not_halted()
    # And the halt is not routine: it is its own audit event type.
    events = [json.loads(l) for l in audit_log_path().read_text().splitlines()]
    assert events[-1]["event"] == "tripwire_halt"


def test_read_unity_verifies_before_returning(founded):
    assert read_unity() == UNITY
    _tamper_unity("impostor content")
    with pytest.raises(UnityIntegrityError):
        read_unity()  # tampered Unity is never handed out as Unity


def test_deleted_lock_is_an_integrity_violation(founded):
    os.chmod(unity_lock_path(), 0o644)
    unity_lock_path().unlink()
    with pytest.raises(UnityIntegrityError):
        verify_unity()
    assert run_tripwire()["halted"] is True


def test_halt_is_not_auto_cleared(founded):
    _tamper_unity("bad")
    assert run_tripwire()["halted"] is True
    # Architect repairs content but has not cleared the halt:
    os.chmod(unity_path(), 0o644)
    unity_path().write_text(UNITY, encoding="utf-8")
    result = run_tripwire()
    assert result["halted"] is True  # still halted: clearing is a human act
    assert "pre_existing_halt" in result["checks"]
    # Architect clears it manually; system recovers.
    halt_path().unlink()
    assert run_tripwire()["halted"] is False


def test_unity_module_has_no_write_path():
    """Art. 32.2, enforced structurally: parse unity.py's AST and assert
    no call in the module can write, delete, or re-permission a file.
    (Checking the AST, not the source text, so documentation may honestly
    *describe* the absence of write calls without tripping the check.)"""
    import ast

    src = Path(__import__("seira_core.unity", fromlist=["unity"]).__file__).read_text()
    tree = ast.parse(src)
    forbidden_attrs = {
        "write_text", "write_bytes", "write", "writelines",
        "unlink", "chmod", "rename", "replace", "truncate", "rmdir",
    }
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr in forbidden_attrs:
            violations.append(f"line {node.lineno}: .{fn.attr}(...)")
        if isinstance(fn, ast.Name) and fn.id == "open":
            # open() with any write/append/create/update mode is a write path.
            mode = ""
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            if any(c in mode for c in "wax+"):
                violations.append(f"line {node.lineno}: open(..., {mode!r})")
    assert not violations, f"unity.py contains write paths: {violations}"
