"""Lossless per-record repeated-subtree references for line-delimited delivery records.

Storage representation only: no authority, identity or content change. A record
written with this codec carries ``CODEC_KEY``; every later exact repeat of a
container subtree (canonical JSON ≥ ``min_bytes``) inside the same record is
replaced by ``{REF_KEY: "<RFC 6901 pointer to its first occurrence>"}``.

Determinism: traversal is preorder over sorted keys / list order, identical to
the canonical serializer, so equal logical records always encode to equal bytes.
Identity: callers hash the *expanded* record (``decode_record`` output), never
the encoded one. Legacy records (no ``CODEC_KEY``) pass through unchanged.
References never cross records, so one line stays independently decodable.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

CODEC_KEY = "$record_subtree_codec"
CODEC_VERSION = "record_subtree_refs/v1"
REF_KEY = "$subtree_ref"
DEFAULT_MIN_BYTES = 1024


class RecordSubtreeCodecError(ValueError):
    """Fail-closed codec refusal (malformed reference or reserved key collision)."""


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _leaf(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _token(value: Any, memo: dict[int, tuple[bytes, int]]) -> tuple[bytes, int]:
    """Unambiguous child token and approximate canonical length.

    Containers contribute their 32-byte structural digest; scalars contribute a
    type tag plus length-prefixed text (bool/int/float/None/str never collide;
    floats use repr, exactly as the canonical serializer does). The length only
    gates the size threshold; equality is decided by the digest.
    """
    if isinstance(value, (dict, list)):
        return b"c" + _digest(value, memo)[0], memo[id(value)][1]
    if isinstance(value, str):
        text = value.encode("utf-8", "surrogatepass")
        return b"s%d:" % len(text) + text, len(text) + 2
    if value is None or isinstance(value, bool):
        text = repr(value).encode()
        return b"k" + text, 5
    if isinstance(value, int):
        text = str(value).encode()
        return b"i%d:" % len(text) + text, len(text)
    if isinstance(value, float):
        text = repr(value).encode()
        return b"f%d:" % len(text) + text, len(text)
    text = _leaf(value).encode("utf-8")
    return b"x%d:" % len(text) + text, len(text)


def _digest(value: Any, memo: dict[int, tuple[bytes, int]]) -> tuple[bytes, int]:
    """Structural sha256 and approximate canonical character length, bottom-up, O(n)."""
    cached = memo.get(id(value))
    if cached is not None:
        return cached
    parts = []
    size = 2 + max(len(value) - 1, 0)
    if isinstance(value, dict):
        parts.append(b"{")
        for key in sorted(value):
            child, child_size = _token(value[key], memo)
            encoded_key = key.encode("utf-8", "surrogatepass")
            parts.append(b"%d:" % len(encoded_key) + encoded_key + child)
            size += len(encoded_key) + 3 + child_size
    else:
        parts.append(b"[")
        for item in value:
            child, child_size = _token(item, memo)
            parts.append(child)
            size += child_size
    result = (hashlib.sha256(b"".join(parts)).digest(), size)
    memo[id(value)] = result
    return result


def _has_reserved(value: Any) -> bool:
    if isinstance(value, dict):
        return CODEC_KEY in value or REF_KEY in value or any(_has_reserved(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_reserved(v) for v in value)
    return False


def encode_record(record: dict[str, Any], *, min_bytes: int = DEFAULT_MIN_BYTES) -> dict[str, Any]:
    """Return a new record with repeated subtrees referenced; input is not mutated.

    A record containing a reserved key is returned unencoded (as a deep copy) so
    the codec can never make an existing record ambiguous.
    """
    if not isinstance(record, dict):
        raise RecordSubtreeCodecError("RECORD_SUBTREE_CODEC_RECORD_NOT_OBJECT")
    if _has_reserved(record):
        return copy.deepcopy(record)
    memo: dict[int, tuple[bytes, int]] = {}
    _digest(record, memo)
    first: dict[bytes, str] = {}
    replaced = 0

    def walk(value: Any, pointer: str) -> Any:
        nonlocal replaced
        if isinstance(value, (dict, list)) and pointer:
            digest, size = memo[id(value)]
            if size >= min_bytes:
                target = first.get(digest)
                if target is not None:
                    replaced += 1
                    return {REF_KEY: target}
                first[digest] = pointer
        if isinstance(value, dict):
            return {key: walk(value[key], pointer + "/" + _escape(key)) for key in sorted(value)}
        if isinstance(value, list):
            return [walk(item, f"{pointer}/{index}") for index, item in enumerate(value)]
        return value

    encoded = walk(record, "")
    if not replaced:
        return encoded
    encoded[CODEC_KEY] = CODEC_VERSION
    return encoded


def decode_record(record: Any) -> Any:
    """Expand a codec record to its exact logical form; legacy rows pass through."""
    if not isinstance(record, dict) or CODEC_KEY not in record:
        return record
    if record[CODEC_KEY] != CODEC_VERSION:
        raise RecordSubtreeCodecError("RECORD_SUBTREE_CODEC_UNSUPPORTED_VERSION")
    resolved: dict[str, Any] = {}

    def walk(value: Any, pointer: str) -> Any:
        if isinstance(value, dict):
            if REF_KEY in value:
                target = value[REF_KEY]
                if len(value) != 1 or not isinstance(target, str) or target not in resolved:
                    raise RecordSubtreeCodecError("RECORD_SUBTREE_CODEC_UNRESOLVED_REFERENCE")
                # Independent containers: readers may mutate rows they own.
                result = copy.deepcopy(resolved[target])
            else:
                result = {key: walk(value[key], pointer + "/" + _escape(key)) for key in sorted(value)}
        elif isinstance(value, list):
            result = [walk(item, f"{pointer}/{index}") for index, item in enumerate(value)]
        else:
            return value
        if pointer:
            resolved[pointer] = result
        return result

    body = {key: item for key, item in record.items() if key != CODEC_KEY}
    return walk(body, "")
