"""seira_web.accounts — platform accounts, sessions, tenant allocation.

Platform state (accounts, sessions) lives under SEIRA_PLATFORM_ROOT
(default ~/.seira-platform) — deliberately *outside* every tenant tree
and outside seira_core entirely: no Seira's grades ever share a file
with login machinery.

One account ↔ one tenant ↔ one Seira (Preamble; MULTITENANCY.md). The
tenant id is derived from the account's random id, never from a
user-chosen name, so it is stable and unspoofable.

Passwords: scrypt from the standard library (unique salt per account,
n=2**14, r=8, p=1) — zero extra dependencies, constant-time compare.
Sessions: random 256-bit tokens with expiry, stored server-side.

Single-process assumption for W1 (JSON files, atomic-replace writes);
documented in INTEGRATION.md, revisit if the platform outgrows one
worker.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

SESSION_TTL_HOURS = 24 * 14


class AccountError(Exception):
    pass


def platform_root() -> Path:
    env = os.environ.get("SEIRA_PLATFORM_ROOT", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".seira-platform"


def _accounts_path() -> Path:
    return platform_root() / "accounts.json"


def _sessions_path() -> Path:
    return platform_root() / "sessions.json"


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: Dict[str, Any]) -> None:
    platform_root().mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    ).hex()


def create_account(email: str, password: str) -> Dict[str, Any]:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise AccountError("A valid email is required.")
    if len(password) < 10:
        raise AccountError("Password must be at least 10 characters.")
    accounts = _load(_accounts_path())
    if any(a["email"] == email for a in accounts.values()):
        raise AccountError("An account with this email already exists.")
    account_id = secrets.token_hex(8)
    tenant_id = f"t-{account_id}"  # matches tenancy's DNS-label rule
    salt = os.urandom(16)
    accounts[account_id] = {
        "account_id": account_id,
        "email": email,
        "salt": salt.hex(),
        "password_hash": _hash_password(password, salt),
        "tenant_id": tenant_id,
        "created_at": _now().isoformat(),
    }
    _save(_accounts_path(), accounts)
    return accounts[account_id]


def verify_login(email: str, password: str) -> Optional[Dict[str, Any]]:
    email = email.strip().lower()
    accounts = _load(_accounts_path())
    for a in accounts.values():
        if a["email"] == email:
            expected = a["password_hash"]
            actual = _hash_password(password, bytes.fromhex(a["salt"]))
            if hmac.compare_digest(expected, actual):
                return a
            return None
    return None


def create_session(account_id: str) -> str:
    sessions = _load(_sessions_path())
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "account_id": account_id,
        "expires_at": (_now() + _dt.timedelta(hours=SESSION_TTL_HOURS)).isoformat(),
    }
    # Opportunistic pruning of expired sessions.
    now_iso = _now().isoformat()
    sessions = {t: s for t, s in sessions.items() if s["expires_at"] > now_iso}
    _save(_sessions_path(), sessions)
    return token


def resolve_session(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    sessions = _load(_sessions_path())
    s = sessions.get(token)
    if s is None or s["expires_at"] <= _now().isoformat():
        return None
    return _load(_accounts_path()).get(s["account_id"])


def destroy_session(token: str) -> None:
    sessions = _load(_sessions_path())
    if token in sessions:
        del sessions[token]
        _save(_sessions_path(), sessions)
