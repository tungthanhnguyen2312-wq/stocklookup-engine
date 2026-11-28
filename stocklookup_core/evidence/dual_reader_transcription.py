"""Decision 2 retained image readings: byte replay only, no parser/LLM authority.

Corporate replay uses only the standard library; non-corporate rows additionally
call the bounded form contract. Admission supplies its existing numeric, unit
and period recognizers; none of its other gates is replaced.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "dual_reader_reviewed_transcription/v1"
RAW_VERSION = "independent_image_reading/v1"
EVIDENCE_TIER = "DUAL_READER_REVIEWED_TRANSCRIPTION"
PROOF_DIR = "dual-reader-transcriptions"
RIGHTS_ROUTE = "OWNER_APPROVED_OFFICIAL_ISSUER_RESEARCH_NOT_VIETSTOCK"
# Accounts, products and model versions do not create separate families.
FAMILY_ALIASES = {"openai-gpt": "gpt", "openai-chatgpt": "gpt", "gpt": "gpt", "codex": "gpt",
                  "google-gemini": "gemini", "gemini": "gemini",
                  "anthropic-claude": "claude", "claude": "claude"}

DUAL_READER_TTM_CONFIG_REL = "config/dual_reader_ttm_research_config.json"
DUAL_READER_TTM_CONFIG_SCHEMA = "dual_reader_ttm_research_config/v1"
RESEARCH_ONLY_COMPATIBILITY_CLASS = "DUAL_READER_OFFICIAL_H1_TTM_RESEARCH_ONLY"
RESEARCH_LIMITATIONS = ("OFFLINE_RESEARCH_ONLY", EVIDENCE_TIER,
                        "NOT_PIT_BACKTEST_ELIGIBLE", "PEER_COHORT_ISOLATED")
RESEARCH_METHOD_FIELDS = ("evidence_tier", "authority_effect", "pit_backtest_eligible",
    "knowledge_available_at", "earnings_attribution", "ttm_compatibility_class",
    "research_caveats", "share_basis_caveats", "share_authority", "share_observation_date",
    "share_observation_lag_days", "ttm_operand_provenance")
RESEARCH_METHOD_FIELDS += ("required_research_caveat_codes",)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CAVEAT_STATES = frozenset({"VERIFIED", "LEAD", "ESTIMATE_UNVERIFIED",
    "LOCATED_TEXT_IMAGE_PENDING", "VERIFIED_TEXT_LAYER_IMAGE_PENDING",
    "VERIFIED_POLICY_TEXT_ESTIMATE_IMPACT_UNVERIFIED",
    "VERIFIED_PRETAX_GROUP_GAIN_SUBSIDIARY_DETAIL_LEAD"})


class DualReaderTtmConfigCorruptError(ValueError):
    pass


class DualReaderTtmIntegrityError(ValueError):
    pass


def research_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("TIMESTAMP_INVALID")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("TIMESTAMP_TIMEZONE_REQUIRED")
    return stamp


def _load_strict_json_bytes(raw: bytes) -> Any:
    if len(raw) > 1024 * 1024:
        raise DualReaderTtmConfigCorruptError("CONFIG_SIZE_INVALID")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DualReaderTtmConfigCorruptError("CONFIG_DUPLICATE_KEY")
            result[key] = value
        return result
    def constant(value):
        raise DualReaderTtmConfigCorruptError("CONFIG_JSON_INVALID:NON_FINITE")
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            constant(value)
        return parsed
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, DualReaderTtmConfigCorruptError):
            raise
        raise DualReaderTtmConfigCorruptError("CONFIG_JSON_INVALID") from exc


def _config_schema(config: Any) -> None:
    def require(condition):
        if not condition:
            raise ValueError("CONFIG_SCHEMA_INVALID")
    require(isinstance(config, dict) and set(config) == {
        "schema_version", "revision", "enabled", "approved_at", "approved_by",
        "max_knowledge_cutoff_override", "evidence_subdirs", "research_caveats", "share_basis_caveats"})
    require(config["schema_version"] == DUAL_READER_TTM_CONFIG_SCHEMA and config["revision"] == "r0001")
    require(type(config["enabled"]) is bool and isinstance(config["approved_by"], str) and bool(config["approved_by"].strip()))
    research_timestamp(config["approved_at"])
    require(config["max_knowledge_cutoff_override"] is None)
    require(isinstance(config["evidence_subdirs"], list) and isinstance(config["research_caveats"], list))
    seen = set()
    for entry in config["evidence_subdirs"]:
        require(isinstance(entry, dict) and set(entry) == {"subdir", "ticker", "reporting_period",
            "approved_at", "rows_file", "rows_sha256", "document_sha256", "proof_sha256", "enabled"})
        require(isinstance(entry["subdir"], str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+", entry["subdir"])))
        require(entry["subdir"] not in seen)
        seen.add(entry["subdir"])
        require(bool(re.fullmatch(r"[A-Z0-9]+", entry["ticker"]))
                and bool(re.fullmatch(r"[0-9]{4}(?:-H1)?", entry["reporting_period"])))
        require(entry["rows_file"] == "dual_reader_admitted_rows.jsonl" and type(entry["enabled"]) is bool)
        research_timestamp(entry["approved_at"])
        for key in ("rows_sha256", "proof_sha256", "document_sha256"):
            require(isinstance(entry[key], str) and _SHA256.fullmatch(entry[key]))
    required = {"code", "ticker", "reporting_period", "document_sha256", "verification_status",
                "never_adjust_multiples", "pb_gate", "ttm_gate", "note"}
    optional = {"null_sha_reason", "recorded_at", "knowledge_available_at"}
    for entry in config["research_caveats"]:
        require(isinstance(entry, dict) and required <= set(entry) <= required | optional)
        require(isinstance(entry["code"], str) and bool(re.fullmatch(r"[A-Z0-9_]+", entry["code"])))
        require(isinstance(entry["ticker"], str) and bool(re.fullmatch(r"[A-Z0-9]+", entry["ticker"])))
        require(isinstance(entry["reporting_period"], str)
                and bool(re.fullmatch(r"[0-9]{4}(?:-H1|-9M)?", entry["reporting_period"])))
        sha = entry["document_sha256"]
        require((isinstance(sha, str) and _SHA256.fullmatch(sha)) or
                (sha is None and isinstance(entry.get("null_sha_reason"), str) and bool(entry["null_sha_reason"].strip())))
        require(entry["verification_status"] in _CAVEAT_STATES and entry["never_adjust_multiples"] is True)
        require(entry["pb_gate"] in {"LABEL_ONLY", "FAIL_CLOSED"} and entry["ttm_gate"] in {"LABEL_ONLY", "FAIL_CLOSED"})
        require(isinstance(entry["note"], str) and bool(entry["note"].strip()))
        for key in ("recorded_at", "knowledge_available_at"):
            if key in entry:
                research_timestamp(entry[key])
    require(isinstance(config["share_basis_caveats"], dict) and set(config["share_basis_caveats"]) == {
        "provider_reported_lagged", "official_registered_shares"})
    for authority, entry in config["share_basis_caveats"].items():
        require(isinstance(entry, dict) and set(entry) == {"code", "verification_status", "pb_gate", "ttm_gate", "note"})
        require(entry["code"] == {"provider_reported_lagged": "SHARE_BASIS_LAGGED_PROVIDER_ISSUED",
            "official_registered_shares": "SHARE_BASIS_VSDC_REGISTERED_INCLUDES_TREASURY"}[authority])
        require(entry["verification_status"] == "VERIFIED" and entry["pb_gate"] == entry["ttm_gate"] == "LABEL_ONLY")
        require(isinstance(entry["note"], str) and bool(entry["note"].strip()))


def load_dual_reader_ttm_research_config(repo_root: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    path = root / DUAL_READER_TTM_CONFIG_REL
    try:
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise DualReaderTtmConfigCorruptError("CONFIG_PATH_ESCAPE")
    except (OSError, RuntimeError) as exc:
        raise DualReaderTtmConfigCorruptError("CONFIG_PATH_ESCAPE") from exc
    try:
        with path.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
    except FileNotFoundError as exc:
        raise DualReaderTtmConfigCorruptError("CONFIG_MISSING") from exc
    except OSError as exc:
        raise DualReaderTtmConfigCorruptError("CONFIG_UNREADABLE") from exc
    config = _load_strict_json_bytes(raw)
    try:
        _config_schema(config)
    except (ValueError, TypeError, KeyError) as exc:
        raise DualReaderTtmConfigCorruptError("CONFIG_SCHEMA_INVALID") from exc
    if expected_sha256 is None:
        try:
            pin = root / "config/owner_daily_capacity_qualification.json"
            if not pin.resolve().is_relative_to(root) or pin.is_symlink():
                raise ValueError("CONFIG_PATH_ESCAPE")
            expected_sha256 = _load_strict_json_bytes(pin.read_bytes())["source_sha256"][DUAL_READER_TTM_CONFIG_REL]
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise DualReaderTtmConfigCorruptError("CONFIG_DIGEST_ANCHOR_INVALID") from exc
    if not isinstance(expected_sha256, str) or hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() != expected_sha256:
        raise DualReaderTtmConfigCorruptError("CONFIG_DIGEST_MISMATCH")
    return config


def bind_sha_caveats(*, ticker: str, operands: Sequence[Mapping[str, Any]],
                     config: Mapping[str, Any], cutoff: str | None = None) -> list[dict[str, Any]]:
    identities = {(r.get("reporting_period"), r.get("document_sha256")) for r in operands}
    result = []
    for entry in config["research_caveats"]:
        if (entry["ticker"] != ticker or entry["document_sha256"] is None
                or (entry["reporting_period"], entry["document_sha256"]) not in identities):
            continue
        if cutoff and any(research_timestamp(entry[key]) > research_timestamp(cutoff)
                          for key in ("recorded_at", "knowledge_available_at") if key in entry):
            continue
        result.append({**entry, "source_verification_status": entry["verification_status"]})
    return result


def evaluate_share_basis_caveat_gate(*, ticker: str, share_basis_input: Mapping[str, Any] | None,
        bound_caveats: Sequence[Mapping[str, Any]], config: Mapping[str, Any], cutoff: str | None = None) -> dict[str, Any]:
    share = share_basis_input or {}
    authority = share.get("authority")
    caveat = config["share_basis_caveats"].get(authority)
    caveats = [{**caveat, "never_adjust_multiples": True,
                "source_verification_status": caveat["verification_status"],
                "observation_date": share.get("observation_date"),
                "observation_lag_days": share.get("observation_lag_days")}] if caveat else []
    blocked = False
    observation = share.get("observation_date")
    if cutoff and observation is not None:
        try:
            # A date is a session label; a timestamp must additionally respect the exact cutoff.
            if len(observation) == 10:
                datetime.strptime(observation, "%Y-%m-%d")
                blocked = observation > cutoff[:10]
            else:
                blocked = research_timestamp(observation) > research_timestamp(cutoff)
        except (ValueError, TypeError):
            blocked = True
    def blockers(key):
        return (["SHARE_BASIS_AFTER_KNOWLEDGE_CUTOFF"] if blocked else []) + [
            c["code"] for c in bound_caveats if c.get(key) == "FAIL_CLOSED"]
    return {"share_basis_caveats": caveats, "share_authority": authority,
        "share_observation_date": observation, "share_observation_lag_days": share.get("observation_lag_days"),
        "share_basis_cutoff_blocked": blocked, "pb_blocked": bool(blockers("pb_gate")),
        "ttm_blocked": bool(blockers("ttm_gate")), "pb_blockers": blockers("pb_gate"), "ttm_blockers": blockers("ttm_gate")}


def load_admitted_rows(evidence_root: Path, entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Read exactly the frozen rows and proof references; common admission still owns qualification."""
    root = Path(evidence_root).resolve()
    rows = []
    for entry in entries:
        landing = root / entry["subdir"]
        path = landing / entry["rows_file"]
        try:
            if (landing.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root)
                    or not landing.resolve().is_relative_to(root)):
                raise DualReaderTtmIntegrityError("EVIDENCE_PATH_ESCAPE")
        except (OSError, RuntimeError) as exc:
            raise DualReaderTtmIntegrityError("EVIDENCE_PATH_ESCAPE") from exc
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["rows_sha256"]:
                raise DualReaderTtmIntegrityError("ROWS_DIGEST_MISMATCH:" + entry["subdir"])
            admitted = [_load_strict_json_bytes(line) for line in raw.splitlines() if line.strip()]
            if not admitted:
                raise DualReaderTtmIntegrityError("ROWS_EMPTY")
            for row in admitted:
                if (row.get("ticker"), row.get("reporting_period"), row.get("document_sha256"), row.get("evidence_subdir")) != (
                        entry["ticker"], entry["reporting_period"], entry["document_sha256"], entry["subdir"]):
                    raise DualReaderTtmIntegrityError("ROW_IDENTITY_MISMATCH")
                ref = row.get("dual_reader_transcription") or {}
                proof = landing / str(ref.get("relative_path") or "")
                if not proof.resolve().is_relative_to(landing.resolve()) or proof.is_symlink():
                    raise DualReaderTtmIntegrityError("PROOF_PATH_ESCAPE")
                if (ref.get("proof_sha256") != entry["proof_sha256"]
                        or hashlib.sha256(proof.read_bytes()).hexdigest() != entry["proof_sha256"]):
                    raise DualReaderTtmIntegrityError("PROOF_DIGEST_MISMATCH")
            rows.extend(admitted)
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
            if isinstance(exc, DualReaderTtmIntegrityError):
                raise
            raise DualReaderTtmIntegrityError("EVIDENCE_UNREADABLE:" + entry["subdir"]) from exc
    return rows


