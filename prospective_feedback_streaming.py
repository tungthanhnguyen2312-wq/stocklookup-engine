"""Streaming, resource-bounded builder for ``prospective_decision_outcome_feedback/v3``.

OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1. This is a resource corrective, not a learning-policy change:
every classification, horizon, maturity, ordering and identity rule is still owned by
``prospective_decision_outcome_feedback`` / ``integrated_decision_prospective_feedback`` /
``prospective_decision_retention``. This module only changes *how* the same artifact is read and written.

* Inputs stay on disk. T0 snapshots and legacy Integrated Decision artifacts are streamed one record at a
  time; the original immutable file remains the only authority (derived receipts/indexes are keyed by the
  SHA-256 of the exact source bytes and are rebuildable).
* Per-record feedback rows are written incrementally to spools, the canonical artifact identity is hashed
  incrementally, and the artifact is atomically published only after a raw-byte re-verification.
* The artifact content and ``artifact_identity`` are identical to ``build_feedback_artifact``'s; only the
  on-disk whitespace differs (canonical compact JSON instead of ``indent=2``).
* Rows are checkpointed per qualified decision source and evaluation context. Settled legacy sessions
  additionally carry a bounded dependency proof, so an appended Daily does not discard their work.
  Data is fsynced before the atomic manifest; every reused partition is re-hashed before publication.
"""
from __future__ import annotations

import errno
import hashlib
import heapq
import io
from importlib import import_module
import json
import os
import shutil
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import bounded_artifact_stream as bas
import integrated_decision_prospective_feedback as forward_bridge
import prospective_decision_outcome_feedback as fb
import prospective_decision_retention as retention
from stocklookup_core.evidence import source_verifier_receipts as _receipts
from stocklookup_core.evidence import source_verifier
from stocklookup_core.evidence.source_file_fingerprint import path_has_reparse_point, source_file_fingerprint

STREAM_CONTRACT_VERSION = _receipts.STREAM_CONTRACT_VERSION
STATE_DIR = _receipts.STATE_DIR
SourceHandle = _receipts.SourceHandle
StreamedRecords = _receipts.StreamedRecords
scan_legacy_artifact = _receipts.scan_legacy_artifact
load_snapshot_handle = _receipts.load_snapshot_handle
_legacy_receipt_path = _receipts._legacy_receipt_path
_receipt_path = _receipts._receipt_path
_price_receipt_path = _receipts._price_receipt_path
_fingerprint_index_path = _receipts._fingerprint_index_path
_trusted_anchored_receipt = _receipts._trusted_anchored_receipt
_bind_fingerprint = _receipts._bind_fingerprint
_receipt_sha_for_same_file = _receipts._receipt_sha_for_same_file
_verify_snapshot_stream = _receipts._verify_snapshot_stream
_handle_from_t0_receipt = _receipts._handle_from_t0_receipt
COMPLETION_CONTRACT_VERSION = "prospective_feedback_completion/v1"
RESULT_CONTRACT_VERSION = "prospective_feedback_result/v1"
PARTITION_CONTRACT_VERSION = "prospective_feedback_partition/v2"
PARTITION_DIR = Path("operations-review/prospective-decision-outcome-feedback-v1/_partitions")
PARTITION_MAX_BYTES = 256 * 1024 * 1024  # one session's rows are decoded resident at assembly
PARTITION_STORE_MAX_BYTES = 8 * 1024**3
PARTITION_STORE_MAX_ENTRIES = 4096
PARTITION_VARIANTS = 3
SETTLED_STORE_MAX_BYTES = 2 * 1024**3
SETTLED_STORE_MAX_ENTRIES = 131072
SETTLED_STORE_DIR = Path("operations-review/prospective-decision-outcome-feedback-v1/_settled_store")
EVALUATOR_INPUT_DIR = Path("operations-review/prospective-decision-outcome-feedback-v1/_evaluator_inputs")
EVALUATOR_INPUT_CONTRACT = "prospective_feedback_evaluator_input/v3"
EVALUATOR_INPUT_MAX_BYTES = 12 * 1024**3  # ~60 sessions of the deduplicated sidecar, with headroom
EVALUATOR_INPUT_MAX_ENTRIES = 4096
RECEIPT_MAX_BYTES = 64 * 1024 * 1024
ARTIFACT_IDENTITY_PREFIX = "prospective_decision_outcome_feedback:"
TEMP_PREFIX = ".feedback-"
LEGACY_UNSORTED_FALLBACK_MAX_BYTES = 128 * 1024 * 1024

OUTCOME_BUILT = "BUILT"
OUTCOME_ALREADY_COMPLETE = "ALREADY_COMPLETE"
OUTCOME_ALREADY_RETAINED_EQUAL = "ALREADY_RETAINED_EQUAL_IDENTITY"

REASON_SOURCE_INTEGRITY = "FEEDBACK_SOURCE_INTEGRITY_FAILED"
REASON_IMMUTABLE_CONFLICT = "FEEDBACK_IMMUTABLE_OUTPUT_CONFLICT"
REASON_COMPUTATION_ERROR = "FEEDBACK_COMPUTATION_ERROR"
REASON_RESOURCE_MEMORY = "FEEDBACK_RESOURCE_MEMORY_LIMIT"
REASON_RESOURCE_DISK = "FEEDBACK_RESOURCE_DISK_UNAVAILABLE"
REASON_INCOMPLETE_INPUT_CHANGED = "FEEDBACK_SOURCE_CHANGED_DURING_RUN"
REASON_T0_CORPUS_EMPTY = "FEEDBACK_T0_CORPUS_EMPTY"


class FeedbackStreamError(Exception):
    code = REASON_COMPUTATION_ERROR


class T0CorpusEmpty(FeedbackStreamError):
    """No genuine T0 source under ``root``: a wrong evidence root or a missing corpus, never zero feedback."""
    code = REASON_T0_CORPUS_EMPTY


class SourceIntegrityError(FeedbackStreamError):
    code = REASON_SOURCE_INTEGRITY


class ImmutableOutputConflict(FeedbackStreamError):
    code = REASON_IMMUTABLE_CONFLICT


def _canon_bytes(value: Any) -> bytes:
    return bas.canonical_bytes(value)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_digest() -> str:
    """Digest of every module whose behaviour defines the artifact; any change invalidates reuse."""
    names = ("prospective_decision_outcome_feedback", "integrated_decision_prospective_feedback",
             "prospective_decision_retention", "prospective_decision_outcome_measurement",
             "prospective_feedback_streaming", "bounded_artifact_stream", "session_bar_integrity",
             "fundamental_signal_consumption_contract", "governed_session_chain", "prospective_pit_capture_retention",
             "daily_session_level2_package")
    digest = hashlib.sha256()
    for name in names:
        # Preserve historical hash labels, but resolve the relocated implementation.
        module = import_module("stocklookup_core.financial." + name
                               if name == "fundamental_signal_consumption_contract" else name)
        path = Path(module.__file__)
        digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest())
    return digest.hexdigest()


