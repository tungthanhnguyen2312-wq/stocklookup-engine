"""Graph loading over the unchanged frozen JSON parser; no verification authority.

Keep this allocation adapter outside E4's frozen source identities. Callers retain
their existing artifact/session/content qualification and their required graph.
"""
from stocklookup_core.evidence.artifact_stream import ObjectStream


# These envelopes contain independent record universes, not individual records.
# Do not recurse through arbitrary objects: one record and ordinary metadata must
# still fit the unchanged ObjectStream member limit.
_RECORD_ENVELOPES = {
    "financial_analysis_product",
    "valuation_balance_sheet_divergence_context",
    "metric_research_context",
}


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
            elif key in _RECORD_ENVELOPES and parser.peek() == "{":
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