# A printed outline enumerator ("3.", "17.", "17.1", "18") sits in the statement's
# numbering column, separate from the line item text and from the Ma so line code.
_OUTLINE_ENUMERATOR = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*\.?)\s+(?=\S)")


def printed_page_identity(literal: Any) -> Any:
    """Strip one exact 'Trang ' only before ASCII digits; preserve all other bytes."""
    if isinstance(literal, str) and re.fullmatch(r"Trang [0-9]+", literal):
        return literal[len("Trang "):]
    return literal


def input_binding_matches(actual: Any, expected: Mapping[str, Any]) -> bool:
    """Only the printed-page prefix exception applies to a raw input binding."""
    if not isinstance(actual, Mapping) or actual.keys() != expected.keys():
        return False
    return all((printed_page_identity(actual[k]) == printed_page_identity(v)
                if k == "printed_page" else actual[k] == v) for k, v in expected.items())


def form_code_literal(literal: str) -> str:
    """A trailing circular line is excluded, with exactly one space or LF separator.

    Some retained readers flatten the printed line break to one space. No other
    separator, circular spelling, suffix or change to the form itself is accepted.
    """
    match = re.fullmatch(r"([^\n]+?)[ \n]Thông tư số [0-9]+/[0-9]{4}/TT-BTC", literal)
    return match.group(1) if match else literal


