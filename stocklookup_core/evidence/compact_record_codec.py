"""Record-local storage envelope for repeated JSON subtrees; no identity authority.

A decision record restates the same large contexts (valuation, fundamental,
peer) under several keys. This codec serialises each repeated subtree once per
record and replaces the other occurrences with explicit references. It is a
physical representation only:

* ``decode_record(encode_record(r))`` is canonically byte-equal to ``r``;
* logical identities keep hashing the expanded record through the existing
  canonical serializer, so no identity, lineage or join changes;
* a reference never leaves its own record, and nothing is shared across
  tickers, sessions or artifacts;
* an inline record that is not an envelope is returned unchanged by
  ``expand_record``, so historical files remain readable as they are.

Nothing in the Daily path calls this module yet.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

VERSION = "compact_record/v1"
MIN_SUBTREE_CHARS = 4096
MAX_DEPTH = 12
_ENVELOPE_KEYS = frozenset({"compact_record", "literal", "refs", "blocks"})
_ENCODER = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class CompactRecordError(ValueError):
    """The envelope is malformed; the caller must fail closed."""


def _canonical(value: Any) -> bytes:
    # Byte-identical to bounded_artifact_stream.canonical_bytes.
    return _ENCODER.encode(value).encode("utf-8")


def is_compact_record(value: Any) -> bool:
    return (isinstance(value, dict) and value.get("compact_record") == VERSION
            and set(value) == _ENVELOPE_KEYS)


def encode_record(record: Any, *, min_subtree_chars: int = MIN_SUBTREE_CHARS,
                  hints: set | None = None) -> dict[str, Any]:
    """Return a deterministic envelope; the input is not modified.

    The envelope shares the untouched subtrees of ``record`` (no deep copy), so serialise it
    before mutating the input. ``hints`` is an optional caller-owned set that remembers which
    path shapes held large subtrees in earlier records of the same artifact; it only avoids
    re-serialising them and never changes the result.
    """
    if is_compact_record(record):
        raise CompactRecordError("RECORD_ALREADY_COMPACT")
    if hints is None:
        hints = set()
    groups: dict[bytes, list[tuple]] = {}
    sizes: dict[bytes, int] = {}
    encode = _ENCODER.encode

    def scan(value: Any, path: tuple) -> str:
        """Canonical text of a non-empty container, assembled from its children."""
        if len(path) >= MAX_DEPTH:
            text = encode(value)
        else:
            parts = []
            if isinstance(value, dict):
                try:
                    keys = sorted(value)
                except TypeError as error:
                    raise CompactRecordError("NON_STRING_OBJECT_KEY") from error
                items = [(key, value[key]) for key in keys]
            else:
                items = list(enumerate(value))
            is_object = isinstance(value, dict)
            for key, child in items:
                if is_object and not isinstance(key, str):
                    raise CompactRecordError("NON_STRING_OBJECT_KEY")
                if isinstance(child, (dict, list)) and child:
                    child_path = (*path, key)
                    shape = _shape(child_path)
                    if shape in hints:
                        text = scan(child, child_path)
                    else:
                        text = encode(child)
                        if len(text) >= min_subtree_chars:
                            hints.add(shape)
                            text = scan(child, child_path)
                else:
                    text = encode(child)
                parts.append(_key_text(key) + ":" + text if is_object else text)
            text = ("{" + ",".join(parts) + "}") if is_object else ("[" + ",".join(parts) + "]")
        if path and len(text) >= min_subtree_chars:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            groups.setdefault(digest, []).append(path)
            sizes[digest] = len(text)
        return text

    if isinstance(record, (dict, list)) and record:
        try:
            scan(record, ())
        except CompactRecordError:
            raise
        except (TypeError, ValueError) as error:  # mixed/non-string keys, NaN, non-JSON values
            raise CompactRecordError("RECORD_NOT_CANONICAL_JSON") from error
    chosen: dict[tuple, int] = {}
    block_paths: list[tuple] = []

    def overlaps(path: tuple) -> bool:
        return any(path[:len(other)] == other or other[:len(path)] == path for other in chosen)

    # Largest subtree first, so the outermost repeated context wins; ties are
    # broken by content digest and then path order for determinism.
    for digest in sorted(groups, key=lambda item: (-sizes[item], item)):
        uses = [path for path in sorted(groups[digest], key=_path_key) if not overlaps(path)]
        if len(uses) < 2:
            continue
        index = len(block_paths)
        block_paths.append(uses[0])
        for path in uses:
            chosen[path] = index

    # Copy only the containers on the way to a reference; everything else is shared.
    literal = record
    copied: dict[tuple, Any] = {}
    if chosen:
        literal = copied[()] = dict(record) if isinstance(record, dict) else list(record)
        for path in chosen:
            node = literal
            for depth, part in enumerate(path[:-1], 1):
                prefix = path[:depth]
                child = copied.get(prefix)
                if child is None:
                    original = node[part]
                    child = copied[prefix] = dict(original) if isinstance(original, dict) else list(original)
                    node[part] = child
                node = child
            node[path[-1]] = None
    return {
        "compact_record": VERSION,
        "literal": literal,
        "refs": [[list(path), chosen[path]] for path in sorted(chosen, key=_path_key)],
        "blocks": [_get(record, path) for path in block_paths],
    }


_KEY_TEXT: dict[str, str] = {}


def _key_text(key: str) -> str:
    text = _KEY_TEXT.get(key)
    if text is None:
        text = _ENCODER.encode(key)
        if len(_KEY_TEXT) < 65536:
            _KEY_TEXT[key] = text
    return text


def _shape(path: tuple) -> tuple:
    return tuple(part if isinstance(part, str) else 0 for part in path)


def decode_record(envelope: Any) -> Any:
    """Expand an envelope; refuse anything that is not exactly well formed."""
    if not is_compact_record(envelope):
        raise CompactRecordError("NOT_A_COMPACT_RECORD")
    blocks, refs, literal = envelope["blocks"], envelope["refs"], envelope["literal"]
    if not isinstance(blocks, list) or not isinstance(refs, list):
        raise CompactRecordError("ENVELOPE_SHAPE_INVALID")
    if any(not isinstance(block, (dict, list)) or not block for block in blocks):
        raise CompactRecordError("BLOCK_NOT_A_CONTAINER")
    seen: list[tuple] = []
    uses = [0] * len(blocks)
    result = _clone(literal)
    for item in refs:
        if (not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], list) or not item[0]
                or isinstance(item[1], bool) or not isinstance(item[1], int)):
            raise CompactRecordError("REFERENCE_SHAPE_INVALID")
        path, index = tuple(item[0]), item[1]
        if any(isinstance(part, bool) or not isinstance(part, (str, int)) for part in path):
            raise CompactRecordError("REFERENCE_PATH_INVALID")
        if not 0 <= index < len(blocks):
            raise CompactRecordError("REFERENCE_BLOCK_OUT_OF_RANGE")
        if any(path[:len(other)] == other or other[:len(path)] == path for other in seen):
            raise CompactRecordError("REFERENCE_DUPLICATE_OR_OVERLAPPING")
        seen.append(path)
        uses[index] += 1
        parent = _get(result, path[:-1])
        key = path[-1]
        try:
            placeholder = parent[key]
        except (KeyError, IndexError, TypeError) as error:
            raise CompactRecordError("REFERENCE_PATH_NOT_IN_LITERAL") from error
        if isinstance(parent, dict) != isinstance(key, str) or placeholder is not None:
            raise CompactRecordError("REFERENCE_PLACEHOLDER_INVALID")
        parent[key] = _clone(blocks[index])
    if any(count < 2 for count in uses):
        raise CompactRecordError("BLOCK_NOT_SHARED")
    if is_compact_record(result):
        raise CompactRecordError("NESTED_ENVELOPE_REFUSED")
    return result


def expand_record(value: Any) -> Any:
    """Reader entry point: envelopes are expanded, inline records pass through."""
    return decode_record(value) if is_compact_record(value) else value


def logical_sha256(value: Any) -> str:
    """Canonical SHA-256 of the expanded record, whichever form was stored."""
    return hashlib.sha256(_canonical(expand_record(value))).hexdigest()


def _path_key(path: tuple) -> tuple:
    return tuple((0, "", part) if isinstance(part, int) else (1, part, 0) for part in path)


def _get(value: Any, path: tuple) -> Any:
    for part in path:
        try:
            if isinstance(value, dict) != isinstance(part, str):
                raise KeyError(part)
            value = value[part]
        except (KeyError, IndexError, TypeError) as error:
            raise CompactRecordError("REFERENCE_PATH_NOT_IN_LITERAL") from error
    return value


def _clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clone(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_clone(child) for child in value]
    return value
