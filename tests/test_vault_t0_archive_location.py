"""D5: T0 archive-location registration while the original is observable, then a registered restore."""
import json
from pathlib import Path

import pytest

import prospective_t0_seal_index as seals
from tools import vault_snapshot as vault
from tools import vault_t0_archive_location as t0loc
from test_storage_portability import t0_fixture, volumes  # noqa: F401  (shared fixtures)

SESSION = "2026-10-05"
BIG = 64 * vault.CHUNK


def backed_up(volumes):
    source, hot, cold, ids, observer = volumes
    original, ref = t0_fixture(source)
    handoff = source / f"operations-review/canonical-post-close-v1/{SESSION}/session_handoff_bundle.json"
    handoff.parent.mkdir(parents=True)
    handoff.write_bytes(vault.canonical(dict(prospective_decision_snapshot=dict(
        status="RETAINED", identity="snapshot:original", path=str(original),
        seal_index={**ref, "status": "RETAINED"}))))
    paths = [*original.parent.iterdir(), handoff]
    rel = lambda p: p.relative_to(source).as_posix()
    index, receipt = original.parent / "prospective_t0_seal_index.json", original.parent / "prospective_t0_snapshot_write_receipt.json"
    boundary = dict(schema="vault_completed_boundary/v1", status="COMPLETE", session_identity=SESSION,
        source_identity="operation:original", cutoff="2026-10-05T09:00:00+00:00",
        completion_proof=dict(handoff=dict(relative_path=rel(handoff), sha256=vault.sha(handoff))),
        files=[dict(relative_path=rel(p), size=p.stat().st_size, sha256=vault.sha(p),
                    family="T0" if p.parent == original.parent else "IMMUTABLE_SESSION",
                    state="COMPLETE", immutable=True, lock_dependent=False) for p in paths],
        receipt_refs=[dict(relative_path=rel(receipt), sha256=vault.sha(receipt))],
        seal_refs=[dict(relative_path=rel(index), sha256=vault.sha(index))])
    boundary_path = hot / "boundary.json"
    boundary_path.write_bytes(vault.canonical(boundary))
    result = vault.snapshot(source, cold, boundary_path, vault.sha(boundary_path),
                            {"source": ids["C"], "destination": ids["W"]}, observer=observer)
    manifest = cold / "snapshots" / result["snapshot_identity"] / "manifest.json"
    return dict(original=original, manifest=manifest, manifest_sha=result["manifest_sha256"],
                boundary=boundary_path, boundary_sha=vault.sha(boundary_path))


def register(volumes, b, **kw):
    source, hot, cold, ids, observer = volumes
    args = dict(manifest_path=b["manifest"], manifest_sha=b["manifest_sha"], boundary_path=b["boundary"],
                boundary_sha=b["boundary_sha"], vault_root=cold, proof_out=hot / "proof" / "t0-archive.json",
                expected_volume=ids["W"], observer=observer, max_bytes=BIG)
    args.update(kw)
    return t0loc.register(**args)


def test_register_then_registered_restore_qualifies_only_through_proof(volumes):
    source, hot, cold, ids, observer = volumes
    b = backed_up(volumes)
    before = {p: p.read_bytes() for p in b["original"].parent.iterdir()}
    result = register(volumes, b)
    entry = result["proposed_catalog_entry"]
    assert result["catalog_activation"] == "NOT_ACTIVATED" and entry["state"] == "ARCHIVED_COLD"
    assert entry["original_path"] == str(b["original"]) and entry["artifact_identity"] == "snapshot:original"
    assert not (hot / "config").exists()  # no catalog written anywhere real
    stage = cold / "restore-drills" / SESSION
    stage.mkdir(parents=True)
    drilled = t0loc.drill(entry=entry, vault_root=cold, stage_root=stage, restore_proof_out=hot / "restored.json",
                          expected_archive_volume=ids["W"], expected_stage_volume=ids["W"], observer=observer,
                          max_bytes=BIG)
    assert drilled["t0_without_proof"] == "REFUSED" and drilled["t0_with_registered_proof"] == "QUALIFIED"
    assert drilled["consumer_eligibility"].startswith("NOT_ELIGIBLE")
    restored = Path(drilled["restored_snapshot"])
    assert restored.read_bytes() == b["original"].read_bytes()
    assert seals.fingerprint(restored) != seals.fingerprint(b["original"])
    assert {p: p.read_bytes() for p in before} == before  # original seal/index/receipt never rewritten


def test_stale_original_after_backup_refuses_registration(volumes):
    b = backed_up(volumes)
    raw = b["original"].read_bytes()
    b["original"].write_bytes(raw)  # same bytes, new native fingerprint (mtime/change)
    with pytest.raises(vault.Refused, match="STALE_ORIGINAL"):
        register(volumes, b)


@pytest.mark.parametrize("fault", ["boundary_sha", "manifest_sha", "wrong_volume", "absent_volume"])
def test_registration_refuses_unbound_inputs(volumes, fault):
    source, hot, cold, ids, observer = volumes
    b = backed_up(volumes)
    kw = {}
    if fault == "boundary_sha":
        kw["boundary_sha"] = "0" * 64
    elif fault == "manifest_sha":
        kw["manifest_sha"] = "0" * 64
    elif fault == "wrong_volume":
        kw["expected_volume"] = dict(ids["W"], id="guid:other")
    else:
        def absent(path):
            raise vault.Refused("volume missing or identity unavailable")
        kw["observer"] = absent
    with pytest.raises(vault.Refused):
        register(volumes, b, **kw)
    assert not (hot / "proof" / "t0-archive.json").exists()


def test_drill_refuses_corrupt_object_wrong_archive_volume_and_existing_target(volumes):
    source, hot, cold, ids, observer = volumes
    b = backed_up(volumes)
    entry = register(volumes, b)["proposed_catalog_entry"]
    stage = cold / "restore-drills" / SESSION
    stage.mkdir(parents=True)
    drill = lambda **kw: t0loc.drill(**{**dict(entry=entry, vault_root=cold, stage_root=stage,
        restore_proof_out=hot / "restored.json", expected_archive_volume=ids["W"], expected_stage_volume=ids["W"],
        observer=observer, max_bytes=BIG), **kw})
    with pytest.raises(vault.Refused):
        drill(expected_archive_volume=dict(ids["W"], id="guid:other"))
    obj = cold / entry["vault"]["object_path"]
    good = obj.read_bytes()
    obj.write_bytes(good.replace(b"original", b"0riginal"))
    with pytest.raises(vault.Refused):
        drill()
    obj.write_bytes(good)
    with pytest.raises(vault.Refused):  # stale storage proof: object fingerprint changed by the rewrite
        drill()
