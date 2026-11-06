"""Offline semantic re-qualification of a staged Vault restore at a NEW storage location.

Original evidence identity (session, source identity, cutoff, T0, seals, receipts,
hashes) comes only from the pinned original completed boundary. The restored tree
is a storage location: byte equality plus one explicit original-root mapping proves
the copy is that qualified closure and that its native references resolve inside it.
It grants no PIT/T0 or consumer authority, rewrites no retained byte, never touches
W:, never invokes Daily and never re-acquires a missing file. Only --out is written.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from tools import vault_snapshot as v

SCHEMA = "vault_restore_requalification/v1"
NOT_ELIGIBLE_REASONS = (
    # Inode-bound native seal fingerprints cannot be carried by a copy.
    "T0_NATIVE_FINGERPRINT_NOT_PORTABLE",
    # Consumers admit relocated bytes only via a catalog PRESENT_QUALIFIED storage proof.
    "NO_REGISTERED_STORAGE_LOCATION_PROOF",
    # Retained JSON keeps original absolute references; consumers do not apply this mapping.
    "NATIVE_REFERENCES_NOT_REWRITTEN",
)


def _within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


class NativeRootMap:
    """Exactly one explicit original-root -> restored-root mapping; no search or fallback."""

    def __init__(self, original_root, restored_root):
        original, restored = Path(original_root), Path(restored_root)
        v.require(original.is_absolute() and restored.is_absolute(), "MAPPING_ROOTS_MUST_BE_ABSOLUTE")
        v.require(".." not in original.parts and ".." not in restored.parts, "unsafe mapping root")
        original, restored = Path(os.path.normpath(original)), Path(os.path.normpath(restored))
        v.require(not _within(restored, original) and not _within(original, restored),
                  "MAPPING_ROOTS_MUST_BE_DISJOINT")
        self.original, self.restored = original, restored

    def relative(self, value, *, relative_root: str) -> str:
        v.require(isinstance(value, str) and bool(value), "native reference missing")
        path = Path(value)
        v.require(".." not in path.parts, "unsafe native reference")
        if not path.is_absolute():
            return (Path(relative_root) / path).as_posix() if relative_root else path.as_posix()
        path = Path(os.path.normpath(path))
        # A different drive/root is never substituted: it is not this restored closure.
        v.require(_within(path, self.original) and path != self.original,
                  "NATIVE_REFERENCE_OUTSIDE_MAPPED_ORIGINAL_ROOT")
        return Path(*path.parts[len(self.original.parts):]).as_posix()


def _walk(root: Path) -> set[str]:
    found = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:  # inspecting a junction/reparse point is itself a refusal
            v.safe_path(root, (Path(parent) / name).relative_to(root).as_posix())
        for name in files:
            found.add((Path(parent) / name).relative_to(root).as_posix())
    return found


def requalify(boundary_path, boundary_sha, original_root, restored_root, *,
              observer=None, expected_volume=None) -> dict:
    boundary_path = Path(boundary_path)
    raw = boundary_path.read_bytes()
    v.require(v.digest(raw) == boundary_sha, "ORIGINAL_BOUNDARY_SHA_MISMATCH")
    b = json.loads(raw)
    v.require(b.get("schema") == "vault_completed_boundary/v1" and b.get("status") == "COMPLETE"
              and b.get("closure_contract") == "vault_session_closure/v1"
              and b.get("cutoff_basis") == "ORIGINAL_CANONICAL_REQUESTED_AT", "unqualified original boundary")
    mapping = NativeRootMap(original_root, restored_root)
    restored = mapping.restored
    v.require(restored.is_dir(), "RESTORED_ROOT_MISSING")
    volume = None
    if expected_volume is not None:
        volume = (observer or v.native_volume)(restored)
        v.require(volume == expected_volume and volume.get("healthy") is True, "RESTORED_VOLUME_WRONG_OR_UNHEALTHY")
    rows = {r["relative_path"]: r for r in b["files"]}
    folded = {rel.casefold(): rel for rel in rows}
    v.require(len(folded) == len(rows), "boundary path case collision")
    present = _walk(restored)
    missing, extra = sorted(set(rows) - present), sorted(present - set(rows))
    # Missing is never "never collected" and never triggers reacquisition: it refuses.
    v.require(not missing, f"PARTIAL_RESTORE:{len(missing)} missing:{missing[:3]}")
    v.require(not extra, f"RESTORE_CONTAINS_FOREIGN_FILES:{len(extra)}:{extra[:3]}")

    with v.LockedSources() as locks:
        total = 0
        for rel, row in sorted(rows.items()):
            path = v.safe_path(restored, rel)
            locks.acquire(path)
            v.require(path.stat().st_size == row["size"] and v.sha(path) == row["sha256"],
                      "RESTORED_BYTES_MISMATCH:" + rel)
            total += row["size"]
        semantic, t0 = _semantic(b, mapping, rows, folded)
        locks.validate_all()
    t0_equal = t0.pop("restored_fingerprint_matches_original")
    return dict(
        schema=SCHEMA, status="RESTORED_CLOSURE_REQUALIFIED",
        original=dict(boundary_sha256=boundary_sha, session_identity=b["session_identity"],
                      source_identity=b["source_identity"], cutoff=b["cutoff"], cutoff_basis=b["cutoff_basis"],
                      completion_proof=b["completion_proof"], receipt_refs=b["receipt_refs"],
                      seal_refs=b["seal_refs"], committed_registry=b.get("committed_registry"), t0=t0),
        location=dict(original_root=str(mapping.original), restored_root=str(restored), volume=volume,
                      mapping_scope="SINGLE_EXPLICIT_ROOT"),
        verification=dict(
            original_native="BOUND_BY_PINNED_ORIGINAL_BOUNDARY_NOT_REPERFORMED",
            portable_bytes=dict(status="PASS", files=len(rows), bytes=total),
            semantic_closure=dict(status="PASS", **semantic),
            t0_native_fingerprint="EQUAL" if t0_equal else "NOT_PORTABLE"),
        consumer_eligibility=dict(status="NOT_ELIGIBLE", reasons=list(NOT_ELIGIBLE_REASONS)),
        authority_effect="NONE", reacquisition="FORBIDDEN", retained_bytes_rewritten=False)


def _semantic(b, mapping, rows, folded):
    restored = mapping.restored
    session = b["session_identity"]

    def load(rel):
        v.require(rel in rows, "proof outside restored closure: " + rel)
        path = v.safe_path(restored, rel)
        v.require(path.stat().st_size <= 8 * v.CHUNK, "proof size ceiling")
        return json.loads(path.read_bytes())

    def closure(value, relative_root=b.get("native_reference_root") or ""):
        rel = mapping.relative(value, relative_root=relative_root)
        hit = folded.get(rel.casefold())
        return rel, hit

    proof = b["completion_proof"]
    for key in ("completion_record", "handoff", "producer_manifest", "operation_manifest"):
        ref = proof[key]
        v.require((rows.get(ref["relative_path"]) or {}).get("sha256") == ref["sha256"],
                  "completion/seal outside restored closure")
    for ref in b["receipt_refs"] + b["seal_refs"]:
        v.require((rows.get(ref["relative_path"]) or {}).get("sha256") == ref["sha256"],
                  "receipt/seal outside restored closure")
    record, handoff, producer, operation = (load(proof[k]["relative_path"]) for k in
        ("completion_record", "handoff", "producer_manifest", "operation_manifest"))
    required = {"daily_operation_state": "LOCAL_COMPLETE", "daily_producer_status": "COMPLETED",
                "runtime_release_status": "READY", "trusted_subset_status": "READY"}
    v.require(record.get("session") == session and all(record.get(k) == x for k, x in required.items())
              and (record.get("acquisition") or {}).get("resolved_completed_session") == session,
              "Daily completion boundary failed")
    v.require(record.get("requested_at") == b["cutoff"], "ORIGINAL_CUTOFF_MISMATCH")
    from daily_research_session_operations import _identity
    from daily_producer_pipeline import _run_identity
    operation_id = operation.get("operation_identity")
    v.require(operation.get("market_session") == session and _identity(operation) == operation_id
              and b["source_identity"] == operation_id
              and record.get("daily_producer_operation_identity") == operation_id
              and (producer.get("daily_session_operation") or {}).get("identity") == operation_id,
              "sealed operation binding failed")
    run_id = _run_identity(session, producer["producer_head"], producer["consumer_head"],
                           producer["source_plan"], operation_id)
    v.require(producer.get("target_market_session") == session and producer.get("run_identity") == run_id
              and record.get("daily_producer_run_identity") == run_id
              and handoff.get("daily_producer") == dict(status="COMPLETED", run_identity=run_id,
                                                        operation_identity=operation_id)
              and (handoff.get("market_session_proof") or {}).get("resolved_completed_session") == session,
              "Producer/handoff identity mismatch")

    # Every native reference the original emitter admitted must resolve inside this closure.
    unavailable = {x["relative_path"] for x in b.get("unavailable_optional_refs") or []}
    mapped = 0
    def must(value, *, allow_unavailable=False):
        nonlocal mapped
        rel, hit = closure(value)
        v.require(hit is not None or (allow_unavailable and rel in unavailable),
                  "REFERENCE_OUTSIDE_RESTORED_CLOSURE:" + rel)
        mapped += 1
        return hit
    for item in (producer.get("source_plan") or {}).get("items", []):
        if item.get("artifact_path"):
            must(item["artifact_path"])
    shadow = producer.get("daily_session_shadow_recommendation") or {}
    if shadow.get("path"):
        must(shadow["path"])
    for value in (handoff.get("deeper_bundles") or {}).values():
        if value:
            must(value, allow_unavailable=True)
    for value in (handoff.get("recommended_ai_inputs") or {}).values():
        if value:
            must(value)

    # Original T0 bindings, minus the inode-bound fingerprint a copy cannot carry.
    from prospective_t0_seal_index import verify
    t0 = handoff.get("prospective_decision_snapshot") or {}
    seal = t0.get("seal_index") or {}
    v.require(t0.get("status") == "RETAINED" and seal.get("status") == "RETAINED", "original sealed T0 required")
    snapshot_rel, index_rel = must(t0.get("path")), must(seal.get("path"))
    receipt_rel = (Path(index_rel).parent / "prospective_t0_snapshot_write_receipt.json").as_posix()
    index = verify(load(index_rel), "prospective_t0_seal_index")
    receipt = verify(load(receipt_rel), "prospective_t0_snapshot_write_receipt")
    v.require(index["artifact_identity"] == seal.get("artifact_identity")
              and receipt["artifact_identity"] == seal.get("write_receipt_identity")
              and index["snapshot_identity"] == t0.get("identity") == receipt["snapshot_identity"]
              and index["session"] == session == receipt["session"]
              and receipt["index_identity"] == index["artifact_identity"]
              and receipt["index_sha256"] == index["artifact_sha256"]
              and receipt["snapshot_file_sha256"] == index["snapshot_file_sha256"]
              and index["snapshot_file"] == "prospective_decision_snapshot.json"
              and snapshot_rel == (Path(index_rel).parent / index["snapshot_file"]).as_posix()
              and rows[snapshot_rel]["sha256"] == index["snapshot_file_sha256"]
              and index.get("operation_identity") == operation_id,
              "T0_INDEX_SNAPSHOT_OR_RECEIPT_BINDING_INVALID")
    restored_fp = v.fingerprint(v.safe_path(restored, snapshot_rel))
    t0_out = dict(snapshot_identity=index["snapshot_identity"], index_identity=index["artifact_identity"],
                  write_receipt_identity=receipt["artifact_identity"],
                  snapshot_file_sha256=index["snapshot_file_sha256"],
                  original_snapshot_fingerprint=receipt["snapshot_fingerprint"],
                  restored_fingerprint_matches_original=restored_fp == receipt["snapshot_fingerprint"])
    return dict(mapped_references=mapped, operation_identity=operation_id, run_identity=run_id), t0_out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--boundary-sha", required=True)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--restored-root", type=Path, required=True)
    parser.add_argument("--expected-volume", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.absolute()
    v.require(not _within(out, args.restored_root.absolute()), "--out must be outside the restored root")
    expected = json.loads(args.expected_volume.read_bytes()) if args.expected_volume else None
    receipt = requalify(args.boundary, args.boundary_sha, args.original_root, args.restored_root,
                        expected_volume=expected)
    v.publish(out, v.canonical(receipt))
    print(json.dumps(dict(status=receipt["status"], out=str(out), sha256=v.sha(out),
                          consumer_eligibility=receipt["consumer_eligibility"]["status"],
                          t0_native_fingerprint=receipt["verification"]["t0_native_fingerprint"]), indent=2))


if __name__ == "__main__":
    main()