def _atomic_write_json(path: Path, value: Any, *, allow_nan: bool = True) -> None:
    """Best-effort derived state; never authoritative, never partially visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=allow_nan).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=TEMP_PREFIX + "state-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _read_state_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > RECEIPT_MAX_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


class _HashingBinary(io.RawIOBase):
    """Raw reader that hashes exactly the bytes handed to the JSON parser (no TOCTOU between proof and use)."""

    def __init__(self, path: Path):
        self._file = open(path, "rb", buffering=0)
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        count = self._file.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
            self.bytes_read += count
        return count

    def close(self) -> None:
        try:
            self._file.close()
        finally:
            super().close()

    def drain(self) -> None:
        while self.readinto(bytearray(1 << 20)):
            pass


class _HashedStream:
    """Context manager: text view over a hashing reader. ``finish()`` drains and returns (sha256, size)."""

    def __init__(self, path: Path):
        self.raw = _HashingBinary(path)
        self.text = io.TextIOWrapper(io.BufferedReader(self.raw, buffer_size=1 << 20), encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.text.close()
        return False

    def finish(self) -> tuple[str, int]:
        # Anything the parser did not request (trailing whitespace) is still part of the proven bytes.
        self.raw.drain()
        return self.raw.digest.hexdigest(), self.raw.bytes_read


def _metric(metrics: dict[str, Any] | None, key: str, amount: int | float = 1) -> None:
    if metrics is not None:
        metrics[key] = metrics.get(key, 0) + amount


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _refuse_reparse(path: Path) -> None:
    """Refuse to create, traverse or delete through a symlink, junction or reparse point."""
    cursor = Path(path)
    while True:
        if path_has_reparse_point(cursor):
            raise FeedbackStreamError("FEEDBACK_REPARSE_POINT_REFUSED:" + str(cursor))
        parent = cursor.parent
        if parent == cursor:
            return
        cursor = parent


def _admitted_source_paths(root: Path, state_root: Path) -> tuple[set[Path], set[Path]]:
    """Paths the seed and the Daily discovery admit. Classification does not write receipts."""

    def t0_loader(path: Path):
        if path_has_reparse_point(path):
            return None
        sha = _receipt_sha_for_same_file(state_root, "t0", path)
        receipt = _read_state_json(_receipt_path(state_root, sha)) if sha else None
        if receipt and receipt.get("source_sha256") == sha and receipt.get("code_digest") == _verification_code_digest():
            return _handle_from_t0_receipt(path, receipt)
        return load_snapshot_handle(path, state_root, None, persist_receipts=False)

    def legacy_loader(path: Path, metrics: dict[str, Any] | None):
        if path_has_reparse_point(path):
            return None
        sha = _receipt_sha_for_same_file(state_root, "legacy", path)
        receipt = _read_state_json(_legacy_receipt_path(state_root, sha)) if sha else None
        if receipt and receipt.get("source_sha256") == sha:
            handle = SourceHandle(receipt["header"])
            handle["records"] = StreamedRecords(path, receipt["record_count"], "legacy")
            handle.valid, handle.raw_sha256, handle.size, handle.path = True, sha, receipt["size"], Path(path)
            return handle
        return scan_legacy_artifact(path, metrics, state_root, persist_receipts=False)

    corpus = fb.discover_prospective_corpus(
        root, payload_projection=lambda artifact: artifact, use_summary_cache=True, cache_metrics={},
        artifact_loader=legacy_loader, cache_root=state_root)
    modern = retention.discover_snapshots(
        root, payload_projection=lambda snapshot: snapshot, snapshot_loader=t0_loader,
        snapshot_validator=lambda snapshot: bool(getattr(snapshot, "valid", False)))
    t0 = {(root / row["inventory"]["snapshot_path"]).resolve() for row in modern["genuine_snapshots"]}
    legacy = {(root / row["artifact_path"]).resolve() for row in corpus["genuine_artifacts"]}
    return t0, legacy


def scrub_sources(root: str | Path, state_root: str | Path) -> dict[str, Any]:
    """Re-hash the sources discovery admits and compare each with its receipt.

    A source outside that set is ``scrub_out_of_scope`` and does not fail the run.
    ``RECEIPT_MISSING`` is an in-scope source with no receipt. ``RECEIPT_MISMATCH`` is a
    receipt whose SHA-256 or size differs. A match refreshes ``verified_at``. Nothing is published.
    """
    root, state_root = Path(root), Path(state_root)
    _refuse_reparse(state_root)
    metrics: dict[str, Any] = {
        "scrub_sources": 0, "scrub_clean": 0, "scrub_mismatches": 0, "scrub_bytes": 0, "scrub_verified_at": 0,
        "scrub_out_of_scope": 0,
    }
    mismatches: list[str] = []
    out_of_scope: list[dict[str, str]] = []

    def note(path: Path, detail: str) -> None:
        mismatches.append(str(path) + ":" + detail)
        _metric(metrics, "scrub_mismatches")

    def refresh(kind: str, path: Path, receipt_file: Path, receipt: dict[str, Any], raw: str, fingerprint) -> None:
        receipt["verified_at"] = _now_utc()
        receipt["content_verified"] = True
        try:
            _atomic_write_json(receipt_file, receipt)
            _bind_fingerprint(state_root, kind, fingerprint, raw)
        except (OSError, FeedbackStreamError) as exc:
            note(path, "RECEIPT_REFRESH_FAILED:" + type(exc).__name__)
            return
        _metric(metrics, "scrub_clean")
        _metric(metrics, "scrub_verified_at")

    def check(kind: str, path: Path, receipt_for) -> None:
        _metric(metrics, "scrub_sources")
        if path_has_reparse_point(path):
            note(path, "REPARSE_POINT")
            return
        fingerprint = source_file_fingerprint(path)
        try:
            raw = bas.source_hash(path)
            size = path.stat().st_size
        except OSError as exc:
            note(path, "UNREADABLE:" + type(exc).__name__)
            return
        _metric(metrics, "scrub_bytes", size)
        anchor = _read_state_json(_fingerprint_index_path(state_root, kind, fingerprint)) if fingerprint else None
        receipt, receipt_file = None, None
        looked: list[str] = []
        if anchor and isinstance(anchor.get("source_sha256"), str):
            looked.append(anchor["source_sha256"])
        if raw not in looked:
            looked.append(raw)
        same_file = _receipt_sha_for_same_file(state_root, kind, path)
        if same_file and same_file not in looked:
            looked.append(same_file)
        for sha in looked:
            candidate = receipt_for(state_root, sha)
            found = _read_state_json(candidate)
            if found:
                receipt, receipt_file = found, candidate
                break
        if receipt is None or receipt_file is None:
            note(path, "RECEIPT_MISSING")
            return
        if (receipt.get("contract_version") != STREAM_CONTRACT_VERSION or receipt.get("source_sha256") != raw
                or receipt.get("size") != size):
            note(path, "RECEIPT_MISMATCH")
            return
        if kind == "t0" and receipt.get("code_digest") != _verification_code_digest():
            note(path, "VERIFIER_DIGEST_MISMATCH")
            return
        refresh(kind, path, receipt_file, receipt, raw, fingerprint)

    from retained_evidence_catalog import historical_paths
    wide_t0 = list(historical_paths(root, "operations-review/prospective-decision-retention-v1", "*/*/prospective_decision_snapshot.json"))
    wide_legacy = list(fb._artifact_paths(root))
    reparse = {path.resolve() for path in [*wide_t0, *wide_legacy] if path_has_reparse_point(path)}
    for path in [*wide_t0, *wide_legacy]:
        if path.resolve() in reparse:
            note(path, "REPARSE_POINT")
    admitted_t0, admitted_legacy = _admitted_source_paths(root, state_root)

    def consider(kind: str, path: Path, admitted: set[Path], receipt_for) -> None:
        resolved = path.resolve()
        if resolved in reparse:
            return
        if resolved not in admitted:
            out_of_scope.append({"path": str(path), "kind": kind, "status": "scrub_out_of_scope"})
            _metric(metrics, "scrub_out_of_scope")
            return
        check(kind, path, receipt_for)

    for path in wide_t0:
        consider("t0", path, admitted_t0, _receipt_path)
    for path in wide_legacy:
        consider("legacy", path, admitted_legacy, _legacy_receipt_path)
    if mismatches:
        raise SourceIntegrityError(REASON_SOURCE_INTEGRITY + ":" + ";".join(mismatches[:30]))
    return {"metrics": metrics, "mismatches": [], "out_of_scope": out_of_scope}


def _verification_code_digest() -> str:
    """Verifier unit only. Evaluator edits in this module do not change it.

    Looked up on the module so a test can replace the digest without editing this file.
    """
    return source_verifier.verification_code_digest()


def iter_legacy_records(handle: SourceHandle) -> Iterator[tuple[str, Any]]:
    """Yield ``(ticker, decision)`` in file order, proving the exact bytes equal the header-scan hash."""
    expected_sha, expected_size, expected_count = handle.raw_sha256, handle.size, len(handle["records"])
    seen = 0
    with _HashedStream(handle.path) as stream:
        parser = bas.ObjectStream(stream.text, sorted_required=False)
        for key in parser.members():
            if key == "records":
                previous = None
                for ticker in parser.members():
                    if previous is not None and ticker <= previous:
                        raise FeedbackStreamError("LEGACY_RECORDS_NOT_SORTED_FOR_STREAMING:" + str(handle.path))
                    previous = ticker
                    seen += 1
                    yield ticker, parser.value()
            else:
                parser.value()
        digest, size = stream.finish()
    if digest != expected_sha or size != expected_size or seen != expected_count:
        raise SourceIntegrityError(REASON_INCOMPLETE_INPUT_CHANGED + ":" + str(handle.path))


def iter_snapshot_records(handle: SourceHandle) -> Iterator[tuple[str, Any]]:
    """Yield ``(ticker, retained_record)`` in sorted order, proving the exact bytes equal the verified hash."""
    expected_sha, expected_size, expected_count = handle.raw_sha256, handle.size, len(handle["records"])
    seen = 0
    with _HashedStream(handle.path) as stream:
        parser = bas.ObjectStream(stream.text, sorted_required=False)
        for key in parser.members():
            if key == "records":
                previous = None
                for ticker in parser.members():
                    if previous is not None and ticker <= previous:
                        raise FeedbackStreamError("T0_RECORDS_NOT_SORTED_FOR_STREAMING:" + str(handle.path))
                    previous = ticker
                    seen += 1
                    yield ticker, parser.value()
            else:
                parser.value()
        digest, size = stream.finish()
    if digest != expected_sha or size != expected_size or seen != expected_count:
        raise SourceIntegrityError(REASON_INCOMPLETE_INPUT_CHANGED + ":" + str(handle.path))


# --------------------------------------------------------------------------------------------------
# Exact-session price snapshots: compact, same-session-only observation index
# --------------------------------------------------------------------------------------------------

class PriceIndex:
    """Compact stand-in for the P3F9B exact-session snapshots the forward bridge reads.

    ``retained_session_price_observations`` and ``evaluate_serialized_close_condition`` only ever consume
    the observation(s) whose ``session`` equals the snapshot's own expected session, so that subset (all
    matches, so the ``len(matches) != 1`` rule is preserved) is exactly sufficient.
    """

    def __init__(self, state_root: Path, metrics: dict[str, Any] | None = None):
        self.state_root, self.metrics = Path(state_root), metrics
        self.sources: dict[str, dict[str, Any]] = {}
        self._content_hash: dict[str, str] = {}

    def _file(self, session: str, raw_sha: str) -> Path:
        return self.state_root / STATE_DIR / "price_index" / f"{session}-{raw_sha[:32]}.json"

    def _remember(self, path: Path, session: str, raw_sha: str, size: int, content_sha: str | None = None) -> None:
        self.sources[session] = {"path": Path(path), "raw_sha256": raw_sha, "size": size}
        if content_sha:
            self._content_hash[session] = content_sha

    def _snapshot_from_index(self, index_path: Path, raw_sha: str, size: int, session: str) -> dict[str, Any] | None:
        cached = _read_state_json(index_path)
        if (cached and cached.get("contract_version") == STREAM_CONTRACT_VERSION and cached.get("source_sha256") == raw_sha
                and cached.get("size") == size and cached.get("session") == session and isinstance(cached.get("snapshot"), dict)):
            return cached
        return None

    def load(self, path: Path, session: str) -> dict[str, Any] | None:
        """Fingerprint hit reads the snapshot from the index file. A missing or disagreeing index hashes the file."""
        fingerprint = source_file_fingerprint(path)
        anchored = _trusted_anchored_receipt(self.state_root, "price", fingerprint, _price_receipt_path)
        if (anchored and anchored.get("session") == session and anchored.get("size") == (fingerprint or {}).get("size")
                and isinstance(anchored.get("source_sha256"), str) and "snapshot" not in anchored):
            index_rel = anchored.get("index_file")
            index_path = Path(index_rel) if isinstance(index_rel, str) and Path(index_rel).is_absolute() else (
                self.state_root / index_rel if isinstance(index_rel, str) else self._file(session, anchored["source_sha256"]))
            cached = self._snapshot_from_index(index_path, anchored["source_sha256"], int(anchored["size"]), session)
            if cached is not None:
                _metric(self.metrics, "price_fingerprint_hits")
                _metric(self.metrics, "price_index_hits")
                self._remember(path, session, anchored["source_sha256"], int(anchored["size"]), anchored.get("content_sha256"))
                return cached["snapshot"]
        _metric(self.metrics, "price_fingerprint_misses")
        try:
            raw_sha = bas.source_hash(path)
            size = path.stat().st_size
        except OSError:
            return None
        _metric(self.metrics, "stream_sha256_bytes", size)
        _metric(self.metrics, "price_hash_bytes", size)
        index_path = self._file(session, raw_sha)
        cached = self._snapshot_from_index(index_path, raw_sha, size, session)
        if cached is not None:
            _metric(self.metrics, "price_index_hits")
            snapshot = cached["snapshot"]
        else:
            snapshot = self._build(path, session)
            _metric(self.metrics, "price_index_misses")
            _metric(self.metrics, "stream_parsed_bytes", size)
            cached = None
        if snapshot is not None:
            content_sha = cached.get("content_sha256") if isinstance(cached, dict) else None
            index_body = {"contract_version": STREAM_CONTRACT_VERSION, "source_sha256": raw_sha, "size": size,
                          "session": session, "snapshot": snapshot}
            receipt = {"contract_version": STREAM_CONTRACT_VERSION, "source_sha256": raw_sha, "size": size,
                       "session": session, "index_file": index_path.relative_to(self.state_root).as_posix()}
            if isinstance(content_sha, str):
                index_body["content_sha256"] = content_sha
                receipt["content_sha256"] = content_sha
            try:
                _atomic_write_json(index_path, index_body, allow_nan=True)
                _atomic_write_json(_price_receipt_path(self.state_root, raw_sha), receipt, allow_nan=True)
                _bind_fingerprint(self.state_root, "price", fingerprint, raw_sha)
            except (OSError, FeedbackStreamError):
                pass
        else:
            receipt = {}
        self._remember(path, session, raw_sha, size, receipt.get("content_sha256") if snapshot is not None else None)
        return snapshot

    def _build(self, path: Path, session: str) -> dict[str, Any] | None:
        header: dict[str, Any] = {}
        records: dict[str, Any] = {}
        try:
            with _HashedStream(path) as stream:
                parser = bas.ObjectStream(stream.text, sorted_required=False)
                for key in parser.members():
                    if key == "records":
                        for ticker in parser.members():
                            row = parser.value()
                            record = row if isinstance(row, Mapping) else {}
                            observations = [o for o in (record.get("observations") or [])
                                            if isinstance(o, Mapping) and o.get("session") == session]
                            records[ticker] = {"observations": observations}
                    else:
                        header[key] = parser.value()
                if parser.peek():
                    return None
                stream.finish()
        except (OSError, UnicodeError, ValueError):
            return None
        if header.get("resolved_completed_session") != session or not isinstance(header.get("snapshot_identity"), str):
            return None
        return {"resolved_completed_session": header["resolved_completed_session"],
                "snapshot_identity": header["snapshot_identity"], "records": records}

    def content_hash(self, session: str) -> str:
        """Hash of the *complete* source snapshot (only needed for terminal settled-cache proofs)."""
        if session in self._content_hash:
            return self._content_hash[session]
        source = self.sources[session]
        cache_file = self._file(session, source["raw_sha256"])
        cached = _read_state_json(cache_file) or {}
        if cached.get("content_sha256"):
            self._content_hash[session] = cached["content_sha256"]
            return cached["content_sha256"]
        _meta, digest, _count = bas.stream_artifact(source["path"], excluded=set(), on_record=lambda t, r: None)
        _metric(self.metrics, "price_content_hash_bytes", source["size"])
        if cached:
            cached["content_sha256"] = digest
            try:
                _atomic_write_json(cache_file, cached, allow_nan=True)
                receipt_file = _price_receipt_path(self.state_root, source["raw_sha256"])
                receipt = _read_state_json(receipt_file)
                if receipt:
                    receipt["content_sha256"] = digest
                    _atomic_write_json(receipt_file, receipt, allow_nan=True)
            except (OSError, FeedbackStreamError):
                pass
        self._content_hash[session] = digest
        return digest


class _DiskSettledStore:
    """Disk-backed settled contributions, one content-keyed file per entry; nothing accumulates in memory.

    Every entry is still validated by ``SettledFeedbackCache.evaluate`` (binding, prefix proof,
    contribution identity, terminal session), so an unreadable or torn file is only a miss.
    The legacy single-file cache is read as a seed and never rewritten here.
    """

    def __init__(self, directory: Path, seed: Mapping[str, Any]):
        self.directory, self.seed = directory, seed

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / (key + ".json")

    def get(self, key, default=None):
        if key in self.seed:
            return self.seed[key]
        try:
            path = self._path(key)
            if path.stat().st_size > 16 * 1024**2:
                return default
            value = json.loads(path.read_bytes())
        except (OSError, ValueError, UnicodeError):
            return default
        return value if isinstance(value, dict) else default

    def __setitem__(self, key, value) -> None:
        path = self._path(key)
        if self.get(key) == value:
            return
        try:
            _atomic_write_json(path, value, allow_nan=False)
        except OSError:
            pass  # a cache write failure only costs a later recomputation


class _StreamSettledCache(fb.SettledFeedbackCache):
    """Existing terminal-only cache; only the snapshot content proof is sourced from the file, not a resident object."""

    def __init__(self, *args, content_hash: Callable[[str, Any], str], **kwargs):
        self._external_content_hash = content_hash
        super().__init__(*args, **kwargs)
        # Write-through to disk instead of the 8,192-entry in-memory working set.
        # Older contributions did not bind evaluator bytes. Never seed a new evaluator from them.
        self.entries = self.retained = _DiskSettledStore(self.root / SETTLED_STORE_DIR / code_digest(), {})

    def _snapshot_content_hash(self, session, snapshot):
        return self._external_content_hash(session, snapshot)

    def terminal_through(self, row):
        """Public terminal session. A partial row returns None and is never reused as final."""
        return self._terminal(row)

    def finish(self):
        return  # every contribution was persisted when it settled


class _PartitionDependencies:
    """Sufficient input identities after native discovery/qualification, never session labels alone.

    Legacy feedback reads bounded returns/diagnostics plus potentially unbounded conditions. Only
    the standing terminal predicate proves extension cannot change any of these fields. Strict
    prospective chains fail closed to their full capture/calendar context (no sparse-prefix reuse).
    """

    def __init__(self, sources, settled, marker, future_inputs, code, contracts):
        self.sources, self.settled, self.marker = sources, settled, marker
        self.price_hashes = {s: fb._settled_hash(v) for s, v in settled.snapshots.items()}
        self.context = {"chain": list(settled.chain), "prices": self.price_hashes}
        self.future_inputs, self.code, self.contracts = future_inputs, code, contracts

    def future(self, session):
        return bool(self.marker) and session >= self.marker["session"]

    def source_key(self, session):
        bound = []
        for source in self.sources[session]:
            candidate = source["candidate"]
            handle = candidate["snapshot" if source["kind"] == "modern" else "artifact"]
            bound.append({"kind": source["kind"], "header": {k: v for k, v in handle.items() if k != "records"},
                          "sha256": handle.raw_sha256, "bytes": handle.size,
                          "qualification": candidate.get("inventory", candidate.get("temporal")),
                          "path": candidate.get("artifact_path")})
        return fb._settled_hash({"contract": PARTITION_CONTRACT_VERSION, "code": self.code,
                                "contracts": self.contracts, "sources": bound,
                                "route": "STRICT_PROSPECTIVE" if self.future(session) else "LEGACY"})

    def context_key(self, session):
        return fb._settled_hash({"legacy": self.context,
                                "future": self.future_inputs if self.future(session) else None})

    def proof(self, through):
        if through not in self.settled.chain:
            return None
        prefix = self.settled.chain[:self.settled.chain.index(through) + 1]
        return {"through": through, "chain": prefix, "prices": {s: self.price_hashes.get(s) for s in prefix}}

    def extension_valid(self, proof):
        """Returns/diagnostics stop at T20; open condition queries must still produce equal events.

        A serialized condition can remain open forever. It is never called settled: re-evaluating
        its exact small query against current observations proves whether the old row can survive.
        """
        if (not isinstance(proof, dict) or not isinstance(proof.get("window"), dict)
                or not isinstance(proof.get("conditions"), list)
                or proof["window"] != self.proof(proof["window"].get("through"))):
            return False
        try:
            return all(fb._trigger_invalidation(item["record"], snapshots=self.settled.snapshots,
                                               chain=self.settled.chain) == item["outcome"]
                       for item in proof["conditions"])
        except (KeyError, TypeError, ValueError):
            return False


def _owned_files(directory: Path) -> list[Path]:
    """Files under ``directory``. A symlink, junction or reparse point refuses instead of being followed."""
    directory = Path(directory)
    if not directory.exists():
        return []
    _refuse_reparse(directory)
    found: list[Path] = []
    stack = [directory]
    while stack:
        current = stack.pop()
        _refuse_reparse(current)
        for child in current.iterdir():
            if path_has_reparse_point(child):
                raise FeedbackStreamError("FEEDBACK_REPARSE_POINT_REFUSED:" + str(child))
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                found.append(child)
    return found


def _prune_derived(directory, *, max_bytes, max_entries, protected=(), strict=True):
    """Bound only rebuildable module-owned state; active files are pinned through final assembly.

    ``strict`` is the settled-store and partition behaviour: a pinned set that itself exceeds the
    budget fails the build. The evaluator-input cache passes ``strict=False`` and only evicts
    unpinned files, because that store is rebuildable and must not fail feedback.
    """
    files = sorted(_owned_files(directory), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    pinned = set(protected)
    total, count = 0, 0
    for path in sorted(files, key=lambda p: p not in pinned):
        size = path.stat().st_size
        if path not in pinned and (total + size > max_bytes or count >= max_entries):
            path.unlink(missing_ok=True)
        else:
            total += size
            count += 1
    if strict and (total > max_bytes or count > max_entries):
        raise FeedbackStreamError("FEEDBACK_CHECKPOINT_STORAGE_LIMIT")


class _Partitions:
    """Content-keyed session variants shared across runs; selected segments are never recopied."""

    def __init__(self, state_root: Path, dependencies, metrics=None):
        self.base = state_root / PARTITION_DIR
        self.directory = self.base / "v2"
        self.dependencies, self.metrics, self.selected = dependencies, metrics, {}
        self.directory.mkdir(parents=True, exist_ok=True)

    def prune_other_runs(self):
        # Preserve recent V1 progress, without treating its corpus identity as a V2 proof.
        legacy = sorted((p for p in self.base.iterdir() if p.is_dir() and len(p.name) == 64),
                        key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for path in legacy[3:]:
            shutil.rmtree(path)
        _prune_derived(self.directory, max_bytes=PARTITION_STORE_MAX_BYTES,
                       max_entries=PARTITION_STORE_MAX_ENTRIES * 3)

    def _candidates(self, session):
        source = self.dependencies.source_key(session)
        directory = self.directory / source
        return directory, sorted(directory.glob("*.partition.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)

    def _valid_bytes(self, stem, value):
        try:
            for kind in ("rows", "trigger"):
                path = Path(str(stem) + "." + kind)
                size = path.stat().st_size
                if size > PARTITION_MAX_BYTES or size != value[kind]["bytes"] or bas.source_hash(path) != value[kind]["sha256"]:
                    return False
            return isinstance(value["row_count"], int) and value["row_count"] >= 0
        except (OSError, KeyError, TypeError):
            return False

    def manifest(self, position, session):
        directory, candidates = self._candidates(session)
        for path in candidates:
            value = _read_state_json(path)
            if not value:
                path.unlink(missing_ok=True)
                continue
            body = {k: v for k, v in value.items() if k != "manifest_sha256"}
            if (value.get("manifest_sha256") != fb._settled_hash(body)
                    or value.get("contract_version") != PARTITION_CONTRACT_VERSION
                    or value.get("source_key") != directory.name or value.get("session") != session):
                path.unlink(missing_ok=True)
                _metric(self.metrics, "partitions_corrupt")
                continue
            exact = value.get("context_key") == self.dependencies.context_key(session)
            proof = value.get("terminal_proof")
            terminal = (not self.dependencies.future(session) and isinstance(proof, dict)
                        and proof == self.dependencies.proof(proof.get("through")))
            extension = (not exact and not terminal and not self.dependencies.future(session)
                         and self.dependencies.extension_valid(value.get("extension_proof")))
            if not (exact or terminal or extension):
                _metric(self.metrics, "partition_variants_invalidated")
                continue
            stem = Path(str(path)[:-len(".partition.json")])
            if not self._valid_bytes(stem, value):
                path.unlink(missing_ok=True)
                _metric(self.metrics, "partitions_corrupt")
                continue  # recover within this invocation; never publish bad bytes
            self.selected[session] = stem
            os.utime(path, None)
            _metric(self.metrics, "partitions_reused_exact" if exact else
                    "partitions_reused_terminal" if terminal else "partitions_reused_extension")
            return value
        if candidates:
            _metric(self.metrics, "partitions_invalidated")
        return None

    def prior_manifest(self, session: str) -> dict[str, Any] | None:
        """Newest intact variant that this run did not select. Row reuse reads it when the partition is rebuilt."""
        directory, candidates = self._candidates(session)
        if not directory.exists():
            return None
        for path in candidates:
            value = _read_state_json(path)
            if not value or value.get("session") != session or value.get("source_key") != directory.name:
                continue
            stem = Path(str(path)[:-len(".partition.json")])
            if stem == self.selected.get(session) or not self._valid_bytes(stem, value):
                continue
            found = dict(value)
            found["_stem"] = stem
            return found
        return None

    def read_rows(self, manifest: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        stem = manifest.get("_stem")
        if not isinstance(stem, Path):
            return
        path = Path(str(stem) + ".rows")
        raw = path.read_bytes()
        if len(raw) != manifest["rows"]["bytes"] or _sha256_bytes(raw) != manifest["rows"]["sha256"]:
            return
        text, decoder, index = raw.decode("utf-8"), json.JSONDecoder(), 0
        del raw
        while index < len(text):
            value, index = decoder.raw_decode(text, index)
            if isinstance(value, dict):
                yield value
            if index < len(text):
                if text[index] != ",":
                    return
                index += 1

    def build(self, position, session, rows):
        directory, _ = self._candidates(session)
        directory.mkdir(parents=True, exist_ok=True)
        context = self.dependencies.context_key(session)
        stem = directory / context
        spools = {kind: _Spool(directory, f"{context}-{kind}-{os.getpid()}") for kind in ("rows", "trigger")}
        through, terminal = None, not self.dependencies.future(session)
        window_through, bounded, conditions = None, not self.dependencies.future(session), []
        try:
            for row in rows:
                spools["rows"].append(row)
                spools["trigger"].append(row["trigger_invalidation_outcome"] | {"feedback_identity": row["feedback_identity"], "ticker": row["ticker"]})
                if terminal:
                    last = self.dependencies.settled.terminal_through(row)
                    terminal = last is not None
                    through = max(through or last, last) if last else None
                if bounded:
                    start = row["forward_outcomes"]["as_of_session"]
                    chain = self.dependencies.settled.chain
                    last_index = chain.index(start) + max(forward_bridge.FORWARD_HORIZONS.values()) if start in chain else len(chain)
                    bounded = last_index < len(chain)
                    if bounded:
                        window_through = max(window_through or chain[last_index], chain[last_index])
                        if any(isinstance((row.get(role) or {}).get("condition"), Mapping) for role in ("trigger", "invalidation")):
                            conditions.append({"record": {"ticker": row["ticker"], "as_of_session": start,
                                                           "trigger": row["trigger"], "invalidation": row["invalidation"]},
                                               "outcome": row["trigger_invalidation_outcome"]})
                _metric(self.metrics, "rows")
            entry = {"contract_version": PARTITION_CONTRACT_VERSION, "source_key": directory.name,
                     "context_key": context, "session": session, "row_count": spools["rows"].count,
                     "future_inputs_digest": fb._settled_hash(self.dependencies.future_inputs) if self.dependencies.future(session) else None,
                     "terminal_proof": self.dependencies.proof(through) if terminal and through else None,
                     "extension_proof": {"window": self.dependencies.proof(window_through), "conditions": conditions}
                                        if bounded and window_through and not terminal else None}
            # A stale manifest must not survive replacement of either data file after a crash.
            manifest_path = Path(str(stem) + ".partition.json")
            manifest_path.unlink(missing_ok=True)
            for kind, spool in spools.items():
                spool.file.flush()
                os.fsync(spool.file.fileno())
                spool.close()
                if spool.path.stat().st_size > PARTITION_MAX_BYTES:
                    raise FeedbackStreamError("FEEDBACK_PARTITION_SIZE_LIMIT:" + session)
                entry[kind] = {"bytes": spool.path.stat().st_size, "sha256": bas.source_hash(spool.path)}
                os.replace(spool.path, Path(str(stem) + "." + kind))
            entry["manifest_sha256"] = fb._settled_hash(entry)
            _atomic_write_json(manifest_path, entry, allow_nan=False)
            self.selected[session] = stem
        finally:
            for spool in spools.values():
                spool.remove()
        _metric(self.metrics, "partitions_built")
        return entry

    def finish(self):
        for directory in (p for p in self.directory.iterdir() if p.is_dir()):
            variants = sorted(directory.glob("*.partition.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for path in variants[PARTITION_VARIANTS:]:
                stem = Path(str(path)[:-len(".partition.json")])
                if stem not in self.selected.values():
                    for suffix in (".partition.json", ".rows", ".trigger"):
                        Path(str(stem) + suffix).unlink(missing_ok=True)
        protected = [Path(str(stem) + suffix) for stem in self.selected.values()
                     for suffix in (".partition.json", ".rows", ".trigger")]
        _prune_derived(self.directory, max_bytes=PARTITION_STORE_MAX_BYTES,
                       max_entries=PARTITION_STORE_MAX_ENTRIES * 3, protected=protected)

    def segment(self, position, session, kind):
        return Path(str(self.selected[session]) + "." + kind)

    def rows(self, position: int, session: str, manifest: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """Re-hash the exact partition bytes, then decode its comma-joined rows one at a time."""
        path = self.segment(position, session, "rows")
        raw = path.read_bytes()
        if (len(raw) != manifest["rows"]["bytes"] or _sha256_bytes(raw) != manifest["rows"]["sha256"]
                or bas.source_hash(self.segment(position, session, "trigger")) != manifest["trigger"]["sha256"]):
            self.invalidate(position, session)
            raise FeedbackStreamError("FEEDBACK_PARTITION_INTEGRITY:" + session)
        text, decoder, index, count = raw.decode("utf-8"), json.JSONDecoder(), 0, 0
        del raw
        while index < len(text):
            value, index = decoder.raw_decode(text, index)
            count += 1
            yield value
            if index < len(text):
                if text[index] != ",":
                    raise FeedbackStreamError("FEEDBACK_PARTITION_INTEGRITY:" + session)
                index += 1
        if count != manifest["row_count"]:
            self.invalidate(position, session)
            raise FeedbackStreamError("FEEDBACK_PARTITION_INTEGRITY:" + session)

    def invalidate(self, position: int, session: str) -> None:
        """A partition whose bytes no longer match its manifest is rebuilt by the next run, never reused."""
        Path(str(self.selected[session]) + ".partition.json").unlink(missing_ok=True)


class _Segments:
    """The concatenation of non-empty partition spools in session order is the original single spool."""

    def __init__(self, paths: list[Path], count: int):
        self.paths, self.count = paths, count


# --------------------------------------------------------------------------------------------------
# Aggregation: reduced rows fed to the *original* summary / health functions (parity by construction)
# --------------------------------------------------------------------------------------------------

class _Aggregator:
    def __init__(self):
        self.by_posture: dict[str, list] = defaultdict(list)
        self.by_coherence: dict[str, list] = defaultdict(list)
        self.by_axis: dict[str, list] = defaultdict(list)
        self.false_negatives: list = []
        self.failed_setups: list = []
        self.horizon_coverage: dict[str, Counter] = {name: Counter() for name in forward_bridge.FORWARD_HORIZONS}
        self.required: dict[str, list] = {ticker: [] for ticker in fb.REQUIRED_TICKERS}
        self.health_rows: list = []
        self.tickers: set[str] = set()
        self.count = 0
        self.t5_mature = 0

    def add(self, row: Mapping[str, Any]) -> None:
        self.count += 1
        horizons = row["forward_outcomes"]["horizons"]
        h5 = horizons.get("forward_close_return_5")
        excursion5 = (row["forward_outcomes"].get("close_path_by_horizon") or {}).get("close_excursion_5")
        mini: dict[str, Any] = {"fundamental_decision_policy_version": row.get("fundamental_decision_policy_version"),
                                "forward_outcomes": {"horizons": {}, "close_path_by_horizon": {}}}
        if h5 is not None:
            mini["forward_outcomes"]["horizons"]["forward_close_return_5"] = {"status": h5.get("status"), "return": h5.get("return")}
        if excursion5 is not None:
            mini["forward_outcomes"]["close_path_by_horizon"]["close_excursion_5"] = {
                key: excursion5.get(key) for key in ("status", "CLOSE_MFE", "CLOSE_MAE") if key in excursion5}
        self.by_posture[str(row["research_action_posture"])].append(mini)
        self.by_coherence[str(row["coherence_state"])].append(mini)
        axes = row["evidence_axes"]
        if axes["status"] == fb.FIELD_NOT_RETAINED:
            self.by_axis[fb.FIELD_NOT_RETAINED].append(mini)
        else:
            for name, axis in axes["axis_states"].items():
                self.by_axis[name + ":" + str(axis.get("state"))].append(mini)
        self.false_negatives.extend(fb._false_negatives([row]))
        self.failed_setups.extend(fb._failed_setups([row]))
        for name in forward_bridge.FORWARD_HORIZONS:
            self.horizon_coverage[name][horizons[name]["status"]] += 1
        if row["ticker"] in self.required:
            self.required[row["ticker"]].append(row)
        if horizons["forward_close_return_5"]["status"] == forward_bridge.MATURE:
            self.t5_mature += 1
        self.tickers.add(row["ticker"])
        trigger_condition = ((row.get("trigger") or {}).get("condition") or {})
        invalidation_condition = ((row.get("invalidation") or {}).get("condition") or {})
        self.health_rows.append({
            "temporal_qualification": {"status": (row.get("temporal_qualification") or {}).get("status")},
            "ticker": row.get("ticker"), "decision_session": row.get("decision_session"),
            "decision_identity": row.get("decision_identity"), "t0_snapshot_identity": row.get("t0_snapshot_identity"),
            "forward_outcomes": {"horizons": {name: {k: h.get(k) for k in ("series_fitness", "status", "maturation_state", "future_session")}
                                              for name, h in horizons.items() if isinstance(h, Mapping)}},
            "evidence_axes": {"status": (row.get("evidence_axes") or {}).get("status", fb.FIELD_NOT_RETAINED)},
            "trigger": {"condition": {"status": trigger_condition["status"]} if "status" in trigger_condition else {}},
            "invalidation": {"condition": {"status": invalidation_condition["status"]} if "status" in invalidation_condition else {}},
        })


# --------------------------------------------------------------------------------------------------
# Spooled artifact writer
# --------------------------------------------------------------------------------------------------

class _Spool:
    """Comma-joined canonical compact JSON elements (the exact bytes of a JSON array body)."""

    def __init__(self, directory: Path, name: str):
        self.path = directory / (TEMP_PREFIX + name + ".spool")
        self.file = open(self.path, "wb", buffering=1 << 20)
        self.count = 0

    def append(self, value: Any) -> None:
        if self.count:
            self.file.write(b",")
        self.file.write(_canon_bytes(value))
        self.count += 1

    def close(self) -> None:
        self.file.flush()
        self.file.close()

    def remove(self) -> None:
        try:
            self.file.close()
        except OSError:
            pass
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def _copy_hashing(source: Path, sinks: list[Callable[[bytes], Any]]) -> int:
    total = 0
    with open(source, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            total += len(block)
            for sink in sinks:
                sink(block)
    return total


def _identity_from_header(path: Path) -> str | None:
    """``artifact_identity`` is the first sorted key of both the legacy and the streamed layouts."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096).decode("utf-8", errors="replace")
    except OSError:
        return None
    marker = '"artifact_identity":'
    index = head.find(marker)
    if index < 0:
        return None
    rest = head[index + len(marker):].lstrip()
    if not rest.startswith('"'):
        return None
    end = rest.find('"', 1)
    return rest[1:end] if end > 0 else None


