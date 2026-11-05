"""Emit an opt-in, source-read-only completed-session Vault boundary.

The source is the common ancestor of the code checkout and retained root. No
latest pointer, mtime, pending registry row, or caller-supplied file list is proof.
Only --out is written. This tool never invokes Daily or any evidence writer.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True

from tools import vault_snapshot as v
from tools.vault_post_daily_adapter import MUTABLE, qualified_boundary, native_reference

REGISTRY = "config/daily_research_session_input_registry.json"
OPERATIONS = "operations-review/daily-research-session-operations-v1"
RUNS = "operations-review/daily-producer-runs-v1"


def artifact_digest(path: Path) -> tuple[dict, str]:
    """Canonical content SHA with one mapping/list record resident at a time."""
    from bounded_artifact_stream import ObjectStream, canonical_bytes
    digest, meta = hashlib.sha256(), {}
    digest.update(b"{")
    first = True
    with path.open(encoding="utf-8") as stream:
        parser = ObjectStream(stream)
        for key in parser.members():
            included = key not in {"artifact_identity", "artifact_sha256"}
            if included:
                if not first:
                    digest.update(b",")
                first = False
                digest.update(canonical_bytes(key) + b":")
            if key == "records" and parser.peek() in {"{", "["}:
                mapping = parser.peek() == "{"
                digest.update(b"{" if mapping else b"[")
                record_first = True
                if mapping:
                    for ticker in parser.members():
                        if not record_first:
                            digest.update(b",")
                        record_first = False
                        digest.update(canonical_bytes(ticker) + b":" + canonical_bytes(parser.value()))
                else:
                    parser.take("[")
                    while parser.peek() != "]":
                        if not record_first:
                            parser.take(",")
                            digest.update(b",")
                        record_first = False
                        digest.update(canonical_bytes(parser.value()))
                    parser.take("]")
                digest.update(b"}" if mapping else b"]")
            else:
                value = parser.value()
                meta[key] = value
                if included:
                    digest.update(canonical_bytes(value))
        v.require(not parser.peek(), "trailing artifact JSON")
    digest.update(b"}")
    return meta, digest.hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                       capture_output=True, timeout=60)
    v.require(p.returncode == 0, "committed registry unavailable")
    return p.stdout


def _eligible(relative: str):
    parts = Path(relative).parts
    v.require(not any(p.lower() in {"config", "data", "dashboard-runtime", "tmp", "temp",
                                   "accumulators"} for p in parts)
              and not any(token.lower() in relative.lower() for token in MUTABLE)
              and Path(relative).suffix.lower() not in {
                  ".db", ".sqlite", ".sqlite3", ".lock", ".tmp", ".partial", ".publishing"}
              and not relative.lower().endswith(("-wal", "-shm", "-journal")),
              "mutable/ineligible closure member: " + relative)


def emit(source: Path, repo: Path, retained: Path, session: str, out: Path, *,
         max_bytes=64*v.CHUNK) -> dict:
    source, repo, retained, out = (Path(p).absolute() for p in (source, repo, retained, out))
    v.require(date.fromisoformat(session).isoformat() == session, "invalid session")
    v.require(not out.is_relative_to(source) and not source.is_relative_to(out),
              "--out must be disjoint from source")
    v.safe_path(out.parent, out.name)
    # safe_path checks every ancestor for reparse points before any traversal/read.
    for path in (repo, retained):
        v.require(path.is_relative_to(source), "source must contain repo and retained roots")
        v.safe_path(source, path.relative_to(source).as_posix())
    commit = _git(repo, "rev-parse", "HEAD").decode().strip()
    raw = _git(repo, "show", f"{commit}:{REGISTRY}")
    committed = json.loads(raw)
    row = (committed.get("completed_sessions") or {}).get(session)
    selection = (committed.get("sessions") or {}).get(session)
    v.require(isinstance(row, dict) and row.get("status") == "COMPLETED_RETAINED_EVIDENCE"
              and row.get("trading_day_valid") is True and isinstance(selection, dict)
              and bool(selection), "session absent from committed completed registry")
    frozen = row.get("frozen_input_identities") or {}
    from pending_session_input_freeze import REQUIRED_INPUT_KEYS
    v.require(set(REQUIRED_INPUT_KEYS) <= set(selection) and set(frozen) == set(selection) and all(
        isinstance(x, dict) and x.get("artifact_identity") == frozen[k]
        for k, x in selection.items()), "committed frozen selection mismatch")
    observed = {}
    def observe(path):
        if path.is_file():
            current = v.fingerprint(path)
            v.require(path not in observed or observed[path] == current, "source changed during discovery")
            observed[path] = current
        return path
    registry_path = observe(repo / REGISTRY)
    working = json.loads(registry_path.read_bytes())
    v.require((working.get("completed_sessions") or {}).get(session) == row
              and (working.get("sessions") or {}).get(session) == selection,
              "working registry differs for selected committed session")

    def resolve(value):
        return observe(native_reference(source, value, relative_root=retained))
    def reference(value):
        return observe(native_reference(source, value, relative_root=repo))

    handoff_path = resolve(f"operations-review/canonical-post-close-v1/{session}/session_handoff_bundle.json")
    handoff = json.loads(handoff_path.read_bytes())
    binding = handoff.get("daily_producer") or {}
    operation_id, run_id = binding.get("operation_identity"), binding.get("run_identity")
    v.require(binding.get("status") == "COMPLETED" and isinstance(operation_id, str)
              and isinstance(run_id, str), "completed handoff binding missing")
    operation_path = resolve(f"{OPERATIONS}/{session}/{operation_id.split(':')[-1]}/run_manifest.json")
    producer_path = resolve(f"{RUNS}/{session}/{run_id.split(':')[-1]}/run_manifest.json")
    operation, producer = (json.loads(p.read_bytes()) for p in (operation_path, producer_path))
    from daily_research_session_operations import _identity
    from daily_producer_pipeline import _run_identity
    v.require(operation.get("market_session") == session and _identity(operation) == operation_id,
              "operation manifest hash mismatch")
    v.require(producer.get("target_market_session") == session and producer.get("run_identity") == run_id
              and _run_identity(session, producer["producer_head"], producer["consumer_head"],
                                producer["source_plan"], operation_id) == run_id,
              "producer manifest identity mismatch")
    inputs = operation.get("input_artifacts") or {}
    v.require(set(frozen) <= set(inputs) and set(inputs) - set(frozen) <= {"macro"}
              and all(inputs[k].get("artifact_identity") == value for k, value in frozen.items()),
              "operation frozen input lineage mismatch")
    v.require((producer.get("daily_session_operation") or {}).get("identity") == operation_id,
              "producer operation binding mismatch")
    records = []
    record_root = resolve(f"operations-review/canonical-daily-operation-v1/{session}")
    for path in sorted(record_root.glob("op-*/daily_operation_record.json")):
        path = observe(v.safe_path(source, path.relative_to(source).as_posix()))
        record = json.loads(path.read_bytes())
        if (record.get("session") == session and record.get("daily_producer_operation_identity") == operation_id
                and record.get("daily_producer_run_identity") == run_id
                and record.get("daily_operation_state") == "LOCAL_COMPLETE"):
            records.append(path)
    v.require(len(records) == 1, "unique completed canonical operation required")
    record_path = records[0]
    t0 = handoff.get("prospective_decision_snapshot") or {}
    v.require(t0.get("status") == "RETAINED" and (t0.get("seal_index") or {}).get("status") == "RETAINED",
              "original sealed T0 required")
    snapshot_path, index_path = reference(t0["path"]), reference(t0["seal_index"]["path"])
    v.require(snapshot_path.parent == index_path.parent, "T0 proof directory mismatch")
    receipt_path = index_path.parent / "prospective_t0_snapshot_write_receipt.json"
    index = json.loads(index_path.read_bytes())
    v.require(index.get("operation_identity") == operation_id, "T0 operation binding mismatch")
    # This is the original canonical request boundary, not an invented backup time.
    cutoff = json.loads(record_path.read_bytes()).get("requested_at")
    v.require(isinstance(cutoff, str) and bool(cutoff), "original canonical cutoff missing")

    paths = {}
    total = 0
    def add(path, family="IMMUTABLE_SESSION"):
        nonlocal total
        relative = path.relative_to(source).as_posix()
        path = observe(v.safe_path(source, relative))
        _eligible(relative)
        v.require(path.is_file(), "closure file missing: " + relative)
        if relative not in paths:
            total += path.stat().st_size
            v.require(total <= max_bytes, "closure exceeds explicit byte budget")
            paths[relative] = family

    def tree(base, family="IMMUTABLE_SESSION"):
        # Never follow a junction; inspecting its path is itself a refusal.
        for parent, dirs, files in os.walk(base, followlinks=False):
            for name in dirs:
                v.safe_path(source, (Path(parent)/name).relative_to(source).as_posix())
            for name in files:
                add(Path(parent)/name, family)

    for base in (operation_path.parent, producer_path.parent, record_path.parent):
        tree(base)
    add(handoff_path)
    for filename in ("opportunity_research_bundle.json", "full_universe_bundle_index.json",
                     "dashboard_release_set_index.json"):
        add(handoff_path.parent / filename)
    tree(snapshot_path.parent, "T0")
    verified_inputs = {}
    def verify_input(path, expected):
        if path not in verified_inputs:
            meta, digest = artifact_digest(path)
            v.require(meta.get("artifact_sha256") == digest
                      and str(meta.get("artifact_identity", "")).split(":")[-1] == digest,
                      "frozen artifact content hash mismatch")
            verified_inputs[path] = meta.get("artifact_identity")
        v.require(verified_inputs[path] == expected, "frozen artifact identity mismatch")
    source_items = {x.get("input_class"): x for x in (producer.get("source_plan") or {}).get("items", [])}
    for key, entry in inputs.items():
        ref = selection.get(key) or {"path": (source_items.get(key) or {}).get("artifact_path")}
        # The operation writer materializes its attached macro under this exact
        # filename; the source plan intentionally carries no external macro path.
        path = (observe(operation_path.parent / "current_macro_regime_artifact.json")
                if key == "macro" and not ref.get("path") else reference(ref["path"]))
        verify_input(path, entry.get("artifact_identity"))
        if key in selection:
            v.require(path == reference(selection[key]["path"]), "frozen input path mismatch")
        add(path, "RAW_EVIDENCE")
    for item in (producer.get("source_plan") or {}).get("items", []):
        if item.get("artifact_path"):
            path = reference(item["artifact_path"])
            verify_input(path, item.get("artifact_identity"))
            add(path, "RAW_EVIDENCE")
    shadow = producer.get("daily_session_shadow_recommendation") or {}
    if shadow.get("path"):
        add(reference(shadow["path"]))
    # A locator for an explicitly UNAVAILABLE downstream observation is not a
    # completed input. Preserve that original negative proof, never fabricate it.
    unavailable = []
    tier2_path = handoff_path.parent / "opportunity_research_bundle.json"
    tier2 = json.loads(tier2_path.read_bytes())
    for key, value in (handoff.get("deeper_bundles") or {}).items():
        if value:
            path = reference(value)
            feedback = tier2.get("prospective_decision_feedback") or {}
            if (key == "prospective_decision_feedback" and not path.exists()
                    and "prospective_decision_feedback_identity" in handoff
                    and handoff["prospective_decision_feedback_identity"] is None
                    and tier2.get("session") == session and feedback.get("status") == "UNAVAILABLE"
                    and feedback.get("identity") is None and bool(feedback.get("reason_code"))
                    and reference(feedback.get("path")) == path):
                unavailable.append(dict(relative_path=path.relative_to(source).as_posix(),
                                        status="UNAVAILABLE", reason_code=feedback["reason_code"]))
            else:
                add(path)
    for value in (handoff.get("recommended_ai_inputs") or {}).values():
        if value:
            add(reference(value))

    proof_paths = dict(registry=registry_path, completion_record=record_path, handoff=handoff_path,
                       producer_manifest=producer_path, operation_manifest=operation_path)
    # Hold the native source files stable across hashing, qualification and publication.
    with v.LockedSources() as locks:
        for path in [registry_path, *(source / rel for rel in sorted(paths))]:
            locks.acquire(path)
            v.require(observed[path] == v.fingerprint(path), "source changed before locking")
        files = [dict(relative_path=rel, size=(source/rel).stat().st_size, sha256=v.sha(source/rel),
                      family=family, state="COMPLETE", immutable=True, lock_dependent=False)
                 for rel, family in sorted(paths.items())]
        hashes = {x["relative_path"]: x["sha256"] for x in files}
        v.require(hashes[snapshot_path.relative_to(source).as_posix()] == index.get("snapshot_file_sha256"),
                  "original T0 native hash mismatch")
        for base in (operation_path.parent, producer_path.parent):
            delivery_path = base / "ai_research_bundle_manifest.json"
            if delivery_path.exists():
                delivery = json.loads(delivery_path.read_bytes())
                for name, item in (delivery.get("files") or {}).items():
                    native_name = ("dashboard/" + name if base == producer_path.parent
                                   and name == "current_decision_cockpit_projection.json" else name)
                    target = v.safe_path(source, (base/native_name).relative_to(source).as_posix())
                    v.require(hashes.get(target.relative_to(source).as_posix()) == item.get("sha256")
                              and target.stat().st_size == item.get("bytes"),
                              "original delivery native hash mismatch: " + str(target))
        proof = {key: dict(relative_path=path.relative_to(source).as_posix(), sha256=v.sha(path))
                 for key, path in proof_paths.items()}
        boundary = dict(schema="vault_completed_boundary/v1", status="COMPLETE", session_identity=session,
                        source_identity=operation_id, cutoff=cutoff, files=files, completion_proof=proof,
                        cutoff_basis="ORIGINAL_CANONICAL_REQUESTED_AT",
                        native_reference_root=repo.relative_to(source).as_posix(),
                        receipt_refs=[proof[k] for k in ("completion_record", "handoff", "producer_manifest")]
                                     + [dict(relative_path=receipt_path.relative_to(source).as_posix(),
                                             sha256=hashes[receipt_path.relative_to(source).as_posix()])],
                        seal_refs=[proof["operation_manifest"], dict(
                            relative_path=index_path.relative_to(source).as_posix(),
                            sha256=hashes[index_path.relative_to(source).as_posix()])],
                        committed_registry=dict(commit=commit, git_blob_sha256=v.digest(raw)),
                        closure_contract="vault_session_closure/v1")
        if unavailable:
            evidence_relative = tier2_path.relative_to(source).as_posix()
            boundary["unavailable_optional_refs"] = [dict(x, evidence_ref=dict(
                relative_path=evidence_relative, sha256=hashes[evidence_relative])) for x in unavailable]
        candidate = out / "boundary.candidate.json"
        # Qualification failure never publishes a COMPLETE boundary.
        out.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(v.canonical(boundary))
        boundary_sha = v.sha(candidate)
        with qualified_boundary(source, candidate, boundary_sha, max_bytes=max_bytes, locked_sources=locks):
            v.require(_git(repo, "rev-parse", "HEAD").decode().strip() == commit,
                      "committed registry HEAD changed")
            locks.validate_all()
            final = out / "boundary.json"
            v.publish(final, candidate.read_bytes())
    candidate.unlink()
    return dict(status="COMPLETE", boundary=str(final), boundary_sha256=boundary_sha,
                session=session, files=len(files), bytes=total, committed_registry_head=commit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "repo", "retained", "out"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--max-bytes", type=int, default=64*v.CHUNK)
    args = parser.parse_args()
    print(json.dumps(emit(args.source, args.repo, args.retained, args.session, args.out,
                          max_bytes=args.max_bytes), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
