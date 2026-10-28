"""Graph loading over the unchanged frozen JSON parser; no verification authority.

Keep this allocation adapter outside E4's frozen source identities. Callers retain
their existing artifact/session/content qualification and their required graph.

SortedRecordArtifactWriter and IndexedRecordMapping keep a sorted record artifact
on disk. They do not decide research authority. The caller still qualifies the
artifact, the session and the content identity.
"""
import codecs
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from stocklookup_core.evidence.artifact_stream import ObjectStream
from stocklookup_core.evidence.bounded_json import canonical_bytes


def load_record_artifact(path):
    """Decode a graph without a whole-file Unicode string; preserve JSON types."""
    def object_value(parser):
        result = {}
        for key in parser.members():
            if key in {"records", "cards"} and parser.peek() == "{":
                records = {}
                for ticker in parser.members():
                    records[ticker] = parser.value()
                result[key] = records
            elif key in {"records", "cards"} and parser.peek() == "[":
                records = []
                parser.take("[")
                while parser.peek() != "]":
                    if records:
                        parser.take(",")
                    records.append(parser.value())
                parser.take("]")
                result[key] = records
            elif key == "financial_analysis_product" and parser.peek() == "{":
                result[key] = object_value(parser)
            else:
                result[key] = parser.value()
        return result

    with path.open(encoding="utf-8") as source:
        parser = ObjectStream(source, sorted_required=False)
        result = object_value(parser)
        if parser.peek():
            raise ValueError("ACCEPTANCE_TRAILING_JSON")
    return result


class RecordArtifactError(ValueError):
    """A spilled or indexed record artifact failed closed."""


@dataclass(frozen=True)
class RecordWriteReceipt:
    """Bytes actually replaced into the canonical path. Not a research receipt."""
    path: Path
    size: int
    mtime_ns: int
    serialized_sha256: str


def _pretty_text(text, newline):
    return text.replace("\n", newline).encode("utf-8")


