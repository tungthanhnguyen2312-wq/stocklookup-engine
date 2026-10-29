"""Exact daily successor preserves the merged resume boundary and every older source receipt."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.verify_retention_reader_transition import (
    TPLUS_DAILY_ARCHIVE, TPLUS_DAILY_BASE, TPLUS_DAILY_MANIFEST,
    TPLUS_RESUME_MANIFEST, TPLUS_RESUME_SOURCE, _tplus_daily_prior_bytes, historical_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def test_exact_merged_boundary_and_live_source_are_separately_bound():
    spec = json.loads((ROOT / TPLUS_DAILY_MANIFEST).read_bytes())
    row = spec["sources"][TPLUS_RESUME_SOURCE]
    prior = (ROOT / TPLUS_DAILY_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    base = subprocess.check_output(["git", "show", f"{TPLUS_DAILY_BASE}:{TPLUS_RESUME_SOURCE}"], cwd=ROOT)
    assert prior == base.replace(b"\r\n", b"\n")
    assert row["prior_sha256_lf"] == hashlib.sha256(prior).hexdigest()
    assert row["prior_sha256_lf"] == json.loads((ROOT / TPLUS_RESUME_MANIFEST).read_bytes())["sources"][TPLUS_RESUME_SOURCE]["active_sha256_lf"]
    live = (ROOT / TPLUS_RESUME_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    assert _tplus_daily_prior_bytes(ROOT, TPLUS_RESUME_SOURCE, live) == prior
    assert hashlib.sha256(live).hexdigest() == row["active_sha256_lf"] != row["prior_sha256_lf"]
    assert historical_bytes(ROOT, TPLUS_RESUME_SOURCE) != live


@pytest.mark.parametrize("tamper", ["live", "archive", "scope"])
def test_daily_successor_rejects_tamper(tmp_path, tamper):
    for relative in (TPLUS_RESUME_SOURCE, TPLUS_DAILY_ARCHIVE, TPLUS_DAILY_MANIFEST):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    if tamper == "live":
        (tmp_path / TPLUS_RESUME_SOURCE).write_bytes(b"changed")
    elif tamper == "archive":
        (tmp_path / TPLUS_DAILY_ARCHIVE).write_bytes(b"changed")
    else:
        spec = json.loads((tmp_path / TPLUS_DAILY_MANIFEST).read_bytes())
        spec["scope"] = "UNBOUNDED"
        (tmp_path / TPLUS_DAILY_MANIFEST).write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="TPLUS_DAILY_SOURCE_TRANSITION_"):
        _tplus_daily_prior_bytes(tmp_path, TPLUS_RESUME_SOURCE, (tmp_path / TPLUS_RESUME_SOURCE).read_bytes().replace(b"\r\n", b"\n"))
