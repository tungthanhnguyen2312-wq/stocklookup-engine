"""Seal and replay one retained Decision 2 dual-reader page (offline research only).

Deterministic, no network and no model calls. The tool never edits the original
evidence: it copies the official PDF, the page image and the two raw reader files
byte-identically (sha256 verified) into a NEW retained evidence subdirectory,
writes a manifest record that carries the explicit rights fields and image
binding, seals the proof once, builds the current-column income rows from the
agreed literals and replays them through the common retained admission owner.

An existing sealed file is reused only when its bytes are identical; nothing is
repaired or rewritten, and the sealed ``admission_completed_at`` is never moved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT  # noqa: E402
from stocklookup_core.evidence import dual_reader_transcription as dual  # noqa: E402

TOOL_VERSION = "run_dual_reader_transcription_admission/v1"
MANIFEST = "official_document_acquisition_manifest.json"
INDEPENDENT_ROUTE = "INDEPENDENT_OFFICIAL_SOURCE"
RIGHTS_STATUS = "RESEARCH_AND_AI_READING_APPROVED"
METRICS = (("revenue", "10"), ("net_income", "60"), ("attributable_net_income", "61"))
# Same exact registered legal names as official_ocr_layout_proof.retained_issuer_name_matches.
REGISTERED_ISSUER_FOLD = {"HPG": "cong ty co phan tap doan hoa phat",
                          "PNJ": "cong ty co phan vang bac da quy phu nhuan",
                          "VRE": "cong ty co phan vincom retail",
                          "NVL": "cong ty co phan tap doan dau tu dia oc no va"}

# The one retained page this v1 run seals. Every value here is checked against bytes.
HPG_2025_H1_P10 = {
    "ticker": "HPG", "reporting_period": "2025-H1",
    "document_sha256": "ebb7e9eead6404301473582fc879e63feb4ca09eecbc92ccf98dab63f97b7eb9",
    "document_id": "e4c57c5a39b3f2a1a09a352b4022fe19fca55cf618283e7a393ec91f40744c56",
    "original_subdir": "h1-2025-q3-20261124",
    "new_subdir": "h1-2025-dual-reader-hpg-20261124",
    "page_key": "hpg-2025h1-p10",
    "source_page": 10, "printed_page": "8",
    "image_sha256": "d9369a945cbdb3a7e560bb6b7d45dc3fc8fc9d31e7a477ca52ac6659ca98d436",
    "column_id": "c1",
    # Retention instants recorded by the Head Leader before comparison (file mtimes agree).
    "readings": (("claude", "blind-input-hpg-2025h1-p10/claude/claude-reader.raw.json", "2026-11-24T21:28:21+07:00"),
                 ("gemini", "blind-input-hpg-2025h1-p10/gemini/gemini-reader.raw.json", "2026-11-24T21:30:47+07:00")),
    "image": "official-hpg-h1-2025/page-10.png",
    "render_meta": "official-hpg-h1-2025/input.meta.json",
    "comparison_started_at": "2026-11-24T21:33:00+07:00",
}

PNJ_2025_P10 = {
    "ticker": "PNJ", "reporting_period": "2025",
    "document_sha256": "309f86836d9f00b37e3cccb25da9e7ffd0dab6c531be995618542004acccdf1d",
    "document_id": "964efd1c800de93d643eebc42476aaf7eadb465a256f1a48f04be2e25e3ad888",
    "original_subdir": "currency-refresh-20260929",
    "new_subdir": "fy2025-dual-reader-pnj-20261124",
    "page_key": "pnj-fy2025-p10",
    "source_page": 10, "printed_page": "8",
    "image_sha256": "4df1be5fb096b9745126885f93bb063aba82c349f58a35c2b15cd56ba41e53d1",
    "column_id": "c1",
    # Claude: raw file write completed 21:52:44.08 (mtime, rounded up); Gemini: comparison record.
    "readings": (("claude", "blind-input-pnj-fy2025-p10/claude/claude-reader.raw.json", "2026-11-24T21:52:45+07:00"),
                 ("gemini", "blind-input-pnj-fy2025-p10/gemini/gemini-reader.raw.json", "2026-11-24T21:55:01+07:00")),
    "image": "blind-input-pnj-fy2025-p10/render/page-10.png",
    "render_meta": "blind-input-pnj-fy2025-p10/input.meta.json",
    "comparison_started_at": "2026-11-24T21:55:24+07:00",
}

# Retention instants: raw file write completion (mtime) rounded up to the next second.
PNJ_2025_H1_P10 = {
    "ticker": "PNJ", "reporting_period": "2025-H1",
    "document_sha256": "12c40161cdb31ef603256892dbe70a2bba6a906c5b2e033ed281cb321466601c",
    "document_id": "9621d34b3740d6408ba52f31d5e167dd3046a99395d389680ce9cadf643d696d",
    "original_subdir": "h1-2025-q3-20261124",
    "new_subdir": "h1-2025-dual-reader-pnj-20261124",
    "page_key": "pnj-2025h1-p10",
    "source_page": 10, "printed_page": "8",
    "image_sha256": "ee674c9b3b79d6c0dff38932c501f74579e03cef14e32bf17ba4238dd3c6d05b",
    "column_id": "c1",
    "readings": (("claude", "blind-input-pnj-2025h1-p10/claude/claude-reader.raw.json", "2026-11-24T22:19:31+07:00"),
                 ("gemini", "blind-input-pnj-2025h1-p10/gemini/gemini-reader.raw.json", "2026-11-24T22:22:10+07:00")),
    "image": "blind-input-pnj-2025h1-p10/claude/page-10.png",
    "render_meta": "blind-input-pnj-2025h1-p10/input.meta.json",
    "comparison_started_at": "2026-11-24T22:25:04+07:00",
}

VRE_2025_P11 = {
    "ticker": "VRE", "reporting_period": "2025",
    "document_sha256": "85b250e9bd3b87aac9a1f650363f7063b2a830f6f4f1dda07eb6eecd09063a3e",
    "document_id": "5a05c0f2a5831663628922733c937615a43ce992d265a460c5a16eab233e84aa",
    "original_subdir": "currency-refresh-20260929",
    "new_subdir": "fy2025-dual-reader-vre-20261124",
    "page_key": "vre-fy2025-p11",
    "source_page": 11, "printed_page": "9",
    "image_sha256": "be921abae56e5d0b09dcaf5b8bd78609d43a3ad1301ecffe83ac45cc89b96b40",
    "column_id": "c1",
    "readings": (("claude", "blind-input-vre-fy2025-p11/claude/claude-reader.raw.json", "2026-11-24T22:19:24+07:00"),
                 ("gemini", "blind-input-vre-fy2025-p11/gemini/gemini-reader.raw.json", "2026-11-24T22:23:16+07:00")),
    "image": "blind-input-vre-fy2025-p11/claude/page-11.png",
    "render_meta": "blind-input-vre-fy2025-p11/input.meta.json",
    "comparison_started_at": "2026-11-24T22:25:06+07:00",
}

# HL-20261125-CDX-08 retained inputs. NVL H1/2025 keeps Claude's literal
# "10"; Gemini's "Trang 10" fails exact input binding (no normalization).
POW_2025_P11 = {
    "page_key": "pow-fy2025-p11",
    "ticker": "POW",
    "reporting_period": "2025",
    "document_sha256": "54077f6abf8f31ce54eb92fd92e00ae107fe30cb9fabac2829dfb911b49bcbe7",
    "document_id": "cb601f58d70aa060d082f5b48d659477dcf7cf28b6514bd4c0a103fc11a72baf",
    "original_subdir": "gem1-04-acquisition-20261125",
    "source_page": 11,
    "image_sha256": "fde535333f1ac65b7e40b613229e8906fb3d34be66ade252ec081ef4c2a752c5",
    "image": "blind-input-pow-fy2025-p11/claude/page-11.png",
    "render_meta": "blind-input-pow-fy2025-p11/input.meta.json",
    "readings": [
        [
            "claude",
            "blind-input-pow-fy2025-p11/claude-r2/claude-reader.raw.json",
            "2026-11-25T12:26:53+07:00"
        ],
        [
            "gemini",
            "blind-input-pow-fy2025-p11/gemini/gemini-reader.raw.json",
            "2026-11-25T12:05:04+07:00"
        ]
    ],
    "new_subdir": "fy2025-dual-reader-pow-20261125",
    "printed_page": "7",
    "column_id": "c1",
    "comparison_started_at": "2026-11-25T12:27:10+07:00"
}

POW_2025_H1_P11 = {
    "page_key": "pow-2025h1-p11",
    "ticker": "POW",
    "reporting_period": "2025-H1",
    "document_sha256": "e56815b230d3130816b1169055691d3dc6ce6b67af932a651db69b6da52045c1",
    "document_id": "422afc62b2d433875eb5db8dfa80e0103932a53f2c4a680edade3564ce4a5312",
    "original_subdir": "h1-2025-ttm-batch3-20261125",
    "source_page": 11,
    "image_sha256": "c69bb4a8cac577b52ba718b6987b37dd51e7b35945d9dd68eb851b86a959df21",
    "image": "blind-input-pow-2025h1-p11/claude/page-11.png",
    "render_meta": "blind-input-pow-2025h1-p11/input.meta.json",
    "readings": [
        [
            "claude",
            "blind-input-pow-2025h1-p11/claude/claude-reader.raw.json",
            "2026-11-25T12:02:25+07:00"
        ],
        [
            "gemini",
            "blind-input-pow-2025h1-p11/gemini/gemini-reader.raw.json",
            "2026-11-25T12:05:26+07:00"
        ]
    ],
    "new_subdir": "h1-2025-dual-reader-pow-20261125",
    "printed_page": "7",
    "column_id": "c1",
    "comparison_started_at": "2026-11-25T12:06:00+07:00"
}

POW_2026_H1_P11 = {
    "page_key": "pow-2026h1-p11",
    "ticker": "POW",
    "reporting_period": "2026-H1",
    "document_sha256": "38f6bcd441d601fa94e2742ee7d6721c4f423110b656e90ba0f9e8ac2e123cd5",
    "document_id": "a9fffec5811e3522a692dcec0795f1d70ea0652e9373c819e7561955d646b6d4",
    "original_subdir": "gem1-04-acquisition-20261125",
    "source_page": 11,
    "image_sha256": "cd386354584d7747f9bb4b6098712b31a4274708ec6e6dd6d21255a34f8578ec",
    "image": "blind-input-pow-2026h1-p11/claude/page-11.png",
    "render_meta": "blind-input-pow-2026h1-p11/input.meta.json",
    "readings": [
        [
            "claude",
            "blind-input-pow-2026h1-p11/claude/claude-reader.raw.json",
            "2026-11-25T12:02:24+07:00"
        ],
        [
            "gemini",
            "blind-input-pow-2026h1-p11/gemini/gemini-reader.raw.json",
            "2026-11-25T12:05:16+07:00"
        ]
    ],
    "new_subdir": "h1-2026-dual-reader-pow-20261125",
    "printed_page": "7",
    "column_id": "c1",
    "comparison_started_at": "2026-11-25T12:06:00+07:00"
}

NVL_2025_H1_P12 = {
    "page_key": "nvl-2025h1-p12",
    "ticker": "NVL",
    "reporting_period": "2025-H1",
    "document_sha256": "618d514b355387ade90d2266f8f8c4c7098d94339592dc696d900482c96b4e6c",
    "document_id": "37c73f169b42344a61cdb529b79c9721f9d0d31d0dc29efd2be824afa3b8897c",
    "original_subdir": "h1-2025-ttm-batch3-20261125",
    "source_page": 12,
    "image_sha256": "375c77e36fad1ca1797f32777f88625dc535751e7b492aeb71af9cd59a77b49b",
    "image": "blind-input-nvl-2025h1-p12/claude/page-12.png",
    "render_meta": "blind-input-nvl-2025h1-p12/input.meta.json",
    "readings": [
        [
            "claude",
            "blind-input-nvl-2025h1-p12/claude/claude-reader.raw.json",
            "2026-11-25T12:02:28+07:00"
        ],
        [
            "gemini",
            "blind-input-nvl-2025h1-p12/gemini/gemini-reader.raw.json",
            "2026-11-25T12:05:36+07:00"
        ]
    ],
    "new_subdir": "h1-2025-dual-reader-nvl-20261125",
    "printed_page": "10",
    "column_id": "c1",
    "comparison_started_at": "2026-11-25T12:06:00+07:00"
}

NVL_2026_H1_P12 = {
    "page_key": "nvl-2026h1-p12",
    "ticker": "NVL",
    "reporting_period": "2026-H1",
    "document_sha256": "20aa7254735542d470f12ada8d02786dfa5e673035274e42d3404352e266a007",
    "document_id": "c7c7ca6cb25567d7a1307e15987cf0eeba7f44b7b11d682ce738a0d978606abd",
    "original_subdir": "nvl-reviewed-evidence-20261008",
    "source_page": 12,
    "image_sha256": "880dfa4354201b1135663b5bf1e5f27c58f79e0ed053982c12235d4caac18e9d",
    "image": "blind-input-nvl-2026h1-p12/claude/page-12.png",
    "render_meta": "blind-input-nvl-2026h1-p12/input.meta.json",
    "readings": [
        [
            "claude",
            "blind-input-nvl-2026h1-p12/claude/claude-reader.raw.json",
            "2026-11-25T12:02:30+07:00"
        ],
        [
            "gemini",
            "blind-input-nvl-2026h1-p12/gemini/gemini-reader.raw.json",
            "2026-11-25T12:05:46+07:00"
        ]
    ],
    "new_subdir": "h1-2026-dual-reader-nvl-20261125",
    "printed_page": "Trang 10",
    "column_id": "c1",
    "comparison_started_at": "2026-11-25T12:06:00+07:00"
}

NVL_2025_P12 = {
    "page_key": "nvl-fy2025-p12",
    "ticker": "NVL",
    "reporting_period": "2025",
    "document_sha256": "8a1cb94cbe9ef5d98550ef6ab734f54f99ecb9376f43c8aa4a3662cd6d5d0353",
    "document_id": "c040b3b610442453248c6c43423a17be20869e7c0560da3384677a74f79b9622",
    "original_subdir": "gem1-04-acquisition-20261125",
    "source_page": 12,
    "image_sha256": "d003a13f910ffab2bf14ef269f80fe3a12b2cf50ba01bdb1706e9b4b28526378",
    "image": "blind-input-nvl-fy2025-p12/claude/page-12.png",
    "render_meta": "blind-input-nvl-fy2025-p12/input.meta.json",
    "readings": [
        [
            "claude",
            "blind-input-nvl-fy2025-p12/claude/claude-reader.raw.json",
            "2026-11-25T08:11:58+07:00"
        ],
        [
            "gemini",
            "blind-input-nvl-fy2025-p12/gemini/gemini-reader.raw.json",
            "2026-11-25T08:15:12+07:00"
        ]
    ],
    "new_subdir": "fy2025-dual-reader-nvl-20261125",
    "printed_page": "Trang 10",
    "column_id": "c1",
    "comparison_started_at": "2026-11-25T08:15:17+07:00"
}

SPECS = {"HPG-2025-H1-P10": HPG_2025_H1_P10, "PNJ-2025-P10": PNJ_2025_P10,
         "PNJ-2025-H1-P10": PNJ_2025_H1_P10, "VRE-2025-P11": VRE_2025_P11,
         "POW-2025-P11": POW_2025_P11,
         "POW-2025-H1-P11": POW_2025_H1_P11,
         "POW-2026-H1-P11": POW_2026_H1_P11,
         "NVL-2025-H1-P12": NVL_2025_H1_P12,
         "NVL-2026-H1-P12": NVL_2026_H1_P12,
         "NVL-2025-P12": NVL_2025_P12}


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8") + b"\n"


def _write_once(path: Path, payload: bytes) -> str:
    """Create a file once; an existing file must already hold identical bytes."""
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"RETAINED_FILE_DIFFERS_REFUSING_OVERWRITE:{path}")
        return "REUSED_IDENTICAL"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if path.read_bytes() != payload:
        raise ValueError(f"RETAINED_WRITE_NOT_BYTE_IDENTICAL:{path}")
    return "CREATED"


def _copy_verified(source: Path, target: Path, sha256: str) -> str:
    payload = source.read_bytes()
    if _sha(payload) != sha256:
        raise ValueError(f"SOURCE_HASH_MISMATCH:{source}")
    status = _write_once(target, payload)
    if _sha(target.read_bytes()) != sha256:
        raise ValueError(f"COPY_HASH_MISMATCH:{target}")
    return status


def _read_render_meta(payload: bytes) -> tuple[dict, str]:
    """Read-only. A meta file with unescaped Windows backslashes is parsed from an
    in-memory escaped copy; the retained bytes are copied unchanged."""
    text = payload.decode("utf-8")
    try:
        return json.loads(text), "STRICT_JSON"
    except ValueError:
        return json.loads(text.replace("\\", "\\\\")), "READ_ONLY_BACKSLASH_ESCAPED_PARSE"


def _stable(prefix: str, value: Any) -> str:
    return _sha((prefix + json.dumps(value, ensure_ascii=False, sort_keys=True)).encode("utf-8"))


def _selected_cell(table, column_id, code):
    columns = [c for c in table["columns"] if c["column_id"] == column_id]
    if len(columns) != 1:
        raise ValueError(f"COLUMN_NOT_UNIQUE:{code}")
    matches = [r for r in table["rows"] if r["line_code_literal"] == code]
    if len(matches) != 1:
        raise ValueError(f"ROW_NOT_UNIQUE:{code}")
    cells = [c for c in matches[0]["cells"] if c["column_id"] == column_id]
    if len(cells) != 1:
        raise ValueError(f"CELL_NOT_UNIQUE:{code}")
    return columns[0], matches[0], cells[0]


def build_rows(*, spec: Mapping[str, Any], document_evidence: Mapping[str, Any], raw_table: Mapping[str, Any],
               proof_ref: Mapping[str, str], knowledge_available_at: str, subdir: str, rejections: list[dict[str, Any]],
               other_tables: tuple[Mapping[str, Any], ...] = ()) -> list[dict[str, Any]]:
    """Current-column rows from one reader's literal cells; admission replays both readers.

    No digit, sign or label is altered. The literal outline enumerator, if printed
    in the numbering column, is kept out of the row label exactly as the verifier
    splits it. Values are parsed by the existing accounting-integer owner.
    """
    from official_financial_value_evidence import parse_accounting_integer
    from official_financial_period_identity import period_bounds
    # Currency/scale come from the qualified document metadata; the verifier then
    # requires both readers' unit literal to declare exactly this unit.
    claims = document_evidence["document_metadata"]["metadata_claims"]
    unit = {"currency": claims["currency"]["value"], "unit_scale": claims["unit_scale"]["value"]}
    if unit["currency"] != "VND" or type(unit["unit_scale"]) is not int or unit["unit_scale"] <= 0:
        raise ValueError("DOCUMENT_UNIT_NOT_QUALIFIED_VND")
    start, end = period_bounds(spec["reporting_period"])
    annual = str(spec["reporting_period"]).isdigit()
    rows = []
    for metric, code in METRICS:
        try:
            for table in (raw_table, *other_tables):
                column, literal_row, cell = _selected_cell(table, spec["column_id"], code)
                if cell["sign_literal"] != "unsigned":
                    raise ValueError(f"SIGNED_CELL_NOT_SUPPORTED_BY_THIS_RUN:{code}")
                try:
                    parse_accounting_integer(cell["raw_value_literal"])
                except (ValueError, TypeError, AttributeError):
                    raise ValueError(f"VALUE_NOT_PARSEABLE:{code}") from None
            column, literal_row, cell = _selected_cell(raw_table, spec["column_id"], code)
            _, label = dual.split_outline_enumerator(literal_row["row_label_literal"])
            literal = cell["raw_value_literal"]
            value = parse_accounting_integer(literal) * unit["unit_scale"]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else f"CELL_LITERAL_MISSING_OR_INVALID:{code}"
            rejections.append({"canonical_metric": metric, "line_code": code,
                               "state": "BLOCKED", "reason_codes": [reason]})
            continue
        identity = {"document_sha256": spec["document_sha256"], "source_page": spec["source_page"],
                    "line_code": code, "column_id": spec["column_id"], "proof_sha256": proof_ref["proof_sha256"]}
        citation = _stable("dual_reader_citation/v1:", identity)
        rows.append({
            "ticker": spec["ticker"], "canonical_metric": metric, "line_code": code,
            "reporting_period": spec["reporting_period"], "period_type": "annual" if annual else "interim",
            "period_start": start, "period_end": end, "statement_scope": "consolidated",
            "statement_family": "income_statement", "temporal_nature": "duration",
            "currency": "VND", "unit_scale": 1, "source_unit_scale": unit["unit_scale"],
            "normalized_value": value, "value": value, "already_normalized": True,
            "qualification_state": "QUALIFIED", "blockers": [],
            "document_sha256": spec["document_sha256"], "citation_id": citation,
            "fact_id": _stable("dual_reader_fact/v1:", {**identity, "canonical_metric": metric}),
            "source_page": spec["source_page"], "audit_or_review_status": document_evidence["audit_or_review_status"],
            "raw_value_text": literal, "raw_row_label": label,
            "source_span": {"text": label + " " + literal, "document_sha256": spec["document_sha256"],
                            "source_page": spec["source_page"], "citation_id": citation},
            "evidence_subdir": subdir, "observed_at": document_evidence["observed_at"],
            "knowledge_available_at": knowledge_available_at, "publication_date": None,
            "source_family": document_evidence["source_family"], "restatement": None,
            "document_metadata": document_evidence["document_metadata"],
            "assurance_evidence": document_evidence["assurance_evidence"],
            # Reused under the OCR layout contract for document-level page text only.
            "ocr_layout_proof": document_evidence["ocr_layout_proof"],
            "extraction_method": "dual_reader_reviewed_transcription",
            "dual_reader_transcription": dict(proof_ref),
            "issuer_literal": raw_table["issuer_literal"],
            "form_reference_literal": raw_table["form_reference_literal"],
            "statement_title_literal": raw_table["statement_title_literal"],
            "current_period_label": column["label_literal"], "column_id": spec["column_id"],
            "evidence_tier": dual.EVIDENCE_TIER, "authority_effect": "OFFLINE_RESEARCH_ONLY",
            "pit_backtest_eligible": False,
        })
    return rows


def _validate_readings(*, spec, reader_root, observed_at, completed):
    """Document-wide provenance fails before any output; cell disagreements stay local."""
    comparison, completion = dual._time(spec["comparison_started_at"]), dual._time(completed)
    if completion < comparison or len(spec["readings"]) != 2:
        raise ValueError("READER_TIME_OR_COUNT_INVALID")
    families, ids, hashes = [], [], []
    expected = {key: spec[key] for key in ("document_sha256", "document_id", "source_page", "printed_page")}
    expected["image_sha256"] = spec["image_sha256"]
    payloads = []
    for family, relative, retained_at in spec["readings"]:
        payload = (reader_root / relative).read_bytes()
        raw = dual._json(payload)
        actual_family = dual.FAMILY_ALIASES.get(str(raw.get("model_family")).lower())
        if not actual_family or actual_family != family or raw.get("contract_version") != dual.RAW_VERSION:
            raise ValueError("READER_CONTRACT_OR_FAMILY_MISMATCH")
        if (raw.get("method") != "DIRECT_PAGE_IMAGE" or raw.get("independent_input") is not True
                or raw.get("saw_other_reader_output") is not False or not raw.get("reader_id")):
            raise ValueError("READER_INDEPENDENCE_NOT_PROVEN")
        if raw.get("input") != expected:
            raise ValueError("READER_INPUT_BINDING_MISMATCH")
        if not (dual._time(observed_at) <= dual._time(raw["recorded_at"])
                <= dual._time(retained_at) < comparison <= completion):
            raise ValueError("RAW_NOT_RETAINED_BEFORE_COMPARISON")
        families.append(actual_family); ids.append(raw["reader_id"]); hashes.append(_sha(payload))
        payloads.append(payload)
    if len(set(families)) != 2 or len(set(ids)) != 2 or len(set(hashes)) != 2:
        raise ValueError("DIFFERENT_MODEL_FAMILIES_AND_RECORDS_REQUIRED")
    return payloads


def run(*, landing_root: Path, reader_root: Path, document_evidence_path: Path, ocr_layout_proof_path: Path,
        admission_completed_at: str | None = None, spec: Mapping[str, Any] = HPG_2025_H1_P10) -> dict[str, Any]:
    import official_financial_ocr_table_evidence  # noqa: F401 - registers native PDF artifact builder
    from stocklookup_core.evidence.official_document_qualification import admit_retained_financial_fact
    from stocklookup_core.evidence.official_ocr_layout_proof import PROOF_DIR as OCR_DIR, verify_proof_identity
    from stocklookup_core.evidence.financial_row_identity import _identity_fold

    landing_root = Path(landing_root).resolve()
    original = landing_root / spec["original_subdir"]
    target = landing_root / spec["new_subdir"]
    if target.resolve() == original.resolve() or not target.resolve().is_relative_to(landing_root):
        raise ValueError("NEW_SUBDIR_REQUIRED")
    files: dict[str, str] = {}

    # 1. Source record and PDF bytes (original manifest is read, never written).
    records = json.loads((original / MANIFEST).read_text(encoding="utf-8"))["records"]
    matches = [r for r in records if r.get("sha256") == spec["document_sha256"]]
    if len(matches) != 1 or matches[0].get("document_id") != spec["document_id"]:
        raise ValueError("ORIGINAL_SOURCE_RECORD_NOT_UNIQUE")
    source = dict(matches[0])
    if (source.get("acquisition_status") != "retained" or source.get("ticker") != spec["ticker"]
            or source.get("reporting_period") != spec["reporting_period"]):
        raise ValueError("ORIGINAL_SOURCE_RECORD_IDENTITY_MISMATCH")
    base = f"{dual.PROOF_DIR}/{spec['page_key']}"
    proof_path = target / base / "agreement.proof.json"
    completed = (json.loads(proof_path.read_text(encoding="utf-8"))["admission_completed_at"]
                 if proof_path.exists() else admission_completed_at
                 or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    payloads = _validate_readings(spec=spec, reader_root=reader_root,
                                  observed_at=source["observed_at"], completed=completed)
    files[source["relative_path"]] = _copy_verified(original / source["relative_path"],
                                                    target / source["relative_path"], spec["document_sha256"])

    # 2. Raw readings + page image, byte-identical, under the governed proof root.
    base = f"{dual.PROOF_DIR}/{spec['page_key']}"
    image_rel = f"{base}/page-{spec['source_page']}.png"
    files[image_rel] = _copy_verified(reader_root / spec["image"], target / image_rel, spec["image_sha256"])
    render_meta = reader_root / spec["render_meta"]
    meta_rel = f"{base}/page-{spec['source_page']}.render-meta.json"
    files[meta_rel] = _copy_verified(render_meta, target / meta_rel, _sha(render_meta.read_bytes()))
    meta, meta_parse = _read_render_meta(render_meta.read_bytes())
    if (meta.get("source_sha256") != spec["document_sha256"] or meta.get("image_sha256") != spec["image_sha256"]
            or meta.get("source_page") != spec["source_page"]
            or meta.get("document_id", spec["document_id"]) != spec["document_id"]
            # Rights are carried by the manifest record; a render meta that states a route must agree.
            or meta.get("rights_route", dual.RIGHTS_ROUTE) != dual.RIGHTS_ROUTE):
        raise ValueError("RENDER_PROVENANCE_MISMATCH")
    readings, tables = [], []
    for (family, relative, retained_at), payload in zip(spec["readings"], payloads):
        name = f"{base}/{Path(relative).name}"
        files[name] = _copy_verified(reader_root / relative, target / name, _sha(payload))
        raw = json.loads(payload.decode("utf-8"))
        if dual.FAMILY_ALIASES.get(str(raw.get("model_family")).lower()) != family:
            raise ValueError("READER_FAMILY_MISMATCH")
        readings.append({"relative_path": name, "sha256": _sha(payload), "retained_at": retained_at})
        tables.append(raw["table"])

    # 3. Manifest record: original fields plus explicit rights, issuer name and image binding.
    issuer = tables[0]["issuer_literal"]
    if (any(t["issuer_literal"] != issuer for t in tables)
            or _identity_fold(issuer) != REGISTERED_ISSUER_FOLD.get(spec["ticker"])):
        raise ValueError("ISSUER_LITERAL_NOT_REGISTERED_LEGAL_NAME")
    image = {"relative_path": image_rel, "sha256": spec["image_sha256"],
             "source_page": spec["source_page"], "printed_page": spec["printed_page"]}
    record = {**source, "rights_route": dual.RIGHTS_ROUTE, "acquisition_route": INDEPENDENT_ROUTE,
              "rights_status": RIGHTS_STATUS, "issuer_name": issuer, "page_image_bindings": [image],
              "retained_copy_of": {"evidence_subdir": spec["original_subdir"], "manifest": MANIFEST,
                                   "record_sha256": _sha(_canonical(matches[0]))},
              "page_image_render": {"render_meta_relative_path": meta_rel, "rendered_at": meta.get("rendered_at"),
                                    **({} if meta_parse == "STRICT_JSON" else {"render_meta_parse": meta_parse})}}
    files[MANIFEST] = _write_once(target / MANIFEST, _canonical({"schema_version": "1.2.0", "records": [record]}))

    # 4. OCR layout proof reused only for document-level page text, hash identity verified.
    evidence = json.loads(Path(document_evidence_path).read_text(encoding="utf-8"))
    ocr_ref = evidence["ocr_layout_proof"]
    ocr_bytes = Path(ocr_layout_proof_path).read_bytes()
    if verify_proof_identity(json.loads(ocr_bytes.decode("utf-8")), document_sha256=spec["document_sha256"],
                             proof_sha256=ocr_ref["proof_sha256"]):
        raise ValueError("OCR_LAYOUT_PROOF_IDENTITY_MISMATCH")
    if not ocr_ref["relative_path"].startswith(OCR_DIR + "/"):
        raise ValueError("OCR_LAYOUT_PROOF_PATH_INVALID")
    files[ocr_ref["relative_path"]] = _copy_verified(Path(ocr_layout_proof_path), target / ocr_ref["relative_path"],
                                                     _sha(ocr_bytes))
    evidence_rel = "document_level_evidence.json"
    files[evidence_rel] = _write_once(target / evidence_rel, Path(document_evidence_path).read_bytes())
    if (evidence["document_sha256"] != spec["document_sha256"] or evidence["ticker"] != spec["ticker"]
            or evidence["reporting_period"] != spec["reporting_period"]):
        raise ValueError("DOCUMENT_EVIDENCE_IDENTITY_MISMATCH")

    # 5. Seal the proof once. An existing proof keeps its original completion instant.
    proof_rel = f"{base}/agreement.proof.json"
    proof_path = target / proof_rel
    if proof_path.exists():
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        completed = proof["admission_completed_at"]
    else:
        proof = {"contract_version": dual.CONTRACT_VERSION, "document_sha256": spec["document_sha256"],
                 "document_id": spec["document_id"], "page_image": image, "readings": readings,
                 "comparison_started_at": spec["comparison_started_at"], "admission_completed_at": completed}
    proof_bytes = _canonical(proof)
    files[proof_rel] = _write_once(proof_path, proof_bytes)
    if proof["readings"] != readings or proof["page_image"] != image:
        raise ValueError("SEALED_PROOF_BINDING_CHANGED")
    proof_ref = {"relative_path": proof_rel, "proof_sha256": _sha(proof_bytes)}

    # 6. Rows from the agreed literal cells, then the common retained admission owner.
    fact_local_rejections = []
    rows = build_rows(spec=spec, document_evidence=evidence, raw_table=tables[0], proof_ref=proof_ref,
                      knowledge_available_at=completed, subdir=spec["new_subdir"],
                      rejections=fact_local_rejections, other_tables=tuple(tables[1:]))
    admissions = []
    for row in rows:
        result = admit_retained_financial_fact(row, evidence_root=landing_root)
        admissions.append({"canonical_metric": row["canonical_metric"], "line_code": row["line_code"],
                           "normalized_value": row["normalized_value"], "fact_id": row["fact_id"],
                           "citation_id": row["citation_id"], "state": result["state"],
                           "reason_codes": result["reason_codes"], "admission_basis": result.get("admission_basis"),
                           "evidence_tier": result.get("evidence_tier"),
                           "evidence_classification": result.get("evidence_classification"),
                           "admission_id": result.get("admission_id")})
    rows_rel = "dual_reader_admitted_rows.jsonl"
    admitted = [row for row, item in zip(rows, admissions) if item["state"] == "ADMITTED"]
    rows_payload = b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                            for row in admitted)
    files[rows_rel] = _write_once(target / rows_rel, rows_payload) if admitted else "NOT_WRITTEN"
    return {"tool_version": TOOL_VERSION, "landing_root": str(landing_root), "evidence_subdir": spec["new_subdir"],
            "ticker": spec["ticker"], "reporting_period": spec["reporting_period"],
            "document_sha256": spec["document_sha256"], "proof": proof_ref,
            "raw_sha256": [r["sha256"] for r in readings], "comparison_started_at": spec["comparison_started_at"],
            "admission_completed_at": completed, "knowledge_floor": completed, "files": files,
            "admissions": admissions, "fact_local_rejections": fact_local_rejections, "rows_relative_path": rows_rel if admitted else None,
            "authority_effect": "OFFLINE_RESEARCH_ONLY", "pit_backtest_eligible": False,
            "network_used": False, "model_calls": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--reader-root", type=Path, required=True)
    parser.add_argument("--document-evidence", type=Path, required=True)
    parser.add_argument("--ocr-layout-proof", type=Path, required=True)
    parser.add_argument("--admission-completed-at")
    parser.add_argument("--spec", choices=sorted(SPECS), default="HPG-2025-H1-P10")
    args = parser.parse_args(argv)
    report = run(landing_root=args.landing_root, reader_root=args.reader_root,
                 document_evidence_path=args.document_evidence, ocr_layout_proof_path=args.ocr_layout_proof,
                 admission_completed_at=args.admission_completed_at, spec=SPECS[args.spec])
    print(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if (not report["fact_local_rejections"] and report["admissions"]
                 and all(item["state"] == "ADMITTED" for item in report["admissions"])) else 2


if __name__ == "__main__":
    raise SystemExit(main())
