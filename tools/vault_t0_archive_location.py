"""Offline, opt-in T0 archive-location registration and registered restore drill (D5).

``register`` binds one backed-up T0 snapshot object in a COMPLETE Vault V1 manifest to its
ORIGINAL native seal while the original is still observable (existing
``register_portable_copy``: original index/receipt/fingerprint verified, never rewritten).
It also emits a *proposed* ``ARCHIVED_COLD`` cold-catalog entry that passes the existing
catalog validator. Nothing is activated: the Production catalog is not written.

``drill`` performs the existing ``restore_registered`` into an explicit staging root plus the
pinned index/receipt objects, then proves ``load_verified`` accepts the relocated T0 only through
that registered storage proof. Both write only under explicit out/staging paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True

from tools import vault_snapshot as v

T0_FILE = "prospective_decision_snapshot.json"
INDEX_FILE = "prospective_t0_seal_index.json"
RECEIPT_FILE = "prospective_t0_snapshot_write_receipt.json"


def _t0_rows(manifest: dict) -> tuple[dict, dict, dict]:
    t0 = [r for r in manifest["files"] if r.get("family") == "T0" and Path(r["relative_path"]).name == T0_FILE]
    v.require(len(t0) == 1, "exactly one archived T0 snapshot required")
    folder = Path(t0[0]["relative_path"]).parent.as_posix()
    rows = {r["relative_path"]: r for r in manifest["files"]}
    index, receipt = rows.get(folder + "/" + INDEX_FILE), rows.get(folder + "/" + RECEIPT_FILE)
    v.require(index is not None and receipt is not None, "archived T0 index/receipt closure missing")
    return t0[0], index, receipt


def _handoff_t0(source_root: Path, boundary: dict) -> dict:
    ref = boundary["completion_proof"]["handoff"]
    path = v.safe_path(source_root, ref["relative_path"])
    raw = path.read_bytes()
    v.require(v.digest(raw) == ref["sha256"], "original handoff changed since boundary")
    t0 = json.loads(raw).get("prospective_decision_snapshot") or {}
    v.require(t0.get("status") == "RETAINED" and (t0.get("seal_index") or {}).get("status") == "RETAINED",
              "original sealed T0 required")
    return t0


def register(*, manifest_path, manifest_sha, boundary_path, boundary_sha, vault_root, proof_out,
             expected_volume, observer=None, max_bytes) -> dict:
    """Register the archived T0 object against its still-observable original native seal."""
    from prospective_t0_seal_index import register_portable_copy
    import retained_evidence_catalog as catalog
    vault_root = Path(vault_root)
    manifest = v.read_manifest(Path(manifest_path), manifest_sha)
    raw = Path(boundary_path).read_bytes()
    v.require(v.digest(raw) == boundary_sha == manifest["boundary_sha256"], "boundary not the manifest's boundary")
    boundary = json.loads(raw)
    session = manifest["session_identity"]
    v.require(boundary["session_identity"] == session and boundary["source_identity"] == manifest["source_identity"],
              "manifest/boundary session or source mismatch")
    row, index_row, receipt_row = _t0_rows(manifest)
    source_root = Path(manifest["source_root"])
    original = Path(str(source_root / row["relative_path"]))  # exact string restore_registered re-derives
    index_path = source_root / index_row["relative_path"]
    t0 = _handoff_t0(source_root, boundary)
    v.require(Path(t0["path"]) == original and Path(t0["seal_index"]["path"]) == index_path,
              "handoff T0 reference is not the archived original path")
    v.require(v.fingerprint(original) == row["source_fingerprint"],
              "STALE_ORIGINAL: original changed since it was archived")
    obj = v.safe_path(vault_root, row["vault_path"])
    reference = {**t0["seal_index"], "path": str(index_path)}
    reference.pop("status", None)
    provenance = dict(snapshot_identity=manifest["plan_sha256"], manifest_sha256=manifest_sha,
                      boundary_sha256=boundary_sha, source_identity=manifest["source_identity"])
    proof = register_portable_copy(original, obj, Path(proof_out), t0_reference=reference,
                                   artifact_identity=t0["identity"], session=session,
                                   expected_volume=expected_volume, provenance=provenance,
                                   observer=observer, max_bytes=max_bytes)
    vault_rel = Path(manifest_path).absolute().relative_to(vault_root.absolute()).as_posix()
    entry = dict(relative_path=row["relative_path"], original_path=str(original), session_identity=session,
                 artifact_identity=t0["identity"], artifact_role="t0_snapshot", state="ARCHIVED_COLD",
                 original_size=row["size"], sha256=row["sha256"],
                 source_seal_provenance=manifest["source_identity"],
                 restore_procedure="tools.vault_t0_archive_location drill (explicit staged restore)",
                 restore_preconditions=["W volume attested", "manifest sha pinned", "archive proof sha pinned"],
                 archive_location=proof,
                 vault=dict(snapshot_identity=manifest["plan_sha256"], manifest_path=vault_rel,
                            manifest_sha256=manifest_sha, object_path=row["vault_path"],
                            object_sha256=row["sha256"], volume_id=expected_volume["id"]))
    with tempfile.TemporaryDirectory() as scratch:  # existing validator, never the Production catalog
        (Path(scratch) / "config").mkdir()
        (Path(scratch) / "config/retained_evidence_cold_catalog.json").write_bytes(
            v.canonical(dict(schema=catalog.SCHEMA, entries=[entry])))
        catalog.load(Path(scratch))
    return dict(status="ARCHIVE_LOCATION_REGISTERED", session=session, archive_proof=proof,
                proposed_catalog_entry=entry, catalog_activation="NOT_ACTIVATED", authority_effect="NONE")


def drill(*, entry, vault_root, stage_root, restore_proof_out, expected_archive_volume, expected_stage_volume,
          observer=None, max_bytes) -> dict:
    """Registered restore into an explicit stage; T0 qualifies only through the pinned proofs."""
    import retained_evidence_catalog as catalog
    from prospective_t0_seal_index import load_verified
    vault_root, stage_root = Path(vault_root), Path(stage_root)
    proof = catalog.restore_registered(entry, vault_root, stage_root, Path(restore_proof_out),
                                       expected_archive_volume=expected_archive_volume,
                                       expected_hot_volume=expected_stage_volume, observer=observer,
                                       max_bytes=max_bytes)
    manifest = v.read_manifest(v.safe_path(vault_root, entry["vault"]["manifest_path"]),
                               entry["vault"]["manifest_sha256"])
    row, index_row, receipt_row = _t0_rows(manifest)
    v.require(row["relative_path"] == entry["relative_path"], "entry is not this manifest's T0")
    for pinned in (index_row, receipt_row):  # exact pinned closure members, exclusive destinations
        source = v.safe_path(vault_root, pinned["vault_path"])
        target = v.safe_path(stage_root, pinned["relative_path"])
        with v.locked_file(source), source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        v.require(v.sha(target) == pinned["sha256"], "restored T0 proof bytes differ")
    restored_index = v.safe_path(stage_root, index_row["relative_path"])
    archive = json.loads(Path(entry["archive_location"]["path"]).read_bytes())
    reference = dict((archive.get("t0") or {}).get("reference") or {})
    v.require(reference, "archive proof carries no original T0 qualification")
    plain = {**reference, "path": str(restored_index)}
    try:  # without the registered proof the copy must stay unqualified
        load_verified(plain, expected_snapshot_identity=entry["artifact_identity"], session=entry["session_identity"])
        unqualified_refused = False
    except ValueError:
        unqualified_refused = True
    v.require(unqualified_refused, "copy qualified without a storage proof")
    qualified = {**plain, "storage_location": proof, "original_snapshot_path": entry["original_path"]}
    bindings = load_verified(qualified, expected_snapshot_identity=entry["artifact_identity"],
                             session=entry["session_identity"])
    v.require(bindings is not None and bindings.identity == entry["artifact_identity"], "registered T0 unqualified")
    return dict(status="REGISTERED_T0_RESTORE_QUALIFIED", session=entry["session_identity"],
                restored_snapshot=str(v.safe_path(stage_root, entry["relative_path"])), restore_proof=proof,
                t0_without_proof="REFUSED", t0_with_registered_proof="QUALIFIED",
                restored_fingerprint_equals_original=False, catalog_activation="NOT_ACTIVATED",
                consumer_eligibility="NOT_ELIGIBLE_UNTIL_CATALOG_ACTIVATED_BY_OWNER", authority_effect="NONE")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register")
    for name in ("manifest", "boundary", "vault", "volume", "out"):
        reg.add_argument("--" + name, type=Path, required=True)
    reg.add_argument("--manifest-sha", required=True)
    reg.add_argument("--boundary-sha", required=True)
    reg.add_argument("--max-bytes", type=int, required=True)
    dr = sub.add_parser("drill")
    for name in ("registration", "vault", "stage", "archive-volume", "stage-volume", "out"):
        dr.add_argument("--" + name, type=Path, required=True)
    dr.add_argument("--registration-sha", required=True)
    dr.add_argument("--max-bytes", type=int, required=True)
    a = parser.parse_args()
    if a.command == "register":
        out = a.out.absolute()
        result = register(manifest_path=a.manifest, manifest_sha=a.manifest_sha, boundary_path=a.boundary,
                          boundary_sha=a.boundary_sha, vault_root=a.vault, proof_out=out / "t0-archive-location.json",
                          expected_volume=json.loads(a.volume.read_bytes()), max_bytes=a.max_bytes)
        v.publish(out / "t0-registration.json", v.canonical(result))
    else:
        raw = a.registration.read_bytes()
        v.require(v.digest(raw) == a.registration_sha, "registration sha mismatch")
        out = a.out.absolute()
        result = drill(entry=json.loads(raw)["proposed_catalog_entry"], vault_root=a.vault, stage_root=a.stage,
                       restore_proof_out=out / "t0-restored-location.json",
                       expected_archive_volume=json.loads(a.archive_volume.read_bytes()),
                       expected_stage_volume=json.loads(a.stage_volume.read_bytes()), max_bytes=a.max_bytes)
        v.publish(out / "t0-drill.json", v.canonical(result))
    print(json.dumps({k: result[k] for k in ("status", "session", "authority_effect")}, indent=1))


if __name__ == "__main__":
    main()
