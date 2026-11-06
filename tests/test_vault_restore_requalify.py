"""D5: a relocated restore is re-qualified against the pinned original closure, never promoted."""
import json
import os
from pathlib import Path
import shutil
import stat

import pytest

from tools import vault_snapshot as v
from tools import vault_restore_requalify as r
from test_vault_boundary_emit import SESSION, completed, run  # noqa: F401  (shared fixture)


def stage(fixture, tmp_path, *, drop_original=False):
    """Emit the original boundary, then copy exactly its closure to a disjoint restore root."""
    result = run(fixture)
    boundary = json.loads(Path(result["boundary"]).read_bytes())
    restored = tmp_path / "restored-elsewhere"
    for row in boundary["files"]:
        target = restored / row["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture["source"] / row["relative_path"], target)
    pinned = tmp_path / "pinned-boundary.json"
    shutil.copyfile(result["boundary"], pinned)
    if drop_original:
        # The original location is gone (git objects are read-only); only the copy remains.
        shutil.rmtree(fixture["source"], onexc=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
    return dict(boundary=pinned, sha=result["boundary_sha256"], original=fixture["source"],
                restored=restored, doc=boundary)


def requalify(s, **kwargs):
    return r.requalify(s["boundary"], s["sha"], s["original"], s["restored"], **kwargs)


def reboundary(s, tmp_path, change):
    doc = json.loads(s["boundary"].read_bytes())
    change(doc)
    path = tmp_path / "edited-boundary.json"
    path.write_bytes(v.canonical(doc))
    return dict(s, boundary=path, sha=v.sha(path))


def test_relocated_closure_requalifies_without_original_and_without_authority(completed, tmp_path):
    s = stage(completed, tmp_path, drop_original=True)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in s["restored"].rglob("*") if p.is_file()}
    receipt = requalify(s)
    assert receipt["status"] == "RESTORED_CLOSURE_REQUALIFIED"
    original = receipt["original"]
    # Original identity is carried verbatim from the pinned boundary, never re-derived from the new location.
    assert (original["session_identity"], original["source_identity"], original["cutoff"]) == (
        SESSION, s["doc"]["source_identity"], s["doc"]["cutoff"])
    assert original["completion_proof"] == s["doc"]["completion_proof"]
    assert original["t0"]["snapshot_identity"] == "prospective_decision_snapshot:original"
    assert receipt["verification"]["portable_bytes"] == dict(
        status="PASS", files=len(s["doc"]["files"]), bytes=sum(x["size"] for x in s["doc"]["files"]))
    assert receipt["verification"]["semantic_closure"]["mapped_references"] >= 3
    # A byte-identical copy is not the original inode: T0 authority and consumer use stay refused.
    assert receipt["verification"]["t0_native_fingerprint"] == "NOT_PORTABLE"
    assert receipt["consumer_eligibility"]["status"] == "NOT_ELIGIBLE"
    assert receipt["authority_effect"] == "NONE" and receipt["reacquisition"] == "FORBIDDEN"
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


@pytest.mark.parametrize("make_original, reason", [
    (lambda s, t: t / "some-other-root", "OUTSIDE_MAPPED_ORIGINAL_ROOT"),
    (lambda s, t: s["restored"], "DISJOINT"),
    (lambda s, t: s["restored"].parent, "DISJOINT"),
    (lambda s, t: Path("relative/root"), "ABSOLUTE"),
])
def test_invalid_mapping_refused(completed, tmp_path, make_original, reason):
    s = stage(completed, tmp_path)
    with pytest.raises(v.Refused, match=reason):
        requalify(dict(s, original=make_original(s, tmp_path)))


def test_wrong_or_absent_volume_refused(completed, tmp_path):
    s = stage(completed, tmp_path)
    good = dict(id="vol-T", label="T", healthy=True)
    assert requalify(s, observer=lambda p: good, expected_volume=good)["location"]["volume"] == good
    with pytest.raises(v.Refused, match="VOLUME_WRONG"):
        requalify(s, observer=lambda p: dict(good, id="vol-W"), expected_volume=good)

    def absent(path):
        raise v.Refused("volume missing or identity unavailable")
    with pytest.raises(v.Refused, match="volume missing"):
        requalify(s, observer=absent, expected_volume=good)


def test_tampered_restored_bytes_or_boundary_refused(completed, tmp_path):
    s = stage(completed, tmp_path)
    with pytest.raises(v.Refused, match="ORIGINAL_BOUNDARY_SHA_MISMATCH"):
        requalify(dict(s, sha="0" * 64))
    victim = s["restored"] / s["doc"]["completion_proof"]["handoff"]["relative_path"]
    victim.write_bytes(victim.read_bytes().replace(b"COMPLETED", b"COMPLETEX", 1))
    with pytest.raises(v.Refused, match="RESTORED_BYTES_MISMATCH"):
        requalify(s)


def test_partial_restore_refuses_without_reacquisition(completed, tmp_path):
    s = stage(completed, tmp_path)
    missing = s["restored"] / s["doc"]["files"][0]["relative_path"]
    missing.unlink()
    before = sorted(p for p in s["restored"].rglob("*"))
    with pytest.raises(v.Refused, match="PARTIAL_RESTORE:1"):
        requalify(s)
    assert sorted(p for p in s["restored"].rglob("*")) == before and not missing.exists()


def test_cross_session_or_foreign_file_refused(completed, tmp_path):
    s = stage(completed, tmp_path)
    foreign = s["restored"] / "retained/operations-review/canonical-post-close-v1/2026-11-05/session_handoff_bundle.json"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"{}")
    with pytest.raises(v.Refused, match="FOREIGN_FILES"):
        requalify(s)


def test_reference_outside_closure_and_cutoff_drift_refused(completed, tmp_path):
    s = stage(completed, tmp_path)
    t0_rel = completed["t0"].relative_to(completed["source"]).as_posix()

    def drop_t0(doc):
        doc["files"] = [x for x in doc["files"] if x["relative_path"] != t0_rel]
    (s["restored"] / t0_rel).unlink()
    with pytest.raises(v.Refused, match="REFERENCE_OUTSIDE_RESTORED_CLOSURE"):
        requalify(reboundary(s, tmp_path, drop_t0))
    shutil.copyfile(completed["t0"], s["restored"] / t0_rel)
    with pytest.raises(v.Refused, match="ORIGINAL_CUTOFF_MISMATCH"):
        requalify(reboundary(s, tmp_path, lambda doc: doc.update(cutoff="2026-11-04T16:00:00+07:00")))


def test_mapping_rejects_other_drive_and_traversal(tmp_path):
    m = r.NativeRootMap(tmp_path / "orig", tmp_path / "restored")
    assert m.relative(str(tmp_path / "orig" / "retained" / "a.json"), relative_root="repo") == "retained/a.json"
    assert m.relative("operations-review/x.json", relative_root="repo") == "repo/operations-review/x.json"
    with pytest.raises(v.Refused, match="unsafe"):
        m.relative(str(tmp_path / "orig" / ".." / "orig" / "a.json"), relative_root="")
    with pytest.raises(v.Refused, match="OUTSIDE_MAPPED"):
        m.relative("Q:/StockLookup/production-v1/retained/a.json" if Path("Q:/").is_absolute()
                   else "/elsewhere/a.json", relative_root="")
