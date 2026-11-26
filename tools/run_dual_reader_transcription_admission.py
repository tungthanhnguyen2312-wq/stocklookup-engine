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
from stocklookup_core.evidence.official_ocr_layout_proof import (  # noqa: E402
    load_registry_snapshot, REGISTERED_ISSUER_FOLD,
)


def load_admission_specs(*, root: Path = ROOT, relative: str = "config/dual_reader_admissions/r0001.json"):
    snapshot = load_registry_snapshot("admissions", root=root, relative=relative)
    result = {}
    for key, entry in snapshot["entries"].items():
        payload = entry["payload"]
        if entry["inputs"]["tuple_readings"]:
            payload["readings"] = tuple(tuple(item) for item in payload["readings"])
        result[key] = payload
    return result


SPECS = load_admission_specs()
HPG_2025_H1_P10 = SPECS['HPG-2025-H1-P10']
PNJ_2025_P10 = SPECS['PNJ-2025-P10']
PNJ_2025_H1_P10 = SPECS['PNJ-2025-H1-P10']
VRE_2025_P11 = SPECS['VRE-2025-P11']
POW_2025_P11 = SPECS['POW-2025-P11']
POW_2025_H1_P11 = SPECS['POW-2025-H1-P11']
POW_2026_H1_P11 = SPECS['POW-2026-H1-P11']
NVL_2025_H1_P12 = SPECS['NVL-2025-H1-P12']
NVL_2026_H1_P12 = SPECS['NVL-2026-H1-P12']
NVL_2025_P12 = SPECS['NVL-2025-P12']
HAH_2025_P13 = SPECS['HAH-2025-P13']
HAH_2025_H1_P12 = SPECS['HAH-2025-H1-P12']
HAH_2026_H1_P13 = SPECS['HAH-2026-H1-P13']
BWE_2025_P12 = SPECS['BWE-2025-P12']
BWE_2025_H1_P12 = SPECS['BWE-2025-H1-P12']
BWE_2026_H1_P12 = SPECS['BWE-2026-H1-P12']


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
    # Decision 2 condition 3: use the two readers' identical statement-page unit
    # when both tables are supplied. Metadata and the full retained proof remain
    # independent admission gates; this does not repair an OCR metadata envelope.
    if other_tables:
        from financial_statement_unit_resolution import parse_explicit_unit_declaration
        unit = dual.agreed_vnd_unit((raw_table, *other_tables), parse_explicit_unit_declaration)
        if unit is None:
            raise ValueError("READERS_UNIT_LITERAL_NOT_IDENTICAL_EXPLICIT_VND")
    else:
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
                # A printed loss "(digits)" is supported only for profit lines 60/61; revenue and
                # any other sign vocabulary stay refused.
                if cell["sign_literal"] != "unsigned" and not (
                        cell["sign_literal"] == "parentheses" and code in {"60", "61"}):
                    raise ValueError(f"SIGNED_CELL_NOT_SUPPORTED_BY_THIS_RUN:{code}")
                signed = dual.signed_cell_literal(cell["raw_value_literal"], cell["sign_literal"])
                try:
                    if signed is None:
                        raise ValueError
                    parse_accounting_integer(signed)
                except (ValueError, TypeError, AttributeError):
                    raise ValueError(f"VALUE_NOT_PARSEABLE:{code}") from None
            column, literal_row, cell = _selected_cell(raw_table, spec["column_id"], code)
            _, label = dual.split_outline_enumerator(literal_row["row_label_literal"])
            literal = dual.signed_cell_literal(cell["raw_value_literal"], cell["sign_literal"])
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
            "form_reference_literal": dual.form_code_literal(raw_table["form_reference_literal"]),
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
        if not dual.input_binding_matches(raw.get("input"), expected):
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
    from stocklookup_core.evidence.official_ocr_layout_proof import exact_registered_issuer_name
    if (any(t["issuer_literal"] != issuer for t in tables)
            or not (exact_registered_issuer_name(spec["ticker"], issuer)
                    or _identity_fold(issuer) == REGISTERED_ISSUER_FOLD.get(spec["ticker"]))):
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


