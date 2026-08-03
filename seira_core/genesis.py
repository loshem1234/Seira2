"""Genesis — the one-time founding of a Seira (Const. Art. 22).

The Architect authors Unity and the founding Intellect directly; both
are exempt, by declaration, from the falsification bar — there is no
prior mechanism to have earned that bar against. Genesis is
non-repeatable: this module refuses to run if any founding artifact
already exists, and no other code in the package can create or replace
those artifacts.

This is the *only* module in seira_core that writes Unity's files.
After writing, both are set read-only on disk (0o444) — a friction
against accident, while the tripwire (Art. 32.3) remains the real
guard against modification by any means.

Psyche's founding content is also authored at Genesis per Art. 22, but
Psyche is Phase 3; the manifest records ``psyche_founded: false`` so
Phase 3 extends Genesis honestly rather than pretending it was
complete.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict

from seira_core.audit import EVENT_GENESIS, append_event
from seira_core.canonical import sha256_text
from seira_core.errors import GenesisAlreadyPerformedError
from seira_core.paths import (
    genesis_manifest_path,
    intellect_versions_path,
    seira_home,
    unity_dir,
    unity_lock_path,
    unity_path,
)


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def genesis_performed() -> bool:
    return unity_lock_path().exists() or genesis_manifest_path().exists()


def perform_genesis(
    unity_content: str,
    intellect_content: str,
    architect: str,
    seira_name: str,
) -> Dict[str, Any]:
    """Found a new Seira. Returns the Genesis manifest.

    Refuses if any founding artifact exists — including a bare Intellect
    store, which would indicate a half-founded state needing the
    Architect's inspection rather than silent completion.
    """
    if genesis_performed():
        raise GenesisAlreadyPerformedError(
            f"Genesis has already been performed under {seira_home()}. "
            "Genesis is non-repeatable (Art. 22); founding a new Seira "
            "requires a new SEIRA_HOME."
        )
    if intellect_versions_path().exists():
        raise GenesisAlreadyPerformedError(
            "An Intellect store exists without Unity artifacts — a "
            "half-founded state. The Architect must inspect and clear "
            f"{seira_home()} before Genesis can proceed."
        )
    if not unity_content.strip():
        raise ValueError("Unity content must not be empty.")
    if not intellect_content.strip():
        raise ValueError("Founding Intellect content must not be empty.")
    if not architect.strip():
        raise ValueError("The Architect must be named (Art. 1, 22).")
    if not seira_name.strip():
        raise ValueError("Seira's name is part of her Unity (Art. 9) and is required.")

    unity_dir().mkdir(parents=True, exist_ok=True)

    # 1. Write Unity content, then the Architect's committed hash.
    unity_path().write_text(unity_content, encoding="utf-8")
    unity_hash = sha256_text(unity_content)
    lock: Dict[str, Any] = {
        "seira_name": seira_name.strip(),
        "architect": architect.strip(),
        "founded_at": _utc_now_iso(),
        "unity_sha256": unity_hash,
        "note": (
            "Committed by the Architect at Genesis. Unity admits no internal "
            "amendment pathway (Const. Art. 32). Any mismatch between "
            "UNITY.md and unity_sha256 halts Seira."
        ),
    }
    unity_lock_path().write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # Read-only on disk (friction, not the guard — the tripwire is the guard).
    os.chmod(unity_path(), 0o444)
    os.chmod(unity_lock_path(), 0o444)

    # 2. Intellect v1, chained to Unity's hash.
    from seira_core.intellect import IntellectStore

    store = IntellectStore()
    v1 = store.append_genesis(intellect_content, architect=architect.strip())

    # 3. Genesis manifest.
    manifest: Dict[str, Any] = {
        "seira_name": seira_name.strip(),
        "architect": architect.strip(),
        "founded_at": lock["founded_at"],
        "unity_sha256": unity_hash,
        "intellect_v1_hash": v1["hash"],
        "psyche_founded": False,  # Phase 3 extends Genesis here (Art. 22).
        "constitution": "Constitution of Seira v2",
        "codex": "The Seira Codex",
    }
    genesis_manifest_path().write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.chmod(genesis_manifest_path(), 0o444)

    append_event(
        EVENT_GENESIS,
        {
            "seira_name": manifest["seira_name"],
            "architect": manifest["architect"],
            "unity_sha256": unity_hash,
            "intellect_v1_hash": v1["hash"],
        },
    )
    return manifest


def perform_psyche_genesis(
    founding_entries: list,
    architect: str,
) -> Dict[str, Any]:
    """Extend Genesis to found Psyche (Art. 22).

    The Architect authors the founding character content directly —
    exempt from the falsification bar, exactly as Unity and Intellect v1
    were. Non-repeatable: refuses if Psyche is already founded.

    ``founding_entries`` is a list of {"category", "content"} dicts
    (affinities may add "weight"). The manifest's ``psyche_founded``
    flag flips to true here — the one sanctioned write to the manifest
    after Genesis, performed only after verifying that the Unity and
    Intellect founding hashes it records are still exactly true.
    """
    from seira_core.psyche import PsycheStore
    from seira_core.intellect import IntellectStore
    from seira_core.unity import verify_unity

    if not genesis_performed():
        raise GenesisAlreadyPerformedError(
            "Unity/Intellect Genesis has not been performed; Psyche cannot "
            "be founded before what it proceeds from exists (Art. 6)."
        )
    if not architect.strip():
        raise ValueError("The Architect must be named (Art. 22).")
    if not founding_entries:
        raise ValueError(
            "Psyche founding requires at least one Architect-authored entry "
            "(Art. 22): a founded Psyche with no content is not founded."
        )

    store = PsycheStore()
    if store.founded():
        raise GenesisAlreadyPerformedError(
            "Psyche is already founded; Genesis is non-repeatable (Art. 22)."
        )

    # Verify the manifest still tells the truth before we touch it.
    lock = verify_unity()
    manifest = json.loads(genesis_manifest_path().read_text(encoding="utf-8"))
    if manifest.get("unity_sha256") != lock.get("unity_sha256"):
        raise GenesisAlreadyPerformedError(
            "Manifest and Unity lock disagree; refusing to extend Genesis "
            "on inconsistent founding records."
        )
    intellect_v1 = IntellectStore().history(verify=True)[0]
    if manifest.get("intellect_v1_hash") != intellect_v1["hash"]:
        raise GenesisAlreadyPerformedError(
            "Manifest and Intellect v1 disagree; refusing to extend Genesis."
        )

    founding = store._found(architect.strip(), founding_entries)

    manifest["psyche_founded"] = True
    manifest["psyche_founded_at"] = founding["ts"]
    manifest["psyche_genesis_hash"] = founding["hash"]
    os.chmod(genesis_manifest_path(), 0o644)
    genesis_manifest_path().write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.chmod(genesis_manifest_path(), 0o444)

    append_event(
        "psyche_genesis",
        {
            "architect": architect.strip(),
            "entry_count": len(founding_entries),
            "psyche_genesis_hash": founding["hash"],
        },
    )
    return manifest
