"""Exact E6 period-identity boundary and fail-closed tamper checks."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.verify_retention_reader_transition import (
    OFFICIAL_FINANCIAL_PERIOD_IDENTITY_MANIFEST as MANIFEST,
    OFFICIAL_FINANCIAL_PERIOD_IDENTITY_SOURCE as SOURCE,
    historical_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def test_period_identity_transition_reconstructs_exact_e6_baseline():
    spec = json.loads((ROOT / MANIFEST).read_bytes())
    original = subprocess.check_output(
        ["git", "show", spec["base_commit"] + ":" + SOURCE], cwd=ROOT).replace(b"\r\n", b"\n")
    assert historical_bytes(ROOT, SOURCE) == original
    assert hashlib.sha256(original).hexdigest() == spec["prior_sha256_lf"]


@pytest.mark.parametrize("tamper", ["active", "archive", "manifest", "hashes", "missing"])
def test_period_identity_transition_rejects_tampering(tmp_path, tamper):
    spec = json.loads((ROOT / MANIFEST).read_bytes())
    for path in (MANIFEST, SOURCE, spec["archive"]):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    if tamper in {"active", "archive"}:
        target = tmp_path / (SOURCE if tamper == "active" else spec["archive"])
        target.write_bytes(target.read_bytes() + b"# tampered\n")
    elif tamper == "manifest":
        spec["release_authority"] = "GRANTED"
    elif tamper == "hashes":
        target = tmp_path / spec["archive"]
        target.write_bytes(b"# substituted baseline\n")
        spec["prior_sha256_lf"] = hashlib.sha256(target.read_bytes()).hexdigest()
    if tamper in {"manifest", "hashes"}:
        (tmp_path / MANIFEST).write_text(json.dumps(spec), encoding="utf-8")
    if tamper == "missing":
        (tmp_path / MANIFEST).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        historical_bytes(tmp_path, SOURCE)
