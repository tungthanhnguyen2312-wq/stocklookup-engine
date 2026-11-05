"""Receipts for feedback sources.

This module produces and reads the cached proof of a T0 or legacy file: the hash,
the header, the record count and the retention validation. It is part of the verifier
digest. The streaming evaluator is not.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

import bounded_artifact_stream as bas
from stocklookup_core.evidence.source_file_fingerprint import path_has_reparse_point

# The streaming module binds these after it imports this file. This module does not
# import back into the Daily cycle; a test patch on the streaming module stays visible.
_retention = None
_streaming = None


def bind_runtime(retention_module, streaming_module) -> None:
    global _retention, _streaming
    _retention = retention_module
    _streaming = streaming_module

STREAM_CONTRACT_VERSION = "prospective_feedback_stream/v1"
STATE_DIR = Path("operations-review/prospective-decision-outcome-feedback-v1/_stream")
_RECEIPT_MAX_BYTES = 64 * 1024 * 1024
_UNSORTED_FALLBACK_MAX_BYTES = 128 * 1024 * 1024
_TEMP_PREFIX = ".feedback-"


class StreamedRecords:
    """Placeholder for a ``records`` container that stays on disk. Supports ``len``/truthiness only."""

    def __init__(self, path: Path, count: int, kind: str):
        self.path, self.count, self.kind = Path(path), int(count), kind

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.count > 0

    def __iter__(self):
        raise TypeError("STREAMED_RECORDS_REQUIRE_EXPLICIT_STREAMING")

    def items(self):
        raise TypeError("STREAMED_RECORDS_REQUIRE_EXPLICIT_STREAMING")


class SourceHandle(dict):
    """Header (every non-record member) plus bookkeeping for one streamed source file."""
    valid = True
    raw_sha256 = None
    size = None
    path = None
    t0_prices: Mapping[str, Any] | None = None


def _metric(metrics: dict[str, Any] | None, key: str, amount: int | float = 1) -> None:
    if metrics is not None:
        metrics[key] = metrics.get(key, 0) + amount


def _canon_bytes(value: Any) -> bytes:
    return bas.canonical_bytes(value)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verifier_digest() -> str:
    """Honor a test patch on the streaming alias and on the verifier module."""
    return _streaming._verification_code_digest()


def _current_fingerprint(path: Path):
    """Look up the helper on the streaming module so a test patch is visible."""
    return _streaming.source_file_fingerprint(path)


def _raise_stream(message: str) -> None:
    raise _streaming.FeedbackStreamError(message)


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write_json(path: Path, value: Any, *, allow_nan: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=allow_nan).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=_TEMP_PREFIX + "state-", suffix=".tmp", delete=False) as out:
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
        if path.stat().st_size > _RECEIPT_MAX_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


class _HashingBinary(io.RawIOBase):
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
    def __init__(self, path: Path):
        self.raw = _HashingBinary(path)
        self.text = io.TextIOWrapper(io.BufferedReader(self.raw, buffer_size=1 << 20), encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.text.close()
        return False

    def finish(self) -> tuple[str, int]:
        self.raw.drain()
        return self.raw.digest.hexdigest(), self.raw.bytes_read


def _legacy_receipt_path(state_root: Path, raw_sha: str) -> Path:
    return state_root / STATE_DIR / "legacy_receipts" / (raw_sha + ".json")


def _receipt_path(state_root: Path, raw_sha: str) -> Path:
    return state_root / STATE_DIR / "t0_receipts" / (raw_sha + ".json")


def _price_receipt_path(state_root: Path, raw_sha: str) -> Path:
    return state_root / STATE_DIR / "price_receipts" / (raw_sha + ".json")


def _fingerprint_body(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    return {key: fingerprint[key] for key in ("volume", "file_id", "size", "mtime_ns", "change")}


def _fingerprint_index_path(state_root: Path, kind: str, fingerprint: Mapping[str, Any]) -> Path:
    return state_root / STATE_DIR / (kind + "_fingerprint") / (_sha256_bytes(_canon_bytes(_fingerprint_body(fingerprint))) + ".json")


def _file_anchor_path(state_root: Path, kind: str, volume: Any, file_id: Any) -> Path:
    token = _sha256_bytes(_canon_bytes({"volume": volume, "file_id": file_id}))
    return state_root / STATE_DIR / (kind + "_file_anchor") / (token + ".json")


def _refuse_reparse(path: Path) -> None:
    cursor = Path(path)
    while True:
        if path_has_reparse_point(cursor):
            _raise_stream("FEEDBACK_REPARSE_POINT_REFUSED:" + str(cursor))
        parent = cursor.parent
        if parent == cursor:
            return
        cursor = parent


def _trusted_anchored_receipt(state_root: Path, kind: str, fingerprint: Mapping[str, Any] | None,
                              receipt_path_for) -> dict[str, Any] | None:
    """Receipt produced by a full SHA-256 under the current verifier, at this exact fingerprint."""
    if not fingerprint:
        return None
    anchor = _read_state_json(_fingerprint_index_path(state_root, kind, fingerprint))
    digest = _verifier_digest()
    if (not anchor or anchor.get("content_verified") is not True or anchor.get("fingerprint") != _fingerprint_body(fingerprint)
            or anchor.get("code_digest") != digest):
        return None
    raw = anchor.get("source_sha256")
    if not isinstance(raw, str):
        return None
    receipt = _read_state_json(receipt_path_for(state_root, raw))
    if (not receipt or receipt.get("contract_version") != STREAM_CONTRACT_VERSION or receipt.get("source_sha256") != raw
            or receipt.get("size") != fingerprint["size"]):
        return None
    if kind == "t0" and receipt.get("code_digest") != digest:
        return None
    return receipt


def _bind_fingerprint(state_root: Path, kind: str, fingerprint: Mapping[str, Any] | None, raw_sha: str) -> None:
    if not fingerprint:
        return
    _refuse_reparse(state_root)
    body = _fingerprint_body(fingerprint)
    digest = _verifier_digest()
    _atomic_write_json(_fingerprint_index_path(state_root, kind, fingerprint), {
        "contract_version": STREAM_CONTRACT_VERSION, "fingerprint": body,
        "source_sha256": raw_sha, "code_digest": digest, "content_verified": True,
        "verified_at": _now_utc(),
    })
    _atomic_write_json(_file_anchor_path(state_root, kind, body["volume"], body["file_id"]), {
        "contract_version": STREAM_CONTRACT_VERSION, "fingerprint": body,
        "source_sha256": raw_sha, "code_digest": digest, "content_verified": True,
        "verified_at": _now_utc(),
    })


def _bind_quietly(state_root: Path, kind: str, fingerprint: Mapping[str, Any] | None, raw_sha: str) -> None:
    try:
        _bind_fingerprint(state_root, kind, fingerprint, raw_sha)
    except OSError:
        pass
    except Exception as exc:
        if not isinstance(exc, _streaming.FeedbackStreamError):
            raise


def _receipt_sha_for_same_file(state_root: Path, kind: str, path: Path) -> str | None:
    """SHA recorded for this volume and file id. One anchor read, not a directory scan."""
    current = _current_fingerprint(path)
    if not current:
        return None
    anchor_path = _file_anchor_path(state_root, kind, current["volume"], current["file_id"])
    if path_has_reparse_point(anchor_path):
        return None
    anchor = _read_state_json(anchor_path)
    body = anchor.get("fingerprint") if isinstance(anchor, dict) else None
    if (not isinstance(body, dict) or anchor.get("content_verified") is not True
            or anchor.get("code_digest") != _verifier_digest()
            or body.get("volume") != current["volume"] or body.get("file_id") != current["file_id"]
            or not isinstance(anchor.get("source_sha256"), str)):
        return None
    return anchor["source_sha256"]


def scan_legacy_artifact(path: Path, metrics: dict[str, Any] | None = None, state_root: Path | None = None,
                         *, persist_receipts: bool = True) -> SourceHandle | None:
    """Header-only pass. A fingerprint hit uses the receipt and does not read the file bytes."""
    header: dict[str, Any] = {}
    count = 0
    raw = None
    size_now = None
    fingerprint = None
    if state_root is not None:
        fingerprint = _current_fingerprint(path)
        cached = _trusted_anchored_receipt(state_root, "legacy", fingerprint, _legacy_receipt_path)
        if cached is not None:
            found = cached["source_sha256"]
            handle = SourceHandle(cached["header"])
            handle["records"] = StreamedRecords(path, cached["record_count"], "legacy")
            handle.valid, handle.raw_sha256, handle.size, handle.path = True, found, cached["size"], Path(path)
            _metric(metrics, "legacy_fingerprint_hits")
            _metric(metrics, "legacy_receipt_hits")
            return handle
        _metric(metrics, "legacy_fingerprint_misses")
        try:
            raw = bas.source_hash(path)
            size_now = path.stat().st_size
        except OSError:
            return None
        _metric(metrics, "stream_sha256_bytes", size_now)
        cached = _read_state_json(_legacy_receipt_path(state_root, raw))
        if (cached and cached.get("contract_version") == STREAM_CONTRACT_VERSION and cached.get("source_sha256") == raw
                and cached.get("size") == size_now and isinstance(cached.get("header"), dict) and isinstance(cached.get("record_count"), int)):
            if persist_receipts:
                _bind_quietly(state_root, "legacy", fingerprint, raw)
            handle = SourceHandle(cached["header"])
            handle["records"] = StreamedRecords(path, cached["record_count"], "legacy")
            handle.valid, handle.raw_sha256, handle.size, handle.path = True, raw, size_now, Path(path)
            _metric(metrics, "legacy_receipt_hits")
            return handle
    try:
        with _HashedStream(path) as stream:
            parser = bas.ObjectStream(stream.text, sorted_required=False)
            for key in parser.members():
                if key == "records":
                    for _ticker in parser.members():
                        parser.value()
                        count += 1
                else:
                    header[key] = parser.value()
            if parser.peek():
                return None
            digest, size = stream.finish()
    except (OSError, UnicodeError, ValueError):
        return None
    _metric(metrics, "stream_header_scan_bytes", size)
    handle = SourceHandle(header)
    handle.update({"records": StreamedRecords(path, count, "legacy")})
    handle.valid, handle.raw_sha256, handle.size, handle.path = True, digest, size, Path(path)
    if persist_receipts and state_root is not None and digest == raw and size == size_now:
        try:
            _atomic_write_json(_legacy_receipt_path(state_root, digest), {
                "contract_version": STREAM_CONTRACT_VERSION, "source_sha256": digest, "size": size, "header": header,
                "record_count": count, "content_verified": True, "verified_at": _now_utc()})
            _bind_quietly(state_root, "legacy", fingerprint, digest)
        except (OSError, ValueError):
            pass
    return handle


def _verify_snapshot_stream(path: Path) -> dict[str, Any]:
    """Cryptographically equivalent to ``_retention.validate_snapshot`` without materialising the snapshot."""
    state = {"valid": True, "reason": None}
    t0_candidates: dict[str, Any] = {}

    def on_record(ticker, row):
        if not state["valid"]:
            return
        if not isinstance(row, Mapping) or row.get("ticker") != ticker:
            state.update(valid=False, reason="RECORD_TICKER_MISMATCH")
            return
        body = {k: v for k, v in row.items() if k != "prospective_snapshot_record_identity"}
        if row.get("prospective_snapshot_record_identity") != _retention.RECORD_PREFIX + _sha256_bytes(_canon_bytes(body)):
            state.update(valid=False, reason="RECORD_IDENTITY_MISMATCH")
            return
        observation = row.get("t0_close_observation")
        if isinstance(observation, Mapping):
            t0_candidates[ticker] = dict(observation)

    metadata, digest, count = bas.stream_artifact(path, excluded={"snapshot_identity"}, on_record=on_record)
    if metadata.get("snapshot_identity") != _retention.SNAPSHOT_PREFIX + digest:
        state.update(valid=False, reason="SNAPSHOT_IDENTITY_MISMATCH")
    if metadata.get("contract_version") != _retention.CONTRACT_VERSION:
        state.update(valid=False, reason="SNAPSHOT_CONTRACT_MISMATCH")
    session = metadata.get("session")
    t0_prices = {t: row for t, row in t0_candidates.items() if isinstance(session, str) and row.get("session") == session}
    return {"header": metadata, "record_count": count, "valid": state["valid"], "reason": state["reason"], "t0_prices": t0_prices}


def _handle_from_t0_receipt(path: Path, receipt: Mapping[str, Any]) -> SourceHandle:
    handle = SourceHandle(receipt["header"])
    handle["records"] = StreamedRecords(path, receipt["record_count"], "t0")
    handle.valid = bool(receipt["valid"])
    handle.raw_sha256, handle.size, handle.path = receipt["source_sha256"], receipt["size"], Path(path)
    handle.t0_prices = receipt["t0_prices"]
    return handle


def load_snapshot_handle(path: Path, state_root: Path, metrics: dict[str, Any] | None = None,
                         *, persist_receipts: bool = True) -> SourceHandle | None:
    """Loader seam for discovery. An exact fingerprint match does not read the file."""
    fingerprint = _current_fingerprint(path)
    anchored = _trusted_anchored_receipt(state_root, "t0", fingerprint, _receipt_path)
    if anchored is not None:
        _metric(metrics, "t0_fingerprint_hits")
        _metric(metrics, "t0_receipt_hits")
        return _handle_from_t0_receipt(path, anchored)
    _metric(metrics, "t0_fingerprint_misses")
    try:
        raw_sha = bas.source_hash(path)
        size = path.stat().st_size
    except OSError:
        return None
    _metric(metrics, "stream_sha256_bytes", size)
    receipt_file = _receipt_path(state_root, raw_sha)
    receipt = _read_state_json(receipt_file)
    digest = _verifier_digest()
    if not (receipt and receipt.get("contract_version") == STREAM_CONTRACT_VERSION and receipt.get("source_sha256") == raw_sha
            and receipt.get("size") == size and receipt.get("code_digest") == digest):
        receipt = None
    if receipt is None:
        try:
            proof = _verify_snapshot_stream(path)
        except (OSError, UnicodeError):
            return None
        except ValueError:
            if size > _UNSORTED_FALLBACK_MAX_BYTES:
                return None
            snapshot = _retention._load(path)
            if not snapshot:
                return None
            records = snapshot.get("records") or {}
            proof = {"header": {k: v for k, v in snapshot.items() if k != "records"}, "record_count": len(records),
                     "valid": _retention.validate_snapshot(snapshot), "reason": None,
                     "t0_prices": {t: dict(r["t0_close_observation"]) for t, r in records.items()
                                   if isinstance(r, Mapping) and isinstance(r.get("t0_close_observation"), Mapping)
                                   and r["t0_close_observation"].get("session") == snapshot.get("session")}}
        receipt = {"contract_version": STREAM_CONTRACT_VERSION, "source_sha256": raw_sha, "size": size,
                   "code_digest": digest, "content_verified": True, "verified_at": _now_utc(), **proof}
        _metric(metrics, "stream_verified_bytes", size)
        _metric(metrics, "t0_receipt_misses")
        if persist_receipts:
            try:
                _atomic_write_json(receipt_file, receipt)
            except OSError:
                pass
    else:
        _metric(metrics, "t0_receipt_hits")
    if persist_receipts:
        _bind_quietly(state_root, "t0", fingerprint, raw_sha)
    return _handle_from_t0_receipt(path, receipt)
