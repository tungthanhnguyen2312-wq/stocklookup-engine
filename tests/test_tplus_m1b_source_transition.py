"""M1b peels to the merged M1 streaming bytes and fails closed on tamper."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.verify_retention_reader_transition import (
    TPLUS_INCREMENTAL_MANIFEST, TPLUS_M1B_ARCHIVE, TPLUS_M1B_BASE, TPLUS_M1B_MANIFEST,
    TPLUS_RESUME_SOURCE, _tplus_incremental_cost_prior_bytes, _tplus_m1b_prior_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def test_m1b_peels_to_the_merged_incremental_active_source():
    spec = json.loads((ROOT / TPLUS_M1B_MANIFEST).read_bytes())
    row = spec["sources"][TPLUS_RESUME_SOURCE]
    prior = _lf((ROOT / TPLUS_M1B_ARCHIVE).read_bytes())
    base = _lf(subprocess.check_output(["git", "show", f"{TPLUS_M1B_BASE}:{TPLUS_RESUME_SOURCE}"], cwd=ROOT))
    assert prior == base
    assert hashlib.sha256(prior).hexdigest() == row["prior_sha256_lf"]
    incremental = json.loads((ROOT / TPLUS_INCREMENTAL_MANIFEST).read_bytes())
    assert row["prior_sha256_lf"] == incremental["sources"][TPLUS_RESUME_SOURCE]["active_sha256_lf"]
    assert spec["previous_e4_v2_digest"] == incremental["active_e4_v2_digest"]
    live = _lf((ROOT / TPLUS_RESUME_SOURCE).read_bytes())
    assert hashlib.sha256(live).hexdigest() == row["active_sha256_lf"] != row["prior_sha256_lf"]
    assert _tplus_m1b_prior_bytes(ROOT, TPLUS_RESUME_SOURCE, live) == prior
    assert _tplus_incremental_cost_prior_bytes(ROOT, TPLUS_RESUME_SOURCE, prior) != prior


@pytest.mark.parametrize("tamper", ["live", "archive", "scope"])
def test_m1b_successor_rejects_tamper(tmp_path, tamper):
    for relative in (TPLUS_RESUME_SOURCE, TPLUS_M1B_ARCHIVE, TPLUS_M1B_MANIFEST):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    if tamper == "live":
        (tmp_path / TPLUS_RESUME_SOURCE).write_bytes(b"changed")
    elif tamper == "archive":
        (tmp_path / TPLUS_M1B_ARCHIVE).write_bytes(b"changed")
    else:
        spec = json.loads((tmp_path / TPLUS_M1B_MANIFEST).read_bytes())
        spec["scope"] = "UNBOUNDED"
        (tmp_path / TPLUS_M1B_MANIFEST).write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="TPLUS_M1B_SOURCE_TRANSITION_"):
        _tplus_m1b_prior_bytes(tmp_path, TPLUS_RESUME_SOURCE, _lf((tmp_path / TPLUS_RESUME_SOURCE).read_bytes()))