def agreed_vnd_unit(tables, parse_unit) -> dict | None:
    """Two byte-identical statement-page literals, parsed by the existing unit owner.

    This helper does not prove provenance or qualify metadata; the complete raw
    proof must still pass verify_dual_reader_transcription before it has authority.
    """
    if len(tables) != 2:
        return None
    literal = tables[0].get("currency_unit_literal")
    if not isinstance(literal, str) or not literal or literal != tables[1].get("currency_unit_literal"):
        return None
    unit = _unit(literal, parse_unit)
    if (not unit or unit.get("currency") != "VND" or type(unit.get("unit_scale")) is not int
            or unit["unit_scale"] <= 0):
        return None
    return {**unit, "evidence_text": literal}


_H1_LITERALS = (
    re.compile(r"(?:Cho kỳ kế toán )?0?6 tháng đầu năm ([0-9]{4})"),
    # English statements of Vietnamese issuers (e.g. POW): "For the 6-month period ended 30 June YYYY".
    re.compile(r"(?:For the )?6-month period ended 30 June ([0-9]{4})"),
)


def vn_first_half_period(literal: Any) -> str | None:
    """Exact first-half literal -> "YYYY-H1".

    Accepted literals (whole string, whitespace-collapsed): "[Cho kỳ kế toán ]06 tháng đầu năm YYYY"
    and "[For the ]6-month period ended 30 June YYYY". Used only where the shared statement-period
    recognizer returns no period; any other wording, extra text or month count stays unrecognized.
    """
    if not isinstance(literal, str):
        return None
    text = " ".join(literal.split())
    for pattern in _H1_LITERALS:
        match = pattern.fullmatch(text)
        if match:
            return match.group(1) + "-H1"
    return None