def completion_manifest_path(output: Path) -> Path:
    return output.with_name(output.name + ".complete.json")


def read_completion(output: Path) -> dict[str, Any] | None:
    """A COMPLETE output has a matching manifest whose size and raw hash equal the artifact's current bytes."""
    manifest = _read_state_json(completion_manifest_path(output))
    if not manifest or manifest.get("contract_version") != COMPLETION_CONTRACT_VERSION:
        return None
    try:
        if output.stat().st_size != manifest.get("artifact_size"):
            return None
        if bas.source_hash(output) != manifest.get("artifact_raw_sha256"):
            return None
    except OSError:
        return None
    return manifest


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_incomplete(directory: Path, *, older_than_seconds: float, now: float | None = None) -> list[str]:
    """Remove only this module's own temporaries: those of a dead writer immediately, others once stale."""
    removed = []
    now = time.time() if now is None else now
    try:
        entries = list(directory.iterdir())
    except OSError:
        return removed
    for entry in entries:
        if entry.name.startswith(TEMP_PREFIX) and entry.suffix in {".spool", ".tmp", ".incomplete"}:
            try:
                stem_pid = entry.stem.rsplit("-", 1)[-1]
                has_pid = stem_pid.isdigit()
                dead = has_pid and int(stem_pid) != os.getpid() and not _pid_alive(int(stem_pid))
                # Another target in this directory can have a live writer. Its
                # files are never stale merely because their mtime is old.
                if dead or (not has_pid and now - entry.stat().st_mtime >= older_than_seconds):
                    entry.unlink()
                    removed.append(entry.name)
            except OSError:
                continue
    return removed


