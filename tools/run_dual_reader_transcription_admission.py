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
REGISTERED_ISSUER_FOLD = {"HPG": "cong ty co phan tap doan hoa phat"}

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


def _stable(prefix: str, value: Any) -> str:
    return _sha((prefix + json.dumps(value, ensure_ascii=False, sort_keys=True)).encode("utf-8"))


def build_rows(*, spec: Mapping[str, Any], document_evidence: Mapping[str, Any], raw_table: Mapping[str, Any],
               proof_ref: Mapping[str, str], knowledge_available_at: str, subdir: str) -> list[dict[str, Any]]:
    """Current-column rows from one reader's literal cells; admission replays both readers.

    No digit, sign or label is altered. The literal outline enumerator, if printed
    in the numbering column, is kept out of the row label exactly as the verifier
    splits it. Values are parsed by the existing accounting-integer owner.
    """
    from official_financial_value_evidence import parse_accounting_integer
    from financial_statement_unit_resolution import parse_explicit_unit_declaration
    from official_financial_period_identity import period_bounds
    unit = parse_explicit_unit_declaration(raw_table["currency_unit_literal"])
    if not unit or unit.get("currency") != "VND":
        raise ValueError("UNIT_NOT_EXPLICIT_VND")
    column = next(c for c in raw_table["columns"] if c["column_id"] == spec["column_id"])
    start, end = period_bounds(spec["reporting_period"])
    rows = []
    for metric, code in METRICS:
        matches = [r for r in raw_table["rows"] if r["line_code_literal"] == code]
        if len(matches) != 1:
            raise ValueError(f"ROW_NOT_UNIQUE:{code}")
        cell = next(c for c in matches[0]["cells"] if c["column_id"] == spec["column_id"])
        _, label = dual.split_outline_enumerator(matches[0]["row_label_literal"])
        literal = cell["raw_value_literal"]
        if cell["sign_literal"] != "unsigned":
            raise ValueError(f"SIGNED_CELL_NOT_SUPPORTED_BY_THIS_RUN:{code}")
        value = parse_accounting_integer(literal) * unit["unit_scale"]
        identity = {"document_sha256": spec["document_sha256"], "source_page": spec["source_page"],
                    "line_code": code, "column_id": spec["column_id"], "proof_sha256": proof_ref["proof_sha256"]}
        citation = _stable("dual_reader_citation/v1:", identity)
        rows.append({
            "ticker": spec["ticker"], "canonical_metric": metric, "line_code": code,
            "reporting_period": spec["reporting_period"], "period_type": "interim",
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


def run(*, landing_root: Path, reader_root: Path, document_evidence_path: Path, ocr_layout_proof_path: Path,
        admission_completed_at: str | None = None, spec: Mapping[str, Any] = HPG_2025_H1_P10) -> dict[str, Any]:
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
    files[source["relative_path"]] = _copy_verified(original / source["relative_path"],
                                                    target / source["relative_path"], spec["document_sha256"])

    # 2. Raw readings + page image, byte-identical, under the governed proof root.
    base = f"{dual.PROOF_DIR}/{spec['page_key']}"
    image_rel = f"{base}/page-{spec['source_page']}.png"
    files[image_rel] = _copy_verified(reader_root / spec["image"], target / image_rel, spec["image_sha256"])
    render_meta = reader_root / spec["render_meta"]
    meta_rel = f"{base}/page-{spec['source_page']}.render-meta.json"
    files[meta_rel] = _copy_verified(render_meta, target / meta_rel, _sha(render_meta.read_bytes()))
    meta = json.loads(render_meta.read_text(encoding="utf-8"))
    if (meta.get("source_sha256") != spec["document_sha256"] or meta.get("image_sha256") != spec["image_sha256"]
            or meta.get("source_page") != spec["source_page"] or meta.get("rights_route") != dual.RIGHTS_ROUTE):
        raise ValueError("RENDER_PROVENANCE_MISMATCH")
    readings, tables = [], []
    for family, relative, retained_at in spec["readings"]:
        payload = (reader_root / relative).read_bytes()
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
              "page_image_render": {"render_meta_relative_path": meta_rel, "rendered_at": meta.get("rendered_at")}}
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
        completed = admission_completed_at or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        proof = {"contract_version": dual.CONTRACT_VERSION, "document_sha256": spec["document_sha256"],
                 "document_id": spec["document_id"], "page_image": image, "readings": readings,
                 "comparison_started_at": spec["comparison_started_at"], "admission_completed_at": completed}
    proof_bytes = _canonical(proof)
    files[proof_rel] = _write_once(proof_path, proof_bytes)
    if proof["readings"] != readings or proof["page_image"] != image:
        raise ValueError("SEALED_PROOF_BINDING_CHANGED")
    proof_ref = {"relative_path": proof_rel, "proof_sha256": _sha(proof_bytes)}

    # 6. Rows from the agreed literal cells, then the common retained admission owner.
    rows = build_rows(spec=spec, document_evidence=evidence, raw_table=tables[0], proof_ref=proof_ref,
                      knowledge_available_at=completed, subdir=spec["new_subdir"])
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
            "admissions": admissions, "rows_relative_path": rows_rel if admitted else None,
            "authority_effect": "OFFLINE_RESEARCH_ONLY", "pit_backtest_eligible": False,
            "network_used": False, "model_calls": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--reader-root", type=Path, required=True)
    parser.add_argument("--document-evidence", type=Path, required=True)
    parser.add_argument("--ocr-layout-proof", type=Path, required=True)
    parser.add_argument("--admission-completed-at")
    args = parser.parse_args(argv)
    report = run(landing_root=args.landing_root, reader_root=args.reader_root,
                 document_evidence_path=args.document_evidence, ocr_layout_proof_path=args.ocr_layout_proof,
                 admission_completed_at=args.admission_completed_at)
    print(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if all(item["state"] == "ADMITTED" for item in report["admissions"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