def signed_cell_literal(raw: Any, sign_literal: Any) -> str | None:
    """The displayed accounting literal implied by one reader cell, or None if inconsistent.

    The reader contract records digits without parentheses plus sign_literal. "parentheses"
    therefore means the printed value was "(digits)". A literal already carrying its own
    parentheses is kept (legacy readings) only when sign_literal says the same. Any other sign
    vocabulary, or a mismatch between the two, is refused; no sign is ever inferred.
    """
    if not isinstance(raw, str) or not raw:
        return None
    wrapped = raw.startswith("(") and raw.endswith(")")
    if sign_literal == "unsigned":
        return None if ("(" in raw or ")" in raw) else raw
    if sign_literal == "parentheses":
        if wrapped:
            return raw
        return None if ("(" in raw or ")" in raw) else "(" + raw + ")"
    return None


def split_outline_enumerator(label: str) -> tuple[str | None, str]:
    """Split only a leading numbering-column token; the line item text is kept verbatim.

    No letter, digit or accent is changed. Callers still compare the remaining text
    exactly, and two printed enumerators must agree exactly.
    """
    match = _OUTLINE_ENUMERATOR.match(str(label))
    return (match.group(1), str(label)[match.end():]) if match else (None, str(label))


def _column_binding(column: Mapping[str, Any], caption: Any) -> dict:
    """A column period that is absent, or the exact shared caption, is bound by that caption.

    Any other literal is kept verbatim and must itself agree between readers.
    """
    literal = column["reporting_period"]
    return {"column_id": column["column_id"], "label_literal": column["label_literal"], "role": column["role"],
            "reporting_period": None if literal is None or literal == caption else literal}