# --------------------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------------------

def _completed_chain(repository: Path) -> list[str]:
    operations = fb._operation_manifests(repository)
    qualified = []
    for link in fb._handoff_bundles(repository, operations):
        manifest = (link.get("operation") or {}).get("manifest") or {}
        if (link["producer_completed"] and link["resolved_completed_session"] == link["session"] and
                manifest.get("market_session") == link["session"] and manifest.get("generation_context") == fb._GENUINE_CONTEXT):
            qualified.append(link["session"])
    return sorted(set(qualified))


def _json_file_digest(path: Path) -> str | None:
    try:
        return bas.source_hash(path)
    except OSError:
        return None


def _future_chain_inputs(repository: Path, marker: Mapping[str, Any] | None, as_of: str) -> dict[str, Any]:
    """Conservative identity of everything ``load_chain`` reads; includes the as-of *date* only."""
    if not marker:
        return {"marker": None}
    import prospective_pit_capture_retention as store
    base = repository / store.STORE
    files = sorted((base / "sessions").glob("*.json")) if (base / "sessions").is_dir() else []
    calendar_files = []
    try:
        calendar_files = [p for p in sorted(base.rglob("*.json")) if "calendar" in str(p).lower()]
    except OSError:
        pass
    return {"marker": marker, "as_of_date": as_of[:10],
            "capture_sessions": {p.name: _json_file_digest(p) for p in files},
            "calendar_files": {str(p.relative_to(base)).replace("\\", "/"): _json_file_digest(p) for p in calendar_files}}


