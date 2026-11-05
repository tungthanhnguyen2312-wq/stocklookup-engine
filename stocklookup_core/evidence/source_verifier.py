"""Receipt trust for feedback sources.

The digest covers the fingerprint helper, this module, the receipt reader, the
hash and stream implementation, and the retention validation those receipts store.
An evaluator-only edit of ``prospective_feedback_streaming`` does not invalidate a
receipt. A change to any unit below does. Without a matching digest the caller
hashes the file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_DIGEST: str | None = None

_UNITS = (
    "stocklookup_core.evidence.source_file_fingerprint",
    "stocklookup_core.evidence.source_verifier",
    "stocklookup_core.evidence.source_verifier_receipts",
    "stocklookup_core.evidence.storage_portability",
    "bounded_artifact_stream",
    "prospective_decision_retention",
    "retained_evidence_catalog",
)


def verification_units() -> tuple[str, ...]:
    """Modules whose bytes are the verifier. The streaming evaluator is not one of them."""
    return _UNITS


def reset_verification_code_digest() -> None:
    global _DIGEST
    _DIGEST = None


def _unit_path(name: str) -> Path:
    """File for a verifier unit. Reading the path does not import the module."""
    return Path(__file__).resolve().parents[2].joinpath(*name.split(".")).with_suffix(".py")


def verification_code_digest() -> str:
    """SHA-256 of each verifier unit, normalized to LF. The streaming evaluator is not included."""
    global _DIGEST
    if _DIGEST is None:
        digest = hashlib.sha256()
        for name in _UNITS:
            payload = _unit_path(name).read_bytes().replace(b"\r\n", b"\n")
            digest.update(hashlib.sha256(payload).digest())
        _DIGEST = digest.hexdigest()
    return _DIGEST
