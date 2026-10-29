"""The resumable T+ successor conserves the exact pre-corrective streaming source and fails closed on tamper."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tools.verify_retention_reader_transition import (
    STORAGE_MANIFEST, TPLUS_RESUME_MANIFEST, TPLUS_RESUME_SOURCE, historical_bytes,
    TPLUS_DAILY_MANIFEST, TPLUS_DAILY_ARCHIVE, _tplus_daily_prior_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "tests/fixtures/tplus_resumable_feedback_v1_sources/prospective_feedback_streaming.py.txt"


def _copy(tmp_path: Path) -> None:
    storage = json.loads((ROOT / STORAGE_MANIFEST).read_bytes())
    for relative in (TPLUS_RESUME_SOURCE, TPLUS_RESUME_MANIFEST, ARCHIVE, STORAGE_MANIFEST,
                     TPLUS_DAILY_MANIFEST, TPLUS_DAILY_ARCHIVE,
                     storage["sources"][TPLUS_RESUME_SOURCE]["archive"], "tests/fixtures/e2e3_frozen_sources.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_successor_peels_to_the_unchanged_storage_boundary():
    spec = json.loads((ROOT / TPLUS_RESUME_MANIFEST).read_bytes())
    row = spec["sources"][TPLUS_RESUME_SOURCE]
    storage = json.loads((ROOT / STORAGE_MANIFEST).read_bytes())["sources"][TPLUS_RESUME_SOURCE]
    assert row["prior_sha256_lf"] == storage["active_sha256_lf"]  # the older manifest is not repinned
    live = (ROOT / TPLUS_RESUME_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    boundary = _tplus_daily_prior_bytes(ROOT, TPLUS_RESUME_SOURCE, live)
    assert hashlib.sha256(boundary).hexdigest() == row["active_sha256_lf"] != row["prior_sha256_lf"]
    storage_archive = (ROOT / storage["archive"]).read_bytes().replace(b"\r\n", b"\n")
    assert historical_bytes(ROOT, TPLUS_RESUME_SOURCE) == storage_archive


@pytest.mark.parametrize("tamper", ["live", "archive", "scope"])
def test_successor_rejects_tampering(tmp_path, tamper):
    _copy(tmp_path)
    # Exercise the older successor at its historical boundary.
    shutil.copyfile(tmp_path / TPLUS_DAILY_ARCHIVE, tmp_path / TPLUS_RESUME_SOURCE)
    (tmp_path / TPLUS_DAILY_MANIFEST).unlink()
    if tamper == "live":
        (tmp_path / TPLUS_RESUME_SOURCE).write_bytes(b"# changed\n")
    elif tamper == "archive":
        (tmp_path / ARCHIVE).write_bytes(b"# changed\n")
    else:
        manifest = tmp_path / TPLUS_RESUME_MANIFEST
        spec = json.loads(manifest.read_bytes())
        spec["scope"] = "ANY_SOURCE"
        manifest.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="TPLUS_RESUME_SOURCE_TRANSITION_"):
        historical_bytes(tmp_path, TPLUS_RESUME_SOURCE)