class SortedRecordArtifactWriter:
    """Spill canonical record bytes, then write one pretty sorted artifact.

    ``newline`` is ``"\\n"`` for the binary IID receipt writer. T0 uses
    ``os.linesep`` because its pretty encoder translates newlines that way.
    Pass B re-parses every spilled record and refuses unless the canonical
    bytes match the spill, so a non-string key or a NaN cannot pass.
    """

    def __init__(self, target, *, newline):
        self.target = Path(target)
        self.newline = newline
        self._spill = self.target.with_name(self.target.name + ".compact-spill")
        self._temp = self.target.with_name(self.target.name + ".tmp")
        self._keys = []
        self._spans = []
        self._previous = None
        self._spill_fh = None
        self._offset = 0
        self.committed = False
        self.receipt = None
        self._finished = False

    def add(self, key, record):
        if self._finished or self.committed:
            raise RecordArtifactError("RECORD_WRITER_ALREADY_FINISHED")
        if not isinstance(key, str):
            raise RecordArtifactError("RECORD_KEY_NOT_STRING")
        if self._previous is not None and key <= self._previous:
            raise RecordArtifactError("RECORD_KEY_NOT_STRICTLY_INCREASING")
        try:
            data = canonical_bytes(record)
        except (TypeError, ValueError) as exc:
            raise RecordArtifactError("RECORD_CANONICAL_REFUSED") from exc
        handle = self._spill_handle()
        handle.write(data)
        self._keys.append(key)
        self._spans.append((self._offset, self._offset + len(data)))
        self._offset += len(data)
        self._previous = key

    def abort(self):
        self._close_spill()
        self._spill.unlink(missing_ok=True)
        self._temp.unlink(missing_ok=True)

    def finish(self, header, identity_fn, excluded=()):
        if self._finished:
            raise RecordArtifactError("RECORD_WRITER_ALREADY_FINISHED")
        if not isinstance(header, Mapping) or "records" in header:
            raise RecordArtifactError("RECORD_WRITER_HEADER_INVALID")
        excluded = frozenset(excluded)
        try:
            digest = self._digest(header, excluded)
            identity = dict(identity_fn(digest))
            if set(identity) & set(header):
                raise RecordArtifactError("RECORD_IDENTITY_FIELD_COLLISION")
            index = self._write_pretty(header, identity)
        except Exception:
            self.abort()
            raise
        self._finished = True
        return identity, self.receipt, index

    def _spill_handle(self):
        if self._spill_fh is None:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            self._spill_fh = self._spill.open("wb")
        return self._spill_fh

    def _close_spill(self):
        if self._spill_fh is not None:
            self._spill_fh.close()
            self._spill_fh = None

    def _spill_slice(self, start, end):
        with self._spill.open("rb") as source:
            source.seek(start)
            data = source.read(end - start)
        if len(data) != end - start:
            raise RecordArtifactError("RECORD_SPILL_TRUNCATED")
        return data

    def _digest(self, header, excluded):
        self._close_spill()
        digest = hashlib.sha256()
        digest.update(b"{")
        keys = sorted(set(key for key in header if key not in excluded) | {"records"})
        for index, key in enumerate(keys):
            if index:
                digest.update(b",")
            digest.update(canonical_bytes(key))
            digest.update(b":")
            if key == "records":
                digest.update(b"{")
                for record_index, ticker in enumerate(self._keys):
                    if record_index:
                        digest.update(b",")
                    start, end = self._spans[record_index]
                    digest.update(canonical_bytes(ticker))
                    digest.update(b":")
                    digest.update(self._spill_slice(start, end))
                digest.update(b"}")
            else:
                digest.update(canonical_bytes(header[key]))
        digest.update(b"}")
        return digest.hexdigest()

    def _write_pretty(self, header, identity):
        encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2)
        newline = self.newline
        keys = sorted(set(header) | set(identity) | {"records"})
        index = {}
        hasher = hashlib.sha256()
        position = 0

        def emit(data):
            nonlocal position
            if handle.write(data) != len(data):
                raise OSError("RECORD_ARTIFACT_SHORT_WRITE")
            hasher.update(data)
            position += len(data)

        self.target.parent.mkdir(parents=True, exist_ok=True)
        with self._temp.open("wb") as handle:
            if not keys:
                emit(_pretty_text("{}\n", newline))
            else:
                emit(_pretty_text("{\n", newline))
                for key_index, key in enumerate(keys):
                    emit(_pretty_text("  " + encoder.encode(key) + ": ", newline))
                    if key == "records":
                        if not self._keys:
                            emit(b"{}")
                        else:
                            emit(_pretty_text("{\n", newline))
                            for record_index, name in enumerate(self._keys):
                                start, end = self._spans[record_index]
                                raw = self._spill_slice(start, end)
                                parsed = json.loads(raw.decode("utf-8"))
                                if canonical_bytes(parsed) != raw:
                                    raise RecordArtifactError("RECORD_CANONICAL_ROUND_TRIP_MISMATCH")
                                prefix = _pretty_text("    " + encoder.encode(name) + ": ", newline)
                                body = _pretty_text(encoder.encode(parsed).replace("\n", "\n    "), newline)
                                emit(prefix)
                                value_start = position
                                emit(body)
                                index[name] = (value_start, position, hashlib.sha256(body).hexdigest())
                                emit(_pretty_text(",\n" if record_index + 1 < len(self._keys) else "\n", newline))
                            emit(b"  }")
                    else:
                        member = identity[key] if key in identity else header[key]
                        emit(_pretty_text(encoder.encode(member).replace("\n", "\n  "), newline))
                    emit(_pretty_text(",\n" if key_index + 1 < len(keys) else "\n", newline))
                emit(_pretty_text("}\n", newline))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(self._temp, self.target)
        self.committed = True
        stat = self.target.stat()
        if stat.st_size != position:
            raise RecordArtifactError("RECORD_ARTIFACT_SIZE_MISMATCH")
        self.receipt = RecordWriteReceipt(self.target.resolve(), position, stat.st_mtime_ns, hasher.hexdigest())
        self._spill.unlink(missing_ok=True)
        return index


class _OffsetObjectStream(ObjectStream):
    """ObjectStream plus the file byte offset of the current character.

    ObjectStream counts characters. A UTF-8 file's byte offset is the bytes of
    the discarded text plus the bytes of the current buffer prefix. The source
    must decode complete characters only.
    """

    def __init__(self, source, **kwargs):
        super().__init__(source, **kwargs)
        self.buffer_byte_start = 0

    def fill(self, size=64 * 1024):
        if self.position:
            self.buffer_byte_start += len(self.buffer[:self.position].encode("utf-8"))
        super().fill(size)

    def byte_offset(self):
        return self.buffer_byte_start + len(self.buffer[:self.position].encode("utf-8"))

    def value_span(self):
        self.peek()
        start = self.byte_offset()
        value = super().value()
        return value, start, self.byte_offset()


