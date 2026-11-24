"""Decision 2 retained image readings: byte replay only, no parser/LLM authority.

This leaf imports only the standard library. Existing admission supplies its
numeric, unit and period recognizers; none of its other gates is replaced.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "dual_reader_reviewed_transcription/v1"
RAW_VERSION = "independent_image_reading/v1"
EVIDENCE_TIER = "DUAL_READER_REVIEWED_TRANSCRIPTION"
PROOF_DIR = "dual-reader-transcriptions"
RIGHTS_ROUTE = "OWNER_APPROVED_OFFICIAL_ISSUER_RESEARCH_NOT_VIETSTOCK"
# Accounts, products and model versions do not create separate families.
FAMILY_ALIASES = {"openai-gpt": "gpt", "gpt": "gpt", "codex": "gpt",
                  "google-gemini": "gemini", "gemini": "gemini",
                  "anthropic-claude": "claude", "claude": "claude"}


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _time(value: Any) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timezone required")
    return stamp


def _json(payload: bytes) -> dict:
    # Duplicate keys must not let a second value override the sealed first one.
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate key")
            out[key] = value
        return out
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def load_retained_dual_reader_proof(row: Mapping[str, Any], landing: Path) -> dict | None:
    """Read separately retained bytes beneath the governed evidence directory.

    No row boolean, inline normalized response, symlink escape or absolute path
    can substitute for the two raw files and the exact page image.
    """
    try:
        landing = landing.resolve()
        root = (landing / PROOF_DIR).resolve()
        if not root.is_relative_to(landing):
            return None
        def read(relative):
            name = Path(str(relative or ""))
            path = (landing / name).resolve()
            if name.is_absolute() or not path.is_relative_to(root) or not path.is_file():
                raise ValueError("evidence path outside proof root")
            return path.read_bytes()
        ref = row["dual_reader_transcription"]
        proof_bytes = read(ref["relative_path"])
        if _sha(proof_bytes) != ref["proof_sha256"]:
            return None
        proof = _json(proof_bytes)
        refs = proof["readings"]
        if len(refs) != 2 or refs[0]["relative_path"] == refs[1]["relative_path"]:
            return None
        return {"proof_bytes": proof_bytes,
                "raw_reader_bytes": [read(item["relative_path"]) for item in refs],
                "image_bytes": read(proof["page_image"]["relative_path"])}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def verify_dual_reader_transcription(row: Mapping[str, Any], evidence: Mapping[str, Any] | None,
        *, source_record, retained_bytes, parse_amount, parse_unit, recognize_period,
        recognize_scope) -> dict:
    """Replay byte identities, independent raw records, exact selected cell and time.

    Only the requested row/column is qualified. Disagreement on another metric
    is preserved in raw evidence and cannot globally reject an issuer.
    """
    def fail(code):
        return {"valid": False, "reason_codes": ["DUAL_READER_" + code]}
    try:
        if not evidence:
            return fail("RETAINED_PROOF_UNAVAILABLE")
        ref = row["dual_reader_transcription"]
        proof_bytes = evidence["proof_bytes"]
        if _sha(proof_bytes) != ref["proof_sha256"]:
            return fail("PROOF_HASH_MISMATCH")
        proof = _json(proof_bytes)
        if proof["contract_version"] != CONTRACT_VERSION:
            return fail("CONTRACT_MISMATCH")
        sha = row["document_sha256"]
        if (not source_record or retained_bytes is None or _sha(retained_bytes) != sha
                or source_record.get("sha256") != sha or proof["document_sha256"] != sha
                or proof["document_id"] != source_record.get("document_id")):
            return fail("DOCUMENT_BINDING_MISMATCH")
        if (source_record.get("rights_route") != RIGHTS_ROUTE
                or source_record.get("acquisition_route") != "INDEPENDENT_OFFICIAL_SOURCE"
                or source_record.get("rights_status") != "RESEARCH_AND_AI_READING_APPROVED"):
            return fail("RIGHTS_OR_INDEPENDENT_SOURCE_NOT_PROVEN")
        image = proof["page_image"]
        if _sha(evidence["image_bytes"]) != image["sha256"]:
            return fail("IMAGE_HASH_MISMATCH")
        if image not in source_record.get("page_image_bindings", []):
            return fail("SOURCE_PAGE_IMAGE_BINDING_MISSING")
        page = image["source_page"]
        if (type(page) is not int or page < 1 or not str(image["printed_page"])
                or page != row.get("source_page") or page != row["source_span"]["source_page"]):
            return fail("PAGE_BINDING_MISMATCH")
        refs, raws = proof["readings"], evidence["raw_reader_bytes"]
        if (len(refs) != 2 or len(raws) != 2 or refs[0]["sha256"] == refs[1]["sha256"]
                or refs[0]["relative_path"] == refs[1]["relative_path"]):
            return fail("TWO_RAW_RECORDS_REQUIRED")
        comparison = _time(proof["comparison_started_at"])
        completion = _time(proof["admission_completed_at"])
        if completion < comparison:
            return fail("TIME_ORDER_INVALID")
        readings, families, ids, times = [], [], [], []
        for entry, payload in zip(refs, raws):
            if _sha(payload) != entry["sha256"]:
                return fail("RAW_HASH_MISMATCH")
            raw = _json(payload)
            family = FAMILY_ALIASES.get(str(raw["model_family"]).lower())
            if not family or raw["contract_version"] != RAW_VERSION:
                return fail("READER_CONTRACT_OR_FAMILY_UNKNOWN")
            if (raw["method"] != "DIRECT_PAGE_IMAGE" or raw["independent_input"] is not True
                    or raw["saw_other_reader_output"] is not False or not raw["reader_id"]):
                return fail("INDEPENDENCE_NOT_PROVEN")
            binding = raw["input"]
            if binding != {"document_sha256": sha, "document_id": proof["document_id"],
                    "image_sha256": image["sha256"], "source_page": page,
                    "printed_page": image["printed_page"]}:
                return fail("INPUT_BINDING_MISMATCH")
            recorded, retained = _time(raw["recorded_at"]), _time(entry["retained_at"])
            if not (_time(source_record["observed_at"]) <= recorded <= retained < comparison <= completion):
                return fail("RAW_NOT_RETAINED_BEFORE_COMPARISON")
            families.append(family); ids.append(raw["reader_id"]); times.append(recorded)
            readings.append(raw["table"])
        if families[0] == families[1] or ids[0] == ids[1]:
            return fail("DIFFERENT_MODEL_FAMILIES_REQUIRED")
        selected = []
        for table in readings:
            columns = [c for c in table["columns"] if c["column_id"] == row["column_id"]]
            rows = [r for r in table["rows"] if r["line_code_literal"] == str(row["line_code"])]
            if len(columns) != 1 or len(rows) != 1:
                return fail("ROW_OR_COLUMN_AMBIGUOUS")
            cells = [c for c in rows[0]["cells"] if c["column_id"] == row["column_id"]]
            if len(cells) != 1:
                return fail("CELL_AMBIGUOUS")
            selected.append({name: table[name] for name in (
                "issuer_literal", "statement_title_literal", "scope_literal", "form_reference_literal",
                "currency_unit_literal", "period_caption_literal")})
            selected[-1].update(column=columns[0], row_label_literal=rows[0]["row_label_literal"],
                                line_code_literal=rows[0]["line_code_literal"], cell=cells[0])
        if selected[0] != selected[1]:
            return fail("LITERAL_DISAGREEMENT")
        agreed = selected[0]
        # Unknown glyphs or omitted literal metadata cannot be repaired by arithmetic.
        if ("UNREADABLE" in json.dumps(agreed, ensure_ascii=False).upper()
                or any(not agreed[k] for k in ("issuer_literal", "statement_title_literal", "scope_literal",
                       "form_reference_literal", "currency_unit_literal", "period_caption_literal"))):
            return fail("UNREADABLE_OR_MISSING_LITERAL")
        column, cell = agreed["column"], agreed["cell"]
        header = " ".join(column["label_literal"].casefold().split())
        year = str(row["reporting_period"]).split("-")[0]
        if header not in {"kỳ này", "năm nay", "current period", "current year", year, "năm " + year}:
            return fail("CURRENT_COLUMN_NOT_EXPLICIT")
        if (agreed["row_label_literal"] != row["raw_row_label"]
                or agreed["issuer_literal"] != row["issuer_literal"]
                or agreed["issuer_literal"] != source_record.get("issuer_name")
                or agreed["form_reference_literal"] != row["form_reference_literal"]
                or agreed["statement_title_literal"] != row["statement_title_literal"]
                or column["label_literal"] != row["current_period_label"]
                or column["reporting_period"] != row["reporting_period"]
                or column["role"] != "current" or not column["label_literal"]
                or recognize_period(agreed["period_caption_literal"])["period"] != row["reporting_period"]
                or recognize_scope(agreed["scope_literal"])["statement_scope"] != row["statement_scope"]):
            return fail("SEMANTIC_BINDING_MISMATCH")
        if (row.get("statement_family") != "income_statement"
                or {"revenue": "10", "net_income": "60", "attributable_net_income": "61"}.get(
                    row.get("canonical_metric")) != str(row.get("line_code"))
                or not re.search(r"B02A?-DN/HN\b", re.sub(r"\s+", "", agreed["form_reference_literal"]).upper())):
            return fail("ACCOUNTING_FORM_OR_ROW_IDENTITY_UNSUPPORTED")
        if cell.get("uncertainty") != []:
            return fail("UNRESOLVED_CELL_UNCERTAINTY")
        unit = parse_unit(agreed["currency_unit_literal"])
        if (not unit or unit["currency"] != row["currency"]
                or unit["unit_scale"] != row.get("source_unit_scale", row["unit_scale"])):
            return fail("CURRENCY_UNIT_MISMATCH")
        raw = cell["raw_value_literal"]
        sign = "parentheses" if str(raw).startswith("(") and str(raw).endswith(")") else "unsigned"
        if (raw != row["raw_value_text"] or cell["sign_literal"] != sign
                or parse_amount(raw) * unit["unit_scale"] != row["normalized_value"]):
            return fail("VALUE_OR_SIGN_MISMATCH")
        floor = max(*times, completion)
        if _time(row["knowledge_available_at"]) < floor:
            return fail("KNOWLEDGE_PRECEDES_COMPLETION")
        return {"valid": True, "reason_codes": [], "knowledge_floor": floor.isoformat(),
                "evidence_tier": EVIDENCE_TIER, "proof_sha256": ref["proof_sha256"],
                "raw_sha256": [r["sha256"] for r in refs], "model_families": families,
                "authority_effect": "OFFLINE_RESEARCH_ONLY", "pit_backtest_eligible": False}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return fail("MALFORMED_RETAINED_PROOF")