def seed_feedback_state(root: str | Path, state_root: str | Path) -> dict[str, Any]:
    """Build receipts, fingerprint anchors and evaluator-input sidecars. Publishes nothing.

    This is the one-time out-of-Daily seed. It does not write a feedback artifact, a completion
    manifest, or a publication lock on an output path. The caller supplies the state root.
    """
    root, state_root = Path(root), Path(state_root)
    if path_has_reparse_point(root) or (state_root.exists() and path_has_reparse_point(state_root)):
        raise FeedbackStreamError("FEEDBACK_REPARSE_POINT_REFUSED:" + str(state_root if state_root.exists() else root))
    state_root.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, Any] = {}
    started = time.perf_counter()
    corpus = fb.discover_prospective_corpus(
        root, payload_projection=lambda artifact: artifact, use_summary_cache=True, cache_metrics=metrics,
        artifact_loader=lambda path, m: scan_legacy_artifact(path, m, state_root), cache_root=state_root)
    modern_discovery = retention.discover_snapshots(
        root, payload_projection=lambda snapshot: snapshot,
        snapshot_loader=lambda path: load_snapshot_handle(path, state_root, metrics),
        snapshot_validator=lambda snapshot: bool(snapshot.valid))
    modern_genuine = modern_discovery["genuine_snapshots"]
    if not modern_genuine and not corpus["genuine_artifacts"]:
        raise T0CorpusEmpty(f"{REASON_T0_CORPUS_EMPTY}:root={root}:t0_inventory={len(modern_discovery['inventory'])}"
                            f":legacy_inventory={len(corpus['inventory'])}")
    protected: list[Path] = []
    for candidate in modern_genuine:
        for _item in _evaluator_inputs(candidate["snapshot"], candidate["inventory"], state_root, metrics, protected):
            pass
    _prune_evaluator_inputs(state_root, protected)
    metrics["evaluator_input_store_bytes"] = _directory_bytes(state_root / EVALUATOR_INPUT_DIR)
    return {"t0_count": len(modern_genuine), "legacy_count": len(corpus["genuine_artifacts"]),
            "elapsed_s": round(time.perf_counter() - started, 3), "metrics": metrics}


def build_streaming_feedback(root: str | Path, output: str | Path, **kwargs) -> dict[str, Any]:
    """Serialize the complete build/reuse transaction, including crash recovery."""
    from feedback_publication_lock import publication_lock
    # Different output paths share derived checkpoints. Hold their own lease through pruning/assembly.
    with publication_lock(output), publication_lock(Path(kwargs.get("state_root") or root) / PARTITION_DIR):
        return _build_streaming_feedback(root, output, **kwargs)


def _build_streaming_feedback(root: str | Path, output: str | Path, *, state_root: str | Path | None = None,
                             metrics: dict[str, Any] | None = None, prior_summary: Mapping[str, Any] | None = None,
                             stale_temp_seconds: float = 6 * 3600) -> dict[str, Any]:
    """Build (or reuse) one feedback artifact. Returns a small structured result; never returns the artifact."""
    root, output = Path(root), Path(output)
    state_root = Path(state_root) if state_root is not None else root
    metrics = metrics if metrics is not None else {}
    clock = time.perf_counter
    phases: dict[str, float] = {}
    started = clock()
    output.parent.mkdir(parents=True, exist_ok=True)
    cleanup_incomplete(output.parent, older_than_seconds=stale_temp_seconds)

    # -- Phase 1: discovery (headers/proofs only; no record payload is resident) ---------------------
    t = clock()
    loader_seconds = {"legacy": 0.0, "t0": 0.0}

    def _timed_legacy(path, metric_sink):
        started = clock()
        try:
            return scan_legacy_artifact(path, metric_sink, state_root)
        finally:
            loader_seconds["legacy"] += clock() - started

    def _timed_t0(path):
        started = clock()
        try:
            return load_snapshot_handle(path, state_root, metrics)
        finally:
            loader_seconds["t0"] += clock() - started

    legacy_started = clock()
    corpus = fb.discover_prospective_corpus(
        root, payload_projection=lambda artifact: artifact, use_summary_cache=True, cache_metrics=metrics,
        artifact_loader=_timed_legacy, cache_root=state_root)
    phases["discovery_legacy_s"] = clock() - legacy_started
    t0_started = clock()
    modern_discovery = retention.discover_snapshots(
        root, payload_projection=lambda snapshot: snapshot,
        snapshot_loader=_timed_t0,
        snapshot_validator=lambda snapshot: bool(snapshot.valid))
    phases["discovery_t0_s"] = clock() - t0_started
    metrics["discovery_legacy_loader_s"] = round(loader_seconds["legacy"], 3)
    metrics["discovery_t0_loader_s"] = round(loader_seconds["t0"], 3)
    metrics["discovery_legacy_other_s"] = round(phases["discovery_legacy_s"] - loader_seconds["legacy"], 3)
    metrics["discovery_t0_other_s"] = round(phases["discovery_t0_s"] - loader_seconds["t0"], 3)
    modern_genuine = modern_discovery["genuine_snapshots"]
    modern_chain = sorted({row["snapshot"].get("session") for row in modern_genuine if isinstance(row["snapshot"].get("session"), str)})
    # Same selection as the original: the first genuine snapshot of a session supplies its sealed T0 closes.
    modern_prices: dict[str, dict[str, Any]] = {}
    for candidate in modern_genuine:
        snapshot = candidate["snapshot"]
        session = snapshot.get("session")
        if not isinstance(session, str) or session in modern_prices:
            continue
        records = {ticker: {"observations": [dict(row)]} for ticker, row in (snapshot.t0_prices or {}).items()}
        modern_prices[session] = {"resolved_completed_session": session,
                                  "snapshot_identity": ((snapshot.get("t0_price_snapshot") or {}).get("snapshot_identity")),
                                  "records": records}
    legacy_chain = corpus["qualified_session_chain"]
    completed_chain = _completed_chain(root)
    chain = sorted(set(completed_chain) | set(legacy_chain) | set(modern_chain))
    phases["discovery_s"] = clock() - t
    if not modern_genuine and not corpus["genuine_artifacts"]:
        # Refuse before any identity, reuse or publication: an empty artifact would be indistinguishable
        # from "no outcome evidence" and would hide a misrouted root (2026-10-22..11-02 Daily runs).
        raise T0CorpusEmpty(f"{REASON_T0_CORPUS_EMPTY}:root={root}:t0_inventory={len(modern_discovery['inventory'])}"
                            f":legacy_inventory={len(corpus['inventory'])}:completed_chain={len(completed_chain)}")

    t = clock()
    prices = PriceIndex(state_root, metrics)
    snapshots: dict[str, Any] = {}
    for session in sorted(set(completed_chain) | set(legacy_chain)):
        if session in modern_prices:
            continue  # modern T0-sealed closes take precedence, exactly as {**completed, **legacy, **modern}
        loaded = prices.load(fb.level2.session_artifact_paths(root, session)["exact_session_snapshot"], session)
        if loaded is not None:
            snapshots[session] = loaded
    snapshots.update(modern_prices)
    phases["price_index_s"] = clock() - t

    from prospective_pit_capture_retention import load_marker, load_chain, io_known_at
    marker = load_marker(root)
    as_of = io_known_at()
    future_chain = load_chain(root, as_of=as_of) if marker else None

    def content_hash(session, snapshot):
        if session in prices.sources:
            return prices.content_hash(session)
        return retention._hash(snapshot)  # modern-derived object is small and was hashed by value originally

    settled = _StreamSettledCache(state_root, chain, snapshots, enabled=True, metrics=metrics, content_hash=content_hash)
    future_settled = _StreamSettledCache(state_root, future_chain, snapshots, enabled=False, metrics=metrics,
                                         content_hash=content_hash) if marker else None

    # -- Input identity (cheap: hashes already taken during discovery) --------------------------------
    code = code_digest()
    # Preserve E4's frozen V1 digest construction. Only explicitly registered
    # storage inputs use the additional reuse domain; historical evidence IDs stay intact.
    from retained_evidence_catalog import load as load_storage_catalog
    if load_storage_catalog(root):
        code = _sha256_bytes(_canon_bytes({"domain": "storage_qualified_feedback_reuse/v1",
            "legacy_code_digest": code, "storage_verifier_digest": _verification_code_digest()}))
    input_manifest = {
        "contracts": {"feedback": fb.CONTRACT_VERSION, "forward": forward_bridge.CONTRACT_VERSION,
                      "retention": retention.CONTRACT_VERSION, "temporal": fb.TEMPORAL_CONTRACT_VERSION,
                      "policy": fb.OUTCOME_POLICY_CONSTANTS, "horizons": forward_bridge.FORWARD_HORIZONS},
        "chain": chain,
        "t0_snapshots": sorted([[str(c["snapshot"].get("snapshot_identity")), c["snapshot"].raw_sha256, c["snapshot"].size]
                                for c in modern_genuine]),
        "snapshot_inventory": [[r.get("snapshot_identity"), r.get("classification")] for r in modern_discovery["inventory"]],
        "legacy_artifacts": sorted([[c["artifact_path"], c["artifact"].raw_sha256, c["artifact"].size] for c in corpus["genuine_artifacts"]]),
        "artifact_inventory": [[r["artifact_path"], r["artifact_identity"], r["classification"], r["record_count"]] for r in corpus["inventory"]],
        "handoff_inventory": modern_discovery["handoff_snapshot_inventory"],
        "price_sources": {s: [v["raw_sha256"], v["size"]] for s, v in sorted(prices.sources.items())},
        "modern_price_sessions": sorted(modern_prices),
        "future_chain": _future_chain_inputs(root, marker, as_of),
    }
    # Data identity only: the same retained inputs keep the same digest across code changes, so FEEDBACK_CALL_RELATION
    # reports what the *evidence* did. Reuse additionally requires an identical code digest (below).
    input_digest = _sha256_bytes(_canon_bytes(input_manifest))
    inputs_summary = {"price_source_sessions": sorted(prices.sources), "chain_sessions": chain, "t0_snapshot_identities": sorted(r[0] for r in input_manifest["t0_snapshots"]),
                      "legacy_artifact_paths": sorted(r[0] for r in input_manifest["legacy_artifacts"]),
                      "artifact_inventory_paths": sorted(r[0] for r in input_manifest["artifact_inventory"]),
                      "input_digest": input_digest}
    relation = relate(prior_summary, inputs_summary)

    # -- Terminal reuse -----------------------------------------------------------------------------
    existing = read_completion(output)
    if existing and existing.get("input_digest") != input_digest:
        raise ImmutableOutputConflict("IMMUTABLE_INPUT_CONFLICT:" + str(output))
    if existing and existing.get("input_digest") == input_digest and existing.get("code_digest") == code:
        phases["total_s"] = clock() - started
        return _result(OUTCOME_ALREADY_COMPLETE, output, existing, inputs_summary, relation, metrics, phases)

    # -- Phase 2: stream rows -> spools, aggregate, then assemble ------------------------------------
    t = clock()
    sources_by_session = _sources_by_session(modern_genuine, corpus["genuine_artifacts"])
    sessions = sorted(sources_by_session)
    dependencies = _PartitionDependencies(sources_by_session, settled, marker, input_manifest["future_chain"],
                                          code, input_manifest["contracts"])
    partitions = _Partitions(state_root, dependencies, metrics)
    partitions.prune_other_runs()
    _prune_derived(state_root / SETTLED_STORE_DIR, max_bytes=SETTLED_STORE_MAX_BYTES,
                   max_entries=SETTLED_STORE_MAX_ENTRIES)
    protected_inputs: list[Path] = []
    final_tmp = output.parent / (TEMP_PREFIX + output.name + f"-{os.getpid()}.incomplete")
    try:
        manifests = []
        partition_seconds: dict[str, float] = {}
        for position, session in enumerate(sessions):
            session_started = clock()
            manifest = partitions.manifest(position, session)
            if manifest is not None:
                _metric(metrics, "partitions_reused")
                _metric(metrics, "rows_reused", manifest["row_count"])
            else:
                prior = partitions.prior_manifest(session)
                reuse = None
                if prior is not None:
                    index = {(row.get("ticker"), row.get("decision_identity")): row for row in partitions.read_rows(prior)}
                    proof = _partition_proof(prior)

                    def reuse(ticker, identity, _index=index, _proof=proof, _dependencies=dependencies,
                              _future=prior.get("future_inputs_digest")):
                        found = _index.get((ticker, identity))
                        if found is not None and _row_is_reusable(found, _dependencies, _proof, _future):
                            return found
                        return None

                    reuse.prior = index  # type: ignore[attr-defined]
                manifest = partitions.build(position, session, _iter_session_rows(
                    sources_by_session[session], settled, future_settled, marker, state_root=state_root,
                    metrics=metrics, protected_inputs=protected_inputs, reuse=reuse))
            partition_seconds[session] = round(clock() - session_started, 3)
            manifests.append(manifest)
        metrics["partition_evaluate_s"] = partition_seconds
        _metric(metrics, "spool_bytes", sum(m["rows"]["bytes"] + m["trigger"]["bytes"] for m in manifests))
        partitions.finish()
        _prune_evaluator_inputs(state_root, protected_inputs)
        _metric(metrics, "evaluator_input_store_bytes", _directory_bytes(state_root / EVALUATOR_INPUT_DIR))
        _prune_derived(state_root / SETTLED_STORE_DIR, max_bytes=SETTLED_STORE_MAX_BYTES,
                       max_entries=SETTLED_STORE_MAX_ENTRIES)
        phases["evaluate_s"] = clock() - t
        settled.finish()
        t = clock()
        aggregate = _Aggregator()
        for position, (session, manifest) in enumerate(zip(sessions, manifests)):
            for row in partitions.rows(position, session, manifest):
                aggregate.add(row)
        phases["aggregate_s"] = clock() - t
        t = clock()
        sections = _sections(corpus, modern_discovery, modern_genuine, legacy_chain, modern_chain, chain,
                             snapshots_sessions=sorted(set(k for k in snapshots if k in legacy_chain) | set(modern_prices)),
                             aggregate=aggregate)
        segments = {kind: _Segments([partitions.segment(p, s, kind) for p, s in enumerate(sessions)],
                                    sum(m["row_count"] for m in manifests)) for kind in ("rows", "trigger")}
        identity, size, raw_sha, record_count = _assemble(final_tmp, sections, segments["rows"], segments["trigger"], metrics)
        phases["assemble_s"] = clock() - t
        outcome = _publish(final_tmp, output, identity, size, raw_sha, aggregate.count, input_digest, code, inputs_summary)
    finally:
        try:
            final_tmp.unlink(missing_ok=True)
        except OSError:
            pass
    phases["total_s"] = clock() - started
    manifest = read_completion(output)
    if manifest is None:
        # An equal-identity artifact written by the original builder has no manifest; adopt it after proof.
        manifest = _adopt_existing(output, identity, size, raw_sha, aggregate.count, input_digest, code, inputs_summary)
    return _result(outcome, output, manifest, inputs_summary, relation, metrics, phases)


