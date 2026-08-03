"""Unity of Seira — Grade 1. Read access and verification only.

Art. 32 is enforced here by all three of its named measures:

1. **Structural isolation** — Unity is two plain files (content + lock),
   written once at Genesis, set read-only on disk. It is not a row in
   any table.
2. **Absence of a write path** — this module exports no function that
   writes Unity. The only code in the entire package that writes these
   files is Genesis (``genesis.py``), which refuses to run twice.
   Grep-auditable: ``unity.py`` contains no ``open(..., "w")``, no
   ``write_text``, no ``os.write``.
3. **The tripwire** — ``verify_unity`` recomputes the SHA-256 of
   UNITY.md and compares it to the Architect's committed hash in the
   lock file. ``tripwire.py`` runs this on a schedule and halts on
   mismatch.

Art. 9 discipline (Unity kept deliberately narrow — identity, telos,
name; no object-level stances) is the Architect's responsibility at
authoring time; code cannot judge doctrine, only guard its integrity.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from seira_core.canonical import sha256_text
from seira_core.errors import UnityIntegrityError
from seira_core.paths import unity_lock_path, unity_path


def read_lock() -> Dict[str, Any]:
    """Read the Unity lock (the Architect's committed hash + metadata)."""
    lock_file = unity_lock_path()
    if not lock_file.exists():
        raise UnityIntegrityError(
            f"Unity lock not found at {lock_file}. "
            "Either Genesis has not been performed, or the lock has been removed — "
            "the latter is itself an integrity violation."
        )
    try:
        return json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise UnityIntegrityError(f"Unity lock at {lock_file} is unreadable: {e}") from e


def read_unity(verify: bool = True) -> str:
    """Return Unity's content.

    By default this *verifies before returning*: content that fails the
    committed-hash check is never handed to a caller as if it were
    Seira's Unity. Pass ``verify=False`` only from the tripwire itself,
    which needs the raw content to report on a mismatch.
    """
    content_file = unity_path()
    if not content_file.exists():
        raise UnityIntegrityError(
            f"UNITY.md not found at {content_file}. "
            "Either Genesis has not been performed, or Unity has been removed."
        )
    try:
        content = content_file.read_text(encoding="utf-8")
    except OSError as e:
        raise UnityIntegrityError(f"UNITY.md at {content_file} is unreadable: {e}") from e
    if verify:
        _verify_content(content)
    return content


def _verify_content(content: str) -> Dict[str, Any]:
    lock = read_lock()
    committed = lock.get("unity_sha256")
    if not committed:
        raise UnityIntegrityError("Unity lock is missing its committed hash field.")
    actual = sha256_text(content)
    if actual != committed:
        raise UnityIntegrityError(
            "UNITY TRIPWIRE: Unity's content does not match the Architect's "
            f"committed hash. committed={committed} actual={actual}. "
            "Per Art. 32.3 this halts Seira; it is never a routine event."
        )
    return lock


def verify_unity() -> Dict[str, Any]:
    """Verify Unity against the committed hash; return lock metadata on
    success, raise UnityIntegrityError on any mismatch or absence."""
    content_file = unity_path()
    if not content_file.exists():
        raise UnityIntegrityError(f"UNITY.md not found at {content_file}.")
    content = content_file.read_text(encoding="utf-8")
    return _verify_content(content)