class _Utf8TextReader:
    """Text source that never splits a UTF-8 character across a read()."""

    def __init__(self, raw):
        self.raw = raw
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.pending = ""
        self.eof = False

    def read(self, size):
        while len(self.pending) < size and not self.eof:
            blob = self.raw.read(64 * 1024)
            if not blob:
                self.eof = True
                self.pending += self.decoder.decode(b"", final=True)
                break
            self.pending += self.decoder.decode(blob)
        text = self.pending[:size]
        self.pending = self.pending[size:]
        return text


class IndexedRecordMapping(Mapping):
    """Sorted ticker view of one pretty record artifact. Not a dict.

    ``__getitem__`` checks the file stat against the receipt, checks the slice
    sha256, then parses that slice. Iteration, length and membership use the
    index and do not parse a record.
    """

    def __init__(self, path, receipt, index):
        self.path = Path(path)
        self.receipt = receipt
        self._index = {key: (int(span[0]), int(span[1]), str(span[2])) for key, span in dict(index).items()}
        self._keys = tuple(sorted(self._index))
        self.reads = 0
        self.temporary_directory = None

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def __contains__(self, key):
        return key in self._index

    def __getitem__(self, key):
        try:
            start, end, digest = self._index[key]
        except KeyError:
            raise KeyError(key) from None
        stat = self.path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (self.receipt.size, self.receipt.mtime_ns):
            raise RecordArtifactError("RECORD_STORE_STAT_MISMATCH")
        with self.path.open("rb") as source:
            source.seek(start)
            data = source.read(end - start)
        if len(data) != end - start or hashlib.sha256(data).hexdigest() != digest:
            raise RecordArtifactError("RECORD_STORE_SLICE_MISMATCH")
        self.reads += 1
        return json.loads(data.decode("utf-8"))

    def rebind(self, path, receipt):
        self.path = Path(path)
        self.receipt = receipt

    def canonical_digest(self, header):
        """Hash ``header`` plus these records in ``record_mapping_digest`` order.

        ``header`` must already omit excluded identity fields and must not
        contain ``records``. Each record is re-parsed and re-canonicalized.
        """
        if not isinstance(header, Mapping) or "records" in header:
            raise RecordArtifactError("CANONICAL_DIGEST_HEADER_INVALID")
        if any(not isinstance(key, str) for key in header):
            raise RecordArtifactError("CANONICAL_DIGEST_HEADER_KEY_INVALID")
        digest = hashlib.sha256()
        digest.update(b"{")
        keys = sorted(set(header) | {"records"})
        for index, key in enumerate(keys):
            if index:
                digest.update(b",")
            digest.update(canonical_bytes(key))
            digest.update(b":")
            if key == "records":
                digest.update(b"{")
                for record_index, ticker in enumerate(self._keys):
                    if record_index:
                        digest.update(b",")
                    digest.update(canonical_bytes(ticker))
                    digest.update(b":")
                    digest.update(canonical_bytes(self[ticker]))
                digest.update(b"}")
            else:
                digest.update(canonical_bytes(header[key]))
        digest.update(b"}")
        return digest.hexdigest()

    @classmethod
    def from_file(cls, path, *, limit=64 * 1024 * 1024):
        """Index a pretty record artifact without retaining its records.

        The member limit is 64 MiB. The frozen parser's 16 MiB default is smaller
        than a large issuer record. Byte offsets come from the UTF-8 reader, not
        from ObjectStream's character position.
        """
        path = Path(path)
        header = {}
        index = {}
        with path.open("rb") as raw, path.open("rb") as slices:
            parser = _OffsetObjectStream(_Utf8TextReader(raw), limit=limit, sorted_required=True)
            saw_records = False
            for key in parser.members():
                if key == "records":
                    if saw_records or parser.peek() != "{":
                        raise RecordArtifactError("RECORD_STORE_RECORDS_INVALID")
                    saw_records = True
                    for ticker in parser.members():
                        _value, start, end = parser.value_span()
                        slices.seek(start)
                        data = slices.read(end - start)
                        if len(data) != end - start:
                            raise RecordArtifactError("RECORD_STORE_SLICE_TRUNCATED")
                        index[ticker] = (start, end, hashlib.sha256(data).hexdigest())
                        del _value
                else:
                    header[key] = parser.value()
            if parser.peek():
                raise RecordArtifactError("RECORD_STORE_TRAILING_JSON")
        hasher = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(block)
        stat = path.stat()
        receipt = RecordWriteReceipt(path.resolve(), stat.st_size, stat.st_mtime_ns, hasher.hexdigest())
        return cls(path, receipt, index), header