def relate(prior: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    """FEEDBACK_CALL_RELATION from deterministic input identities (never from timing)."""
    if not prior:
        return {"relation": "NO_PRIOR", "new_sessions": [], "new_t0_snapshots": []}
    if prior.get("input_digest") == current.get("input_digest"):
        return {"relation": "IDENTICAL", "new_sessions": [], "new_t0_snapshots": []}
    new_sessions = sorted(set(current["chain_sessions"]) - set(prior["chain_sessions"]))
    new_t0 = sorted(set(current["t0_snapshot_identities"]) - set(prior["t0_snapshot_identities"]))
    superset = (set(prior["chain_sessions"]) <= set(current["chain_sessions"]) and
                set(prior["t0_snapshot_identities"]) <= set(current["t0_snapshot_identities"]) and
                set(prior["legacy_artifact_paths"]) <= set(current["legacy_artifact_paths"]))
    return {"relation": "INCREMENTAL" if superset else "DISTINCT", "new_sessions": new_sessions, "new_t0_snapshots": new_t0,
            "inventory_only_delta": sorted(set(current["artifact_inventory_paths"]) - set(prior["artifact_inventory_paths"]))}


def _sources_by_session(modern_genuine, legacy_genuine) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in modern_genuine:
        snapshot = candidate["snapshot"]
        grouped[str(snapshot.get("session"))].append({"kind": "modern", "candidate": candidate})
    for candidate in legacy_genuine:
        grouped[str(candidate["artifact"].get("session"))].append({"kind": "legacy", "candidate": candidate})
    return grouped


def _iter_rows(sources_by_session, settled, future_settled, marker, state_root=None, metrics=None, protected_inputs=None) -> Iterator[dict[str, Any]]:
    for session in sorted(sources_by_session):
        yield from _iter_session_rows(sources_by_session[session], settled, future_settled, marker,
                                      state_root=state_root, metrics=metrics, protected_inputs=protected_inputs)


def _partition_proof(manifest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(manifest, Mapping):
        return None
    proof = manifest.get("terminal_proof")
    if isinstance(proof, dict):
        return proof
    extension = manifest.get("extension_proof")
    if isinstance(extension, dict) and isinstance(extension.get("window"), dict):
        return extension["window"]
    return None


def _row_is_reusable(prior: Mapping[str, Any], dependencies, old_proof: Mapping[str, Any] | None,
                     future_digest: str | None = None) -> bool:
    """Row-level ``extension_valid``. A partially mature row is never final.

    A strict-prospective row is reusable only when the prior manifest recorded the same
    future-input digest. Anything else is evaluated again.
    """
    if not isinstance(old_proof, Mapping):
        return False
    outcomes = prior.get("forward_outcomes") if isinstance(prior.get("forward_outcomes"), Mapping) else {}
    session = outcomes.get("as_of_session")
    if isinstance(session, str) and dependencies.future(session):
        current = fb._settled_hash(dependencies.future_inputs)
        if future_digest != current:
            return False
    try:
        through = dependencies.settled.terminal_through(prior)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    if through is None:
        return False
    current = dependencies.proof(through)
    if not isinstance(current, dict):
        return False
    old_chain = list(old_proof.get("chain") or [])
    old_prices = old_proof.get("prices") or {}
    if current.get("chain") != old_chain[:len(current.get("chain") or [])]:
        return False
    if any(current.get("prices", {}).get(session) != old_prices.get(session) for session in current.get("chain") or []):
        return False
    outcomes = prior.get("forward_outcomes") if isinstance(prior.get("forward_outcomes"), Mapping) else {}
    record = {"ticker": prior.get("ticker"), "as_of_session": outcomes.get("as_of_session"),
              "trigger": prior.get("trigger"), "invalidation": prior.get("invalidation")}
    try:
        outcome = fb._trigger_invalidation(record, snapshots=dependencies.settled.snapshots, chain=dependencies.settled.chain)
    except (KeyError, TypeError, ValueError):
        return False
    return outcome == prior.get("trigger_invalidation_outcome")


def _iter_session_rows(sources, settled, future_settled, marker, state_root=None, metrics=None, protected_inputs=None,
                       reuse=None) -> Iterator[dict[str, Any]]:
    streams = [_source_stream(index, source, state_root=state_root, metrics=metrics, protected_inputs=protected_inputs)
               for index, source in enumerate(sources)]
    for ticker, identity, _index, work in heapq.merge(*streams, key=lambda item: (item[0], item[1])):
        evaluator_choice, kwargs = work
        if reuse is not None:
            cached = reuse(ticker, identity)
            if cached is not None:
                _metric(metrics, "rows_reused_inside_partition")
                yield cached
                continue
        evaluator = future_settled if evaluator_choice(marker) else settled
        row = evaluator.evaluate(**kwargs)
        _metric(metrics, "rows_reevaluated")
        if reuse is not None:
            prior = reuse.prior.get((ticker, identity)) if hasattr(reuse, "prior") else None
            if prior is not None and _canon_bytes(prior) != _canon_bytes(row):
                _metric(metrics, "rows_output_changed")
        yield row


_PROJECTION_DIGEST: str | None = None


def _projection_code_digest() -> str:
    """Digest of the modules that define the evaluator-input projection. A change rebuilds sidecars."""
    global _PROJECTION_DIGEST
    if _PROJECTION_DIGEST is None:
        digest = hashlib.sha256()
        for name in ("prospective_decision_outcome_feedback", "integrated_decision_prospective_feedback",
                     "prospective_feedback_streaming"):
            module = import_module(name)
            digest.update(hashlib.sha256(Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")).digest())
        _PROJECTION_DIGEST = digest.hexdigest()
    return _PROJECTION_DIGEST


def _evaluator_input_paths(state_root: Path, raw_sha: str, projection: str) -> tuple[Path, Path]:
    directory = state_root / EVALUATOR_INPUT_DIR / raw_sha
    return directory / (projection + ".jsonl"), directory / (projection + ".index.json")


def _modern_frame(handle: SourceHandle, inventory: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Any]:
    """Discovery fields and the T0 header. These are not stored in the sidecar."""
    origin = handle.get("source_integrated_decision_artifact") or {}
    artifact = {"session": handle.get("session"), "artifact_identity": origin.get("artifact_identity"),
                "contract_version": origin.get("contract_version", fb.FIELD_NOT_RETAINED), "requested_at": None}
    temporal = {
        "contract_version": fb.TEMPORAL_CONTRACT_VERSION, "status": fb.GENUINE, "decision_session": handle.get("session"),
        "decision_artifact_identity": origin.get("artifact_identity"),
        "daily_session_operation_identity": handle.get("daily_session_operation_identity"),
        "canonical_handoff_path": inventory.get("canonical_handoff_path"),
        "operation_manifest_path": inventory.get("operation_manifest_path"),
        "proof_reason_codes": inventory.get("proof_reason_codes"),
    }
    header = {k: v for k, v in handle.items() if k != "records"}
    return artifact, temporal, header, inventory["snapshot_path"]


def _modern_row(ticker: str, projected_record: Mapping[str, Any], artifact: Mapping[str, Any],
                temporal: Mapping[str, Any], header: Mapping[str, Any], source_path: Any) -> dict[str, Any] | None:
    """One evaluator input. ``record`` is the projected decision stored inside ``projected_record``."""
    decision = projected_record.get("integrated_decision_at_t0")
    if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
        return None
    return {"ticker": ticker, "decision_identity": str(decision.get("decision_identity")),
            "kwargs": {"artifact": artifact, "source_path": source_path, "temporal": temporal,
                       "record": decision, "t0_snapshot": header, "t0_snapshot_record": projected_record}}


# Fields the row evaluator and the assembler read. A sibling that is not copied into the
# feedback row must not change artifact bytes. ``trigger`` and ``invalidation`` are copied whole.
_RECORD_KEEP = (
    "ticker", "as_of_session", "decision_identity", "research_action_posture", "policy_version",
    "fundamental_decision_policy_version", "fundamental_state", "market_structure_state",
    "trigger", "invalidation", "source_identities", "scenario_condition_context", "benchmark",
    "known_at", "target_condition_at_t0", "forward_driver_context_at_t0", "intrinsic_scenario_at_t0",
)
_RECORD_NESTED = {
    "evidence_axis_coherence": ("state",),
    "priority_posture_reconciliation": ("research_priority_tier",),
    "valuation_context_summary": ("status",),
    "momentum_context": ("status",),
    "participation": ("status",),
    "market_sector_context": ("market_regime",),
    "qualified_tactical_signal_at_t0": ("status", "source_identity"),
}
_SNAPSHOT_RECORD_KEEP = ("prospective_snapshot_record_identity", "t0_contract_versions", "known_at", "integrated_decision_at_t0")


def _project_record_minimal(record: Mapping[str, Any]) -> dict[str, Any]:
    """The evaluator projection. Unread siblings of a copied field are omitted."""
    projected = {key: record[key] for key in _RECORD_KEEP if key in record}
    axes = record.get("evidence_axes")
    if isinstance(axes, Mapping):
        projected["evidence_axes"] = {
            str(name): {field: axis[field] for field in ("state", "fitness", "lineage", "method") if field in axis}
            for name, axis in axes.items() if isinstance(axis, Mapping)
        }
    for key, fields in _RECORD_NESTED.items():
        value = record.get(key)
        if isinstance(value, Mapping):
            projected[key] = {field: value[field] for field in fields if field in value}
    return projected


def _project_snapshot_record(retained: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    body = {key: retained[key] for key in _SNAPSHOT_RECORD_KEEP if key in retained and key != "integrated_decision_at_t0"}
    body["integrated_decision_at_t0"] = _project_record_minimal(decision)
    return body


def _modern_input_rows(handle: SourceHandle, inventory: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """The ordered ``(ticker, decision_identity, kwargs)`` stream ``_source_stream`` yields for one T0."""
    artifact, temporal, header, source_path = _modern_frame(handle, inventory)
    for ticker, retained in iter_snapshot_records(handle):
        if not isinstance(retained, Mapping) or not isinstance(retained.get("integrated_decision_at_t0"), Mapping):
            continue
        decision = fb._project_decision_for_feedback(retained["integrated_decision_at_t0"])
        projected_record = _project_snapshot_record(retained, decision)
        row = _modern_row(ticker, projected_record, artifact, temporal, header, source_path)
        if row is not None:
            yield row


def _sidecar_is_valid(path: Path, index: Mapping[str, Any]) -> bool:
    try:
        if path_has_reparse_point(path) or path.stat().st_size != index["bytes"] or index["row_count"] < 0:
            return False
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as source:
            for line in iter(lambda: source.readline(), b""):
                if not line.endswith(b"\n"):
                    return False
                digest.update(line)
                count += 1
        return digest.hexdigest() == index["sha256"] and count == index["row_count"]
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        return False


def _stored_sidecar_row(item: Mapping[str, Any]) -> dict[str, Any]:
    """Persist only T0-derived fields. ``record`` is inside the projected snapshot record."""
    return {"ticker": item["ticker"], "decision_identity": item["decision_identity"],
            "t0_snapshot_record": item["kwargs"]["t0_snapshot_record"]}


def _iter_sidecar_rows(path: Path, handle: SourceHandle, inventory: Mapping[str, Any],
                       metrics: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    artifact, temporal, header, source_path = _modern_frame(handle, inventory)
    with path.open("rb") as source:
        for line in source:
            started = time.perf_counter()
            item = json.loads(line)
            _metric(metrics, "sidecar_json_decode_s", time.perf_counter() - started)
            _metric(metrics, "sidecar_decoded_bytes", len(line))
            projected = item.get("t0_snapshot_record") if isinstance(item, dict) else None
            if not isinstance(projected, dict):
                raise FeedbackStreamError("FEEDBACK_EVALUATOR_INPUT_INTEGRITY")
            row = _modern_row(item.get("ticker"), projected, artifact, temporal, header, source_path)
            if row is None or row["decision_identity"] != item.get("decision_identity"):
                raise FeedbackStreamError("FEEDBACK_EVALUATOR_INPUT_INTEGRITY")
            yield row


def _write_evaluator_sidecar(data_path: Path, index_path: Path, rows: Iterator[dict[str, Any]], raw: str,
                             projection: str, *, budget_remaining: int) -> str:
    """Write the sidecar from a T0 pass. ``over_budget`` installs nothing. Failure leaves no index."""
    temporary = None
    try:
        _refuse_reparse(data_path.parent)
        hasher = hashlib.sha256()
        count = 0
        with tempfile.NamedTemporaryFile(dir=data_path.parent, prefix=TEMP_PREFIX + "evaluator-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            for item in rows:
                line = _canon_bytes(_stored_sidecar_row(item)) + b"\n"
                out.write(line)
                hasher.update(line)
                count += 1
            out.flush()
            os.fsync(out.fileno())
        size = temporary.stat().st_size
        index_value = {
            "contract_version": EVALUATOR_INPUT_CONTRACT, "source_sha256": raw, "projection_digest": projection,
            "sha256": hasher.hexdigest(), "bytes": size, "row_count": count,
        }
        index_payload = json.dumps(index_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if size + len(index_payload) > budget_remaining:
            return "over_budget"
        os.replace(temporary, data_path)
        temporary = None
        _atomic_write_json(index_path, index_value)
        return "written"
    except FeedbackStreamError:
        raise
    except (OSError, ValueError, TypeError):
        return "failed"
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _evaluator_store_occupied(state_root: Path, *excluded: Path) -> int:
    directory = Path(state_root) / EVALUATOR_INPUT_DIR
    if not directory.exists():
        return 0
    skip = set()
    for path in excluded:
        try:
            skip.add(path.resolve())
        except OSError:
            continue
    total = 0
    for path in _owned_files(directory):
        try:
            if path.resolve() in skip:
                continue
        except OSError:
            continue
        total += path.stat().st_size
    return total


def _evaluator_inputs(handle: SourceHandle, inventory: Mapping[str, Any], state_root: Path | None,
                      metrics: dict[str, Any] | None, protected_inputs: list[Path] | None) -> Iterator[dict[str, Any]]:
    raw = handle.raw_sha256
    if state_root is None or not isinstance(raw, str):
        yield from _modern_input_rows(handle, inventory)
        return
    projection = _projection_code_digest()
    data_path, index_path = _evaluator_input_paths(Path(state_root), raw, projection)
    index = _read_state_json(index_path)
    valid = (index and index.get("contract_version") == EVALUATOR_INPUT_CONTRACT and index.get("source_sha256") == raw
             and index.get("projection_digest") == projection and _sidecar_is_valid(data_path, index))
    if not valid:
        if index:
            _metric(metrics, "sidecar_corrupt")
            index_path.unlink(missing_ok=True)
        _metric(metrics, "sidecar_misses")
        try:
            _refuse_reparse(state_root)
            data_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, FeedbackStreamError):
            yield from _modern_input_rows(handle, inventory)
            return
        occupied = _evaluator_store_occupied(Path(state_root), data_path, index_path)
        if occupied >= EVALUATOR_INPUT_MAX_BYTES:
            data_path.unlink(missing_ok=True)
            _metric(metrics, "sidecar_skipped_budget")
            yield from _modern_input_rows(handle, inventory)
            return
        status = _write_evaluator_sidecar(
            data_path, index_path, _modern_input_rows(handle, inventory), raw, projection,
            budget_remaining=EVALUATOR_INPUT_MAX_BYTES - occupied)
        if status != "written":
            data_path.unlink(missing_ok=True)
            index_path.unlink(missing_ok=True)
            if status == "over_budget":
                _metric(metrics, "sidecar_skipped_budget")
            yield from _modern_input_rows(handle, inventory)
            return
        index = _read_state_json(index_path)
        if not index or not _sidecar_is_valid(data_path, index):
            yield from _modern_input_rows(handle, inventory)
            return
        _metric(metrics, "sidecar_bytes_written", index["bytes"])
    else:
        _metric(metrics, "sidecar_hits")
    _metric(metrics, "sidecar_bytes", index["bytes"])
    if protected_inputs is not None:
        protected_inputs.extend((data_path, index_path))
    yield from _iter_sidecar_rows(data_path, handle, inventory, metrics)


def _prune_evaluator_inputs(state_root: Path, protected: list[Path]) -> None:
    directory = Path(state_root) / EVALUATOR_INPUT_DIR
    if not directory.exists():
        return
    _prune_derived(directory, max_bytes=EVALUATOR_INPUT_MAX_BYTES, max_entries=EVALUATOR_INPUT_MAX_ENTRIES,
                   protected=protected, strict=False)


def _directory_bytes(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(path.stat().st_size for path in _owned_files(directory))


def _source_stream(index: int, source: Mapping[str, Any], state_root: Path | None = None,
                   metrics: dict[str, Any] | None = None, protected_inputs: list[Path] | None = None) -> Iterator[tuple[str, str, int, Any]]:
    candidate = source["candidate"]
    if source["kind"] == "modern":
        handle = candidate["snapshot"]
        for item in _evaluator_inputs(handle, candidate["inventory"], state_root, metrics, protected_inputs):
            artifact = item["kwargs"]["artifact"]
            yield item["ticker"], item["decision_identity"], index, (
                lambda marker, a=artifact: bool(marker) and a["session"] >= marker["session"],
                item["kwargs"])
    else:
        handle = candidate["artifact"]
        header = {k: v for k, v in handle.items() if k != "records"}
        for ticker, decision in iter_legacy_records(handle):
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            projected = fb._project_decision_for_feedback(decision)
            yield ticker, str(projected.get("decision_identity")), index, (
                lambda marker, a=header: bool(marker) and a["session"] >= marker["session"],
                {"artifact": header, "source_path": candidate["artifact_path"], "temporal": candidate["temporal"], "record": projected})


def _sections(corpus, modern_discovery, modern_genuine, legacy_chain, modern_chain, chain,
              *, snapshots_sessions, aggregate: _Aggregator) -> dict[str, Any]:
    false_negatives, failed_setups = aggregate.false_negatives, aggregate.failed_setups
    required = {ticker: aggregate.required[ticker] or [{"ticker": ticker, "status": "NO_PROSPECTIVE_CASE"}] for ticker in fb.REQUIRED_TICKERS}
    policy_candidates = [{
        "disposition": "MORE_PROSPECTIVE_EVIDENCE_REQUIRED", "current_rule": "Outcome feedback never mutates current daily posture policy.",
        "observed_prospective_counterexamples": len(false_negatives) + len(failed_setups), "sample_size": aggregate.t5_mature,
        "why_current_rule_may_be_too_restrictive_or_loose": "No mature T5 close-return sample exists in the temporally qualified corpus.",
        "possible_bounded_change": None, "expected_affected_cohort": None, "risk_of_change": "LOOK_AHEAD_OR_THIN_SAMPLE_OVERFIT",
        "evidence_strength": "INSUFFICIENT", "policy_mutated": False,
    }]
    corpus_health = retention.build_corpus_health(snapshot_inventory=modern_discovery, feedback_artifact={"feedback_records": aggregate.health_rows})
    horizon_coverage = {name: dict(sorted(counter.items())) for name, counter in aggregate.horizon_coverage.items()}
    # The inventory rows reference handles only for genuine entries; make them plain data.
    return {
        "schema_version": "1.0.0", "contract_version": fb.CONTRACT_VERSION, "outcome_policy_constants": fb.OUTCOME_POLICY_CONSTANTS,
        "prospective_corpus": {"candidate_artifact_count": len(corpus["inventory"]), "genuine_artifact_count": len(corpus["genuine_artifacts"]),
                               "immutable_snapshot_count": len(modern_discovery["inventory"]), "genuine_immutable_snapshot_count": len(modern_genuine),
                               "genuine_decision_count": aggregate.count, "unique_sessions": sorted(set(legacy_chain) | set(modern_chain)),
                               "unique_tickers": len(aggregate.tickers), "classification_counts": corpus["classification_counts"],
                               "snapshot_classification_counts": modern_discovery["classification_counts"]},
        "temporal_qualification": {"artifact_inventory": corpus["inventory"], "immutable_snapshot_inventory": modern_discovery["inventory"],
                                   "handoff_snapshot_inventory": modern_discovery["handoff_snapshot_inventory"], "qualified_session_chain": chain,
                                   "retained_snapshot_sessions": snapshots_sessions,
                                   "temporal_gate": "LEGACY_CANONICAL_HANDOFF_OR_IMMUTABLE_T0_SNAPSHOT_PLUS_RETAINED_DAILY_OPERATION"},
        "forward_outcome_coverage": {"horizons": horizon_coverage, "close_excursions": {"CLOSE_MFE_CLOSE_MAE_ONLY": True, "intraday_mfe_mae": "NOT_CLAIMED"}},
        "posture_outcome_summary": fb._summary(aggregate.by_posture, dimension="research_action_posture"),
        "coherence_outcome_summary": fb._summary(aggregate.by_coherence, dimension="evidence_axis_coherence"),
        "evidence_axis_outcome_summary": fb._summary(aggregate.by_axis, dimension="evidence_axis_state"),
        "false_negative_cases": false_negatives, "failed_setup_cases": failed_setups,
        "prospective_corpus_health": corpus_health, "policy_diagnostic_candidates": policy_candidates, "required_ticker_cases": required,
        "authority_boundary": {"downstream_observation_only": True, "no_retroactive_recommendation_reconstruction": True, "no_policy_mutation": True,
                               "no_probability_or_calibration": True, "no_raw_as_traded_or_pit_authority": True, "no_daily_decision_feedback_loop": True},
    }


def _assemble(final_tmp: Path, sections: Mapping[str, Any], rows: _Segments, triggers: _Segments, metrics) -> tuple[str, int, str, int]:
    """Write ``{"artifact_identity":…,<canonical members>}`` and hash the canonical members as they are written."""
    placeholder = ARTIFACT_IDENTITY_PREFIX + "0" * 64
    head = b'{"artifact_identity":"' + placeholder.encode() + b'",'
    streamed = {"feedback_records": rows, "trigger_invalidation_outcomes": triggers}
    keys = sorted(set(sections) | set(streamed))
    digest = hashlib.sha256()
    with open(final_tmp, "wb", buffering=1 << 20) as out:
        out.write(head)

        def emit(block: bytes) -> None:
            out.write(block)
            digest.update(block)

        digest.update(b"{")  # the file's opening brace is part of ``head``; the hash needs its own
        for position, key in enumerate(keys):
            if position:
                emit(b",")
            emit(json.dumps(key, ensure_ascii=False).encode("utf-8") + b":")
            if key in streamed:
                emit(b"[")
                written = False
                segments = streamed[key]
                if not isinstance(segments, _Segments) or not segments.paths:
                    # One partition per genuine session; an empty corpus is refused at discovery.
                    raise FeedbackStreamError("FEEDBACK_STREAM_SEGMENTS_MISSING:" + key)
                for path in segments.paths:
                    if path.stat().st_size == 0:
                        continue
                    if written:
                        emit(b",")
                    _copy_hashing(path, [emit])
                    written = True
                emit(b"]")
            else:
                emit(_canon_bytes(sections[key]))
        emit(b"}")
        identity = ARTIFACT_IDENTITY_PREFIX + digest.hexdigest()
        out.seek(len(b'{"artifact_identity":"'))
        out.write(identity.encode())
        out.flush()
        os.fsync(out.fileno())
        size = out.seek(0, os.SEEK_END)
    # Re-read the bytes that reached disk: the identity member plus the hashed body must reproduce the digest.
    check = hashlib.sha256()
    check.update(b"{")
    with open(final_tmp, "rb") as written:
        written.seek(len(head))
        for block in iter(lambda: written.read(1 << 20), b""):
            check.update(block)
    if check.hexdigest() != digest.hexdigest():
        raise FeedbackStreamError("FEEDBACK_OUTPUT_READBACK_MISMATCH")
    raw_sha = bas.source_hash(final_tmp)
    _metric(metrics, "output_bytes", size)
    return identity, size, raw_sha, rows.count


class _ArrayStream(bas.ObjectStream):
    """ObjectStream that can also walk a JSON array element by element (bounded by one element)."""

    def elements(self):
        self.take("[")
        if self.peek() == "]":
            self.take("]")
            return
        while True:
            yield self.value()
            if self.peek() == "]":
                self.take("]")
                return
            self.take(",")


ARRAY_MEMBERS = frozenset({"feedback_records", "trigger_invalidation_outcomes"})


def stream_artifact_identity(path: Path) -> str:
    """Recompute ``artifact_identity`` of a feedback artifact of either layout without materialising it."""
    digest = hashlib.sha256()
    digest.update(b"{")
    first = True
    with open(path, encoding="utf-8") as source:
        parser = _ArrayStream(source, sorted_required=True)
        for key in parser.members():
            included = key != "artifact_identity"
            if included:
                if not first:
                    digest.update(b",")
                first = False
                digest.update(json.dumps(key, ensure_ascii=False).encode("utf-8") + b":")
            if key in ARRAY_MEMBERS:
                if included:
                    digest.update(b"[")
                for position, element in enumerate(parser.elements()):
                    if included:
                        if position:
                            digest.update(b",")
                        digest.update(_canon_bytes(element))
                if included:
                    digest.update(b"]")
            else:
                value = parser.value()
                if included:
                    digest.update(_canon_bytes(value))
        if parser.peek():
            raise ValueError("FEEDBACK_ARTIFACT_TRAILING_JSON")
    digest.update(b"}")
    return ARTIFACT_IDENTITY_PREFIX + digest.hexdigest()


def _publish(final_tmp: Path, output: Path, identity: str, size: int, raw_sha: str, record_count: int,
             input_digest: str, code: str, inputs_summary: Mapping[str, Any]) -> str:
    """Atomic COMPLETE publication. An existing artifact is accepted only if it provably carries the same content."""
    if output.exists():
        completion = read_completion(output)
        if completion is not None and completion.get("artifact_identity") == identity:
            if completion.get("input_digest") != input_digest or completion.get("code_digest") != code:
                # Same proven content under new code or a changed-but-equivalent input set: refresh the manifest so the
                # next identical call reuses the output instead of recomputing it forever.
                _write_completion(output, identity, completion["artifact_size"], completion["artifact_raw_sha256"], record_count,
                                  input_digest, code, inputs_summary)
            return OUTCOME_ALREADY_RETAINED_EQUAL
        existing_sha = bas.source_hash(output)
        equal = existing_sha == raw_sha
        if not equal and _identity_from_header(output) == identity:
            # A same-identity artifact in another layout (the original builder's indent=2 file): prove it by content.
            try:
                equal = stream_artifact_identity(output) == identity
            except (OSError, ValueError):
                equal = False
        if not equal:
            raise ImmutableOutputConflict("IMMUTABLE_ARTIFACT_CONFLICT:" + str(output))
        _write_completion(output, identity, output.stat().st_size, existing_sha, record_count, input_digest, code, inputs_summary)
        return OUTCOME_ALREADY_RETAINED_EQUAL
    # The kernel lease coordinates our writers; hard-link creation also refuses
    # any uncoordinated writer's existing destination. COMPLETE is never replaced.
    try:
        os.link(final_tmp, output)
    except FileExistsError as exc:
        raise ImmutableOutputConflict("IMMUTABLE_ARTIFACT_CONFLICT:" + str(output)) from exc
    _write_completion(output, identity, size, raw_sha, record_count, input_digest, code, inputs_summary)
    return OUTCOME_BUILT


def _write_completion(output: Path, identity, size, raw_sha, record_count, input_digest, code, inputs_summary) -> None:
    manifest = {"contract_version": COMPLETION_CONTRACT_VERSION, "artifact_identity": identity, "artifact_path": output.name,
                "artifact_size": size, "artifact_raw_sha256": raw_sha, "record_count": record_count, "input_digest": input_digest,
                "code_digest": code, "inputs_summary": dict(inputs_summary), "format": "canonical_compact_json"}
    _atomic_write_json(completion_manifest_path(output), manifest, allow_nan=False)


def _adopt_existing(output, identity, size, raw_sha, record_count, input_digest, code, inputs_summary):
    _write_completion(output, identity, output.stat().st_size, bas.source_hash(output), record_count, input_digest, code, inputs_summary)
    return read_completion(output)


def _result(outcome: str, output: Path, manifest: Mapping[str, Any] | None, inputs_summary, relation, metrics, phases) -> dict[str, Any]:
    manifest = manifest or {}
    return {"contract_version": RESULT_CONTRACT_VERSION, "outcome": outcome, "artifact_identity": manifest.get("artifact_identity"),
            "path": str(output), "artifact_size": manifest.get("artifact_size"), "artifact_raw_sha256": manifest.get("artifact_raw_sha256"),
            "record_count": manifest.get("record_count"), "input_digest": inputs_summary["input_digest"],
            "inputs_summary": dict(inputs_summary), "relation": relation, "metrics": dict(metrics),
            "phases_seconds": {k: round(v, 3) for k, v in phases.items()}}
