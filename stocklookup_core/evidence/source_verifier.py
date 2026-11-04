"""Receipt trust for feedback sources.

The digest covers this module and the fingerprint helper only. An evaluator-only
edit of ``prospective_feedback_streaming`` does not invalidate a receipt. A change
to the fingerprint helper or to this module does. Without a matching digest the
caller hashes the file.
"""
from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path

_DIGEST: str | None = None

_UNITS = (
    "stocklookup_core.evidence.source_file_fingerprint",
    "stocklookup_core.evidence.source_verifier",
)


def verification_units() -> tuple[str, ...]:
    """Modules whose bytes are the verifier. The streaming evaluator is not one of them."""
    return _UNITS


def reset_verification_code_digest() -> None:
    global _DIGEST
    _DIGEST = None


def verification_code_digest() -> str:
    """SHA-256 of the fingerprint helper and this module, each normalized to LF."""
    global _DIGEST
    if _DIGEST is None:
        digest = hashlib.sha256()
        for name in _UNITS:
            module = import_module(name)
            payload = Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
            digest.update(hashlib.sha256(payload).digest())
        _DIGEST = digest.hexdigest()
    return _DIGEST