def replay_ttm(config_path: Path, decision_session: str, tickers, *, evidence_root: Path | None = None,
               raw_valuation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read-only replay; no admission files, runtime artifacts or sealed sessions are written."""
    root = Path(config_path).resolve().parents[1]
    if Path(config_path).resolve() != root / dual.DUAL_READER_TTM_CONFIG_REL:
        raise ValueError("CONFIG_PATH_INVALID")
    try:
        config = dual.load_dual_reader_ttm_research_config(root)
    except dual.DualReaderTtmConfigCorruptError as exc:
        return {"state": "CORRUPT_BLOCKED", "reason": str(exc), "records": {}, "network_used": False}
    tickers = sorted(set(tickers or [e["ticker"] for e in config["evidence_subdirs"] if e["enabled"]]))
    if config["enabled"] is False:
        return {"state": "OFF", "records": {}, "network_used": False}
    if config["enabled"]:
        registered = {(s["ticker"], s["reporting_period"], s["document_sha256"], s["new_subdir"]) for s in SPECS.values()}
        for entry in config["evidence_subdirs"]:
            if entry["enabled"] and (entry["ticker"], entry["reporting_period"], entry["document_sha256"], entry["subdir"]) not in registered:
                return {"state": "INTEGRITY_BLOCKED", "reason": "ADMISSION_SPEC_IDENTITY_MISMATCH", "records": {}, "network_used": False}
        # Snapshot and A2 selector vintages are independent approval inputs.
        snapshot = load_registry_snapshot("admissions", root=ROOT, relative="config/dual_reader_admissions/r0001.json")
        cutoff = dual.research_timestamp(f"{decision_session}T15:00:00+07:00")
        receipt = json.loads((root / "config/owner_daily_capacity_qualification.json").read_bytes())
        approvals = [snapshot["review"]["recorded_at"], *[
            s["approved_at"] for s in receipt.get("financial_registry_inputs", {}).values()]]
        for role, selector in receipt.get("financial_registry_inputs", {}).items():
            selected = load_registry_snapshot(role, root=ROOT, relative=selector["path"])
            approvals.append(selected["review"]["recorded_at"])
        if any(dual.research_timestamp(stamp) > cutoff for stamp in approvals):
            return {"state": "PRE_APPROVAL_CUTOFF", "reason": "REGISTRY_APPROVAL_AFTER_KNOWLEDGE_CUTOFF", "records": {}, "network_used": False}
    from canonical_daily_financial_v2_materialization import _load_dual_reader_ttm_research_overlay
    from stocklookup_core.valuation import current_research_valuation_context as valuation
    from ai_research_session_delivery import _valuation_methods_for_delivery
    overlay = _load_dual_reader_ttm_research_overlay(repo_root=root, decision_session=decision_session,
        product_tickers=tickers, official_financial_facts=[], evidence_root=evidence_root, config=config)
    if overlay["state"] == "OFF":
        return {"state": "OFF", "records": {}, "network_used": False}
    records = {}
    for ticker in tickers:
        records[ticker] = valuation.evaluate_ticker_valuation(ticker=ticker, feature_record=None,
            valuation_record=((raw_valuation or {}).get("records") or {}).get(ticker),
            financial_analysis_record={"features": overlay["features_by_ticker"].get(ticker, {})},
            decision_session=decision_session, official_financial_facts=[], official_equity_facts=[],
            dual_reader_research_state=overlay)
    records = valuation.attach_peer_relative(records)
    for record in records.values():
        record["ai_export"] = _valuation_methods_for_delivery({"valuation_methods": record["methods"]},
                                                            source_session=decision_session)
    return {"state": overlay["state"], **({"reason": overlay["reason"]} if "reason" in overlay else {}),
        "decision_session": decision_session, "records": records, "network_used": False,
        "authority_effect": "OFFLINE_RESEARCH_ONLY", "pit_backtest_eligible": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path)
    parser.add_argument("--reader-root", type=Path)
    parser.add_argument("--document-evidence", type=Path)
    parser.add_argument("--ocr-layout-proof", type=Path)
    parser.add_argument("--replay-ttm", action="store_true")
    parser.add_argument("--config", type=Path, default=ROOT / dual.DUAL_READER_TTM_CONFIG_REL)
    parser.add_argument("--decision-session")
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--raw-valuation", type=Path)
    parser.add_argument("--admission-completed-at")
    parser.add_argument("--spec", choices=sorted(SPECS), default="HPG-2025-H1-P10")
    args = parser.parse_args(argv)
    if args.replay_ttm:
        if not args.decision_session:
            parser.error("--replay-ttm requires --decision-session")
        # Do not let the legacy admission default become a replay fallback.
        report = replay_ttm(args.config, args.decision_session, args.tickers, evidence_root=args.landing_root,
            raw_valuation=json.loads(args.raw_valuation.read_bytes()) if args.raw_valuation else None)
        print(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True))
        return 0 if report["state"] in {"OFF", "ON"} else 2
    if any(value is None for value in (args.reader_root, args.document_evidence, args.ocr_layout_proof)):
        parser.error("admission requires --reader-root, --document-evidence and --ocr-layout-proof")
    report = run(landing_root=args.landing_root or Path(DEFAULT_LANDING_ROOT), reader_root=args.reader_root,
                 document_evidence_path=args.document_evidence, ocr_layout_proof_path=args.ocr_layout_proof,
                 admission_completed_at=args.admission_completed_at, spec=SPECS[args.spec])
    print(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if (not report["fact_local_rejections"] and report["admissions"]
                 and all(item["state"] == "ADMITTED" for item in report["admissions"])) else 2


if __name__ == "__main__":
    raise SystemExit(main())