def _agreed_column_label(first: str, second: str, unit_literal: str) -> tuple[str | None, str | None]:
    """Owner-approved PNJ rule 1: identical labels agree; otherwise one label may equal the other
    followed by whitespace and a final token that is exactly the agreed currency/unit literal.

    Returns the shorter (agreed) label and the normalization applied; any other difference is None.
    """
    if first == second:
        return first, None
    for short, long in ((first, second), (second, first)):
        if (short and unit_literal and long.startswith(short)
                and re.fullmatch(r"\s+" + re.escape(unit_literal), long[len(short):])):
            return short, "TRAILING_CURRENCY_UNIT_TOKEN"
    return None, None


# Head Leader decision 2026-11-24: for accounting-form identity only, these dashes match ASCII '-'.
_FORM_DASH_VARIANTS = {"\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-"}


def _form_identity_text(literal: str) -> tuple[str, bool]:
    """Matching key for the printed form reference; the agreed literal itself is never changed.

    Whitespace is ignored (as before) and only the four dash variants map to '-'.
    """
    text = re.sub(r"\s+", "", str(literal))
    keyed = text.translate(str.maketrans(_FORM_DASH_VARIANTS))
    return keyed.upper(), keyed != text


def _label_period(label: str, recognize_period) -> str | None:
    """Owner-approved PNJ rule 2: a column label states its own period (recognizer, or a bare year)."""
    recognized = recognize_period(label)["period"]
    if recognized:
        return recognized
    text = " ".join(str(label).split())
    return text if re.fullmatch(r"(?:19|20)\d{2}", text) else None


