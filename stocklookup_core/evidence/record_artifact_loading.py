"""Graph loading over the unchanged frozen JSON parser; no verification authority.

Keep this allocation adapter outside E4's frozen source identities. Callers retain
their existing artifact/session/content qualification and their required graph.
"""
import json
import sys
from collections import OrderedDict

from stocklookup_core.evidence.artifact_stream import ObjectStream


# These envelopes contain independent record universes, not individual records.
# Do not recurse through arbitrary objects: one record and ordinary metadata must
# still fit the unchanged ObjectStream member limit.
_RECORD_ENVELOPES = {
    "financial_analysis_product",
    "valuation_balance_sheet_divergence_context",
    "metric_research_context",
}


def shared_string_decoder():
    """Native JSON decoder with bounded per-reader immutable-string sharing."""
    # raw_decode clears the stdlib scanner's key memo after each record. Without
    # a per-artifact memo, repeated schema keys become independent strings in
    # every retained row. Repeated labels/lineage strings also need no separate
    # allocation. Share only immutable strings; containers stay independently
    # owned. Bound both memos and release them with this loader, never globally.
    keys = {}
    strings = OrderedDict()
    string_bytes = 0
    def shared_value(value):
        nonlocal string_bytes
        if isinstance(value, str) and len(value) <= 2048:
            existing = strings.get(value)
            if existing is not None:
                strings.move_to_end(value)
                return existing
            size = sys.getsizeof(value) + 128
            while strings and (len(strings) >= 8192 or string_bytes + size > 8 * 1024**2):
                old, _ = strings.popitem(last=False)
                string_bytes -= sys.getsizeof(old) + 128
            strings[value] = value
            string_bytes += size
        elif isinstance(value, list):
            for index, item in enumerate(value):
                value[index] = shared_value(item)
        return value
    def shared_keys(pairs):
        result = {}
        for key, value in pairs:
            if len(key) <= 256:
                shared = keys.get(key)
                if shared is not None:
                    key = shared
                elif len(keys) < 4096:
                    keys[key] = key
            result[key] = shared_value(value)
        return result
    return json.JSONDecoder(object_pairs_hook=shared_keys)


def load_record_artifact(path, *, record_tickers=None):
    """Decode without whole-file text, optionally retaining selected keyed records.

    Selection is a read projection, never identity verification. Every record is
    still decoded and checked by the same parser, including discarded records.
    Metadata and list-valued collections retain their original JSON types.
    """
    selected = None if record_tickers is None else frozenset(record_tickers)
    def object_value(parser):
        result = {}
        for key in parser.members():
            if key in {"records", "cards"} and parser.peek() == "{":
                records = {}
                for ticker in parser.members():
                    row = parser.value()
                    if selected is None or key != "records" or ticker in selected:
                        records[ticker] = row
                    del row
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
            elif key in _RECORD_ENVELOPES and parser.peek() == "{":
                result[key] = object_value(parser)
            else:
                result[key] = parser.value()
        return result

    with path.open(encoding="utf-8") as source:
        parser = ObjectStream(source, sorted_required=False)
        parser.decoder = shared_string_decoder()
        result = object_value(parser)
        if parser.peek():
            raise ValueError("ACCEPTANCE_TRAILING_JSON")
    return result