def _unit(literal: str, parse_unit) -> dict | None:
    """Owner-approved PNJ rule 3: the whole literal 'VND' declares VND at scale 1.

    The existing parser does not accept a bare 'VND'; every other literal keeps its handling.
    """
    if literal == "VND":
        return {"currency": "VND", "unit_scale": 1, "unit_label": "VND", "evidence_text": literal,
                "label_recognition": "DUAL_READER_BARE_VND_TABLE_UNIT"}
    return parse_unit(literal)


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
        result = {"proof_bytes": proof_bytes,
                "raw_reader_bytes": [read(item["relative_path"]) for item in refs],
                "image_bytes": read(proof["page_image"]["relative_path"])}
        # Corporate replay performs exactly its existing reads. Supplementary
        # note evidence classifies securities code 201 only, never a note fact.
        if (row.get("canonical_metric") == "securities_profit_allocated_to_owners"
                and "appropriation_note" in proof):
            note = proof["appropriation_note"]
            result["appropriation_note"] = {
                "raw_reader_bytes": [read(item["relative_path"]) for item in note["readings"]],
                "image_bytes": read(note["page_image"]["relative_path"])}
        return result
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
        readings, families, ids, times, printed_pages = [], [], [], [], []
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
            if not input_binding_matches(binding, {"document_sha256": sha, "document_id": proof["document_id"],
                    "image_sha256": image["sha256"], "source_page": page,
                    "printed_page": image["printed_page"]}):
                return fail("INPUT_BINDING_MISMATCH")
            recorded, retained = _time(raw["recorded_at"]), _time(entry["retained_at"])
            if not (_time(source_record["observed_at"]) <= recorded <= retained < comparison <= completion):
                return fail("RAW_NOT_RETAINED_BEFORE_COMPARISON")
            families.append(family); ids.append(raw["reader_id"]); times.append(recorded)
            printed_pages.append(binding["printed_page"])
            readings.append(raw["table"])
        if families[0] == families[1] or ids[0] == ids[1]:
            return fail("DIFFERENT_MODEL_FAMILIES_REQUIRED")
        selected, enumerators = [], []
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
            enumerator, label = split_outline_enumerator(rows[0]["row_label_literal"])
            enumerators.append(enumerator)
            selected[-1].update(column=_column_binding(columns[0], table["period_caption_literal"]),
                                row_label_literal=label, line_code_literal=rows[0]["line_code_literal"], cell=cells[0])
        forms = [item["form_reference_literal"] for item in selected]
        for item in selected:
            item["form_reference_literal"] = form_code_literal(item["form_reference_literal"])
        labels = [item["column"].pop("label_literal") for item in selected]
        agreed_label, label_normalization = _agreed_column_label(
            labels[0], labels[1], selected[0]["currency_unit_literal"])
        if (selected[0] != selected[1] or agreed_label is None
                or (None not in enumerators and enumerators[0] != enumerators[1])):
            return fail("LITERAL_DISAGREEMENT")
        agreed = selected[0]
        agreed["column"]["label_literal"] = agreed_label
        # Unknown glyphs or omitted literal metadata cannot be repaired by arithmetic.
        if ("UNREADABLE" in json.dumps(agreed, ensure_ascii=False).upper()
                or any(not agreed[k] for k in ("issuer_literal", "statement_title_literal", "scope_literal",
                       "form_reference_literal", "currency_unit_literal", "period_caption_literal"))):
            return fail("UNREADABLE_OR_MISSING_LITERAL")
        column, cell = agreed["column"], agreed["cell"]
        caption_period = (recognize_period(agreed["period_caption_literal"])["period"]
                          or vn_first_half_period(agreed["period_caption_literal"]))
        if caption_period is None and agreed["form_reference_literal"] == "B02a-CTCK/HN":
            from stocklookup_core.evidence.dual_reader_form_contract import income_period_literal
            caption_period = income_period_literal(agreed["form_reference_literal"], agreed["period_caption_literal"])
        if caption_period is None:
            # Rule 2: a caption without a period defers to the current column's own label, which must
            # equal both the fact period and the qualified document metadata period.
            claims = (row.get("document_metadata") or {}).get("metadata_claims") or {}
            label_period = _label_period(column["label_literal"], recognize_period)
            if (label_period == row["reporting_period"]
                    and label_period == (claims.get("reporting_period") or {}).get("value")
                    and column["role"] == "current"):
                caption_period = label_period
        # Caption-bound columns reuse the validated resolution, including the yearless fallback.
        column_period = caption_period if column["reporting_period"] is None else (
            column["reporting_period"] if column["reporting_period"] == row["reporting_period"]
            else (recognize_period(column["reporting_period"])["period"]
                  or vn_first_half_period(column["reporting_period"])))
        if column_period is None and agreed["form_reference_literal"] == "B02a-CTCK/HN":
            from stocklookup_core.evidence.dual_reader_form_contract import income_period_literal
            column_period = income_period_literal(agreed["form_reference_literal"], column["reporting_period"])
        header = " ".join(column["label_literal"].casefold().split())
        year = str(row["reporting_period"]).split("-")[0]
        # The explicit annual header already accepts "Năm YYYY" below. When
        # readers repeat that same literal as the column period, bind its year
        # consistently; the independent caption must still prove the same FY.
        # Do not apply this to H1, another period literal or a contrary caption.
        if (column_period is None and row["reporting_period"] == year
                and caption_period == year
                and column["reporting_period"] == column["label_literal"]
                and header == "năm " + year):
            column_period = year
        # An H1 current column may print its own explicit half-year header; it is accepted
        # only for an H1 fact of that same year (the caption check below must still agree).
        h1_headers = ({"06 tháng đầu năm " + year, "6 tháng đầu năm " + year}
                      if str(row["reporting_period"]) == year + "-H1" else set())
        if header not in {"kỳ này", "năm nay", "current period", "current year", year, "năm " + year,
                          *h1_headers}:
            if agreed["form_reference_literal"] != "B02a-CTCK/HN":
                return fail("CURRENT_COLUMN_NOT_EXPLICIT")
            from stocklookup_core.evidence.dual_reader_form_contract import current_column_identity
            if not current_column_identity(agreed["form_reference_literal"], row["reporting_period"],
                                           column["label_literal"]):
                return fail("CURRENT_COLUMN_NOT_EXPLICIT")
        if (agreed["row_label_literal"] != row["raw_row_label"]
                or agreed["issuer_literal"] != row["issuer_literal"]
                or agreed["issuer_literal"] != source_record.get("issuer_name")
                or agreed["form_reference_literal"] != form_code_literal(row["form_reference_literal"])
                or agreed["statement_title_literal"] != row["statement_title_literal"]
                or column["label_literal"] != row["current_period_label"]
                or column_period != row["reporting_period"]
                or column["role"] != "current" or not column["label_literal"]
                or caption_period != row["reporting_period"]
                or recognize_scope(agreed["scope_literal"])["statement_scope"] != row["statement_scope"]):
            return fail("SEMANTIC_BINDING_MISMATCH")
        form_key, form_dash_variant = _form_identity_text(agreed["form_reference_literal"])
        corporate_form = bool(re.search(r"B02A?-DN/HN\b", form_key))
        form_evidence = {}
        if corporate_form and (row.get("statement_family") != "income_statement"
                or {"revenue": "10", "net_income": "60", "attributable_net_income": "61"}.get(
                    row.get("canonical_metric")) != str(row.get("line_code"))):
            return fail("ACCOUNTING_FORM_OR_ROW_IDENTITY_UNSUPPORTED")
        if not corporate_form:
            from stocklookup_core.evidence.dual_reader_form_contract import (
                CONTRACT_VERSION as form_contract_version, row_identity, verify_appropriation_basis)
            if not row_identity(agreed["form_reference_literal"], row.get("statement_family"),
                    row.get("reporting_period"), row.get("line_code"),
                    agreed["row_label_literal"], row.get("canonical_metric")):
                return fail("ACCOUNTING_FORM_OR_ROW_IDENTITY_UNSUPPORTED")
            form_evidence = {"form_identity_contract": form_contract_version,
                             "form_family": "securities_company_income_statement",
                             "valuation_applicability": {"P/S": "NOT_APPLICABLE", "EV/EBITDA": "NOT_APPLICABLE"}}
            if str(row.get("line_code")) == "201":
                basis = verify_appropriation_basis(row, evidence.get("appropriation_note"),
                    proof=proof, source_record=source_record, families=families,
                    family_aliases=FAMILY_ALIASES, time=_time,
                    input_binding_matches=input_binding_matches, signed_cell_literal=signed_cell_literal,
                    recognize_scope=recognize_scope)
                if not basis["valid"]:
                    return basis
                form_evidence["appropriation_basis"] = basis["appropriation_basis"]
        if cell.get("uncertainty") != []:
            return fail("UNRESOLVED_CELL_UNCERTAINTY")
        unit = agreed_vnd_unit(readings, parse_unit)
        if (not unit or unit["currency"] != row["currency"]
                or unit["unit_scale"] != row.get("source_unit_scale", row["unit_scale"])):
            return fail("CURRENCY_UNIT_MISMATCH")
        raw = cell["raw_value_literal"]
        signed = signed_cell_literal(raw, cell.get("sign_literal"))
        if (signed is None or signed != row["raw_value_text"]
                or parse_amount(signed) * unit["unit_scale"] != row["normalized_value"]):
            return fail("VALUE_OR_SIGN_MISMATCH")
        normalizations = []
        if any(form_code_literal(f) != f for f in forms):
            normalizations.append({"field": "form_reference_literal", "reader_literals": forms,
                                   "agreed": agreed["form_reference_literal"], "rule": "TRAILING_CIRCULAR_REFERENCE_LINE"})
        if any(p != image["printed_page"] for p in printed_pages):
            normalizations.append({"field": "input.printed_page", "reader_literals": printed_pages,
                                   "agreed": image["printed_page"], "rule": "LEADING_TRANG_PAGE_PREFIX"})
        if label_normalization:
            normalizations.append({"field": "column.label_literal", "column_id": row["column_id"],
                                   "reader_literals": labels, "agreed": agreed_label, "rule": label_normalization})
        if form_dash_variant:
            normalizations.append({"field": "form_reference_literal", "agreed": agreed["form_reference_literal"],
                                   "matched_as": form_key, "rule": "FORM_REFERENCE_DASH_VARIANT"})
        floor = max(*times, completion)
        if _time(row["knowledge_available_at"]) < floor:
            return fail("KNOWLEDGE_PRECEDES_COMPLETION")
        return {"valid": True, "reason_codes": [], "knowledge_floor": floor.isoformat(),
                "evidence_tier": EVIDENCE_TIER, "proof_sha256": ref["proof_sha256"],
                "raw_sha256": [r["sha256"] for r in refs], "model_families": families,
                "statement_unit_evidence": {"document_sha256": sha, "source_page": page,
                    "currency": unit["currency"], "unit_scale": unit["unit_scale"],
                    "literal": agreed["currency_unit_literal"], "proof_sha256": ref["proof_sha256"]},
                "authority_effect": "OFFLINE_RESEARCH_ONLY", "pit_backtest_eligible": False,
                **form_evidence,
                **({"literal_normalizations": normalizations} if normalizations else {})}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return fail("MALFORMED_RETAINED_PROOF")
