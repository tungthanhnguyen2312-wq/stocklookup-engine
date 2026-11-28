"""Read-only EVF/SSI cold-reader replay. Prints deterministic per-cell JSON.

No acquisition, schema migration, sealing, admission writes or model calls.
Optional rows-file/evidence-root must name EXISTING common-owner proof inputs.
Absent proofs are reported, never synthesized from postcomparison research.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stocklookup_core.evidence import dual_reader_transcription as dual
from stocklookup_core.evidence.dual_reader_form_contract import FORM_ROWS, EVF_CANDIDATE_ROWS

PACKAGES = ("EVF_material_credit_funding", "SSI_earnings_basis")
PAGE_KEYS = frozenset({"EVF_2025", "EVF_2025H1", "EVF_2026H1",
                       "SSI_2025", "SSI_2025H1", "SSI_2026H1"})
MISSING_PROOFS = (
    "Decision 2 agreement proof binding PDF/document ID, page image and both exact raw hashes",
    "Actual timezone-aware recording and retention instants preceding comparison; Gemini recorded_at is null",
    "Supported raw family literals and explicit current-column schema, without rewriting sealed originals",
    "Manifest-selected source record with all three rights fields, issuer name and page-image bindings",
    "Common-owner qualified document metadata, legal issuer/scope and audited/reviewed assurance proofs",
    "For SSI 201: same-PDF note image, two timed independent note readings, identical printed disclosure and numerator",
    "For EVF: printed form and scope identity (both retained as null), plus document ID; no inferred TCTD literal",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bound(root, relative, expected=None):
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("REPLAY_PATH_ESCAPE")
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError("REPLAY_SEALED_HASH_MISMATCH:" + relative)
    return raw


def selected_cells(raw):
    table = raw["table"]
    columns = defaultdict(list)
    for column in table["columns"]:
        columns[column["column_id"]].append(column)
    result = defaultdict(list)
    for row in table["rows"]:
        label = dual.split_outline_enumerator(row["row_label_literal"])[1]
        for cell in row["cells"]:
            for column in columns[cell["column_id"]]:
                result[(row["line_code_literal"], label, column["label_literal"])].append((column, cell))
    return result


def replay(sealed_root, neutral_root, *, rows_file=None, evidence_root=None):
    index_bytes = read_bound(sealed_root, "SEALED_READER_INDEX.json")
    index = json.loads(index_bytes)
    pages, observations = {}, defaultdict(dict)
    for package in PACKAGES:
        manifest = json.loads(read_bound(neutral_root, f"packages/{package}/input_manifest.json"))
        for page in manifest["pages"]:
            if page["key"] in PAGE_KEYS and page["source_page"] in {11, 17}:
                pages[page["image_sha256"]] = page
    for entry in index["readers"]:
        if entry["package_id"] not in PACKAGES or entry["family"] not in {"claude", "gemini"}:
            continue
        seal_bytes = read_bound(sealed_root, entry["seal_path"], entry["seal_sha256"])
        seal = json.loads(seal_bytes)
        package_root = sealed_root / Path(entry["seal_path"]).parent
        for relative, pin in sorted(seal["output_files"].items()):
            if not relative.startswith("output/page_") or not relative.endswith(".json"):
                continue
            payload = read_bound(package_root, relative, pin["sha256"])
            raw = json.loads(payload)
            image = raw.get("input", {}).get("image_sha256")
            if image in pages:
                if entry["family"] in observations[image]:
                    raise ValueError("REPLAY_DUPLICATE_PAGE_READING")
                observations[image][entry["family"]] = (raw, payload, relative)
    retained = defaultdict(list)
    if rows_file:
        for line in rows_file.read_bytes().splitlines():
            if line.strip():
                row = json.loads(line)
                key = (row.get("document_sha256"), row.get("source_page"), str(row.get("line_code")),
                       row.get("raw_row_label"), row.get("current_period_label"))
                retained[key].append(row)
    results = []
    for image_sha, page in sorted(pages.items(), key=lambda item: item[1]["key"]):
        # The exact original PDF and unannotated image remain factual inputs.
        read_bound(neutral_root, page["image"], image_sha)
        read_bound(neutral_root, page["original_pdf"], page["document_sha256"])
        pair = observations[image_sha]
        cells = {family: selected_cells(value[0]) for family, value in pair.items()}
        keys = set().union(*(set(value) for value in cells.values()))
        for code, label, header in sorted(keys, key=lambda k: tuple(str(x) for x in k)):
            reasons = []
            if set(pair) != {"claude", "gemini"}:
                reasons.append("REPLAY_TWO_SEALED_FAMILIES_MISSING")
            values = {f: cells[f].get((code, label, header), []) for f in pair}
            if any(len(value) != 1 for value in values.values()):
                reasons.append("REPLAY_CELL_MISSING_OR_AMBIGUOUS")
            for raw, _, _ in pair.values():
                if str(raw["model_family"]).lower() not in dual.FAMILY_ALIASES:
                    reasons.append("DUAL_READER_READER_CONTRACT_OR_FAMILY_UNKNOWN")
                if raw.get("recorded_at") is None:
                    reasons.append("REPLAY_RECORDED_AT_MISSING")
                if not raw["table"].get("form_reference_literal"):
                    reasons.append("REPLAY_PRINTED_FORM_LITERAL_MISSING")
                if not raw["table"].get("scope_literal"):
                    reasons.append("REPLAY_PRINTED_SCOPE_LITERAL_MISSING")
            for occurrences in values.values():
                for column, cell in occurrences:
                    if column.get("role") != "current":
                        reasons.append("REPLAY_COLUMN_ROLE_NOT_CURRENT_V1")
                    if cell.get("uncertainty") != []:
                        reasons.append("DUAL_READER_UNRESOLVED_CELL_UNCERTAINTY")
            if len(values) == 2 and all(len(v) == 1 for v in values.values()):
                a, b = [v[0][1] for v in values.values()]
                if (a.get("raw_value_literal"), a.get("sign_literal")) != (b.get("raw_value_literal"), b.get("sign_literal")):
                    reasons.append("DUAL_READER_LITERAL_DISAGREEMENT")
            metric = None
            for raw, _, _ in pair.values():
                for c, literal, name in FORM_ROWS.get(raw["table"].get("form_reference_literal"), ()):
                    if (c, literal) == (code, label):
                        metric = name
            # EVF candidates retain their native meaning but grant no form identity.
            if page["key"].startswith("EVF"):
                metric = next((m for c, literal, m in EVF_CANDIDATE_ROWS if (c, literal) == (code, label)), None)
            if metric is None:
                reasons.append("DUAL_READER_ACCOUNTING_FORM_OR_ROW_IDENTITY_UNSUPPORTED")
            lookup = (page["document_sha256"], page["source_page"], str(code), label, header)
            candidates = retained.get(lookup, [])
            gate = dual.verify_dual_reader_transcription({}, None, source_record=None,
                retained_bytes=None, parse_amount=None, parse_unit=None, recognize_period=None, recognize_scope=None)
            common = None
            if len(candidates) == 1:
                from stocklookup_core.evidence.official_document_qualification import admit_retained_financial_fact
                row = candidates[0]
                landing = evidence_root / row["evidence_subdir"]
                if not landing.resolve().is_relative_to(evidence_root.resolve()):
                    raise ValueError("REPLAY_PATH_ESCAPE")
                evidence = dual.load_retained_dual_reader_proof(row, landing)
                if (evidence and sorted(sha(p) for p in evidence["raw_reader_bytes"])
                        == sorted(sha(p[1]) for p in pair.values())):
                    common = admit_retained_financial_fact(row, evidence_root=evidence_root)
                    # Common admission calls the extended verifier and all other gates.
                    gate = {"valid": common["state"] == "ADMITTED", "reason_codes": common["reason_codes"]}
                else:
                    reasons.append("REPLAY_SEALED_READER_BINDING_MISMATCH")
            elif len(candidates) > 1:
                reasons.append("REPLAY_RETAINED_ROW_AMBIGUOUS")
            if common is None:
                reasons.extend(gate["reason_codes"])
                reasons.append("REPLAY_COMMON_OWNER_PROOFS_UNAVAILABLE")
                if str(code) == "201":
                    reasons.append("DUAL_READER_APPROPRIATION_BASIS_UNPROVEN")
            else:
                reasons.extend(common["reason_codes"])
            # Diagnostics never override a complete owner replay. A missing proof
            # can never produce ADMIT even if both cold readers agree numerically.
            state = "ADMIT" if common and common["state"] == "ADMITTED" and not reasons else "REFUSE"
            results.append({"page_key": page["key"], "document_sha256": page["document_sha256"],
                "source_page": page["source_page"], "line_code_literal": code,
                "row_label_literal": label, "column_label_literal": header,
                "candidate_metric": metric, "state": state, "reason_codes": sorted(set(reasons)),
                "observed_cells": {f: [v[1] for v in occurrences] for f, occurrences in values.items()}})
    return {"schema_version": "dual_reader_form_replay/v1", "authority_effect": "OFFLINE_RESEARCH_ONLY",
        "pit_backtest_eligible": False, "sealed_index_sha256": sha(index_bytes),
        "pages": len(pages), "counts": dict(Counter(r["state"] for r in results)),
        "page_inputs": [{"page_key": p["key"], "document_sha256": p["document_sha256"],
            "image_sha256": image_sha, "readings": {
                family: {"raw_sha256": sha(value[1]), "sealed_relative_path": value[2]}
                for family, value in observations[image_sha].items()}}
            for image_sha, p in sorted(pages.items(), key=lambda item: item[1]["key"])],
        "by_issuer": {issuer: dict(Counter(r["state"] for r in results if r["page_key"].startswith(issuer)))
                      for issuer in ("EVF", "SSI")},
        "missing_proof_inputs": list(MISSING_PROOFS) if any("REPLAY_COMMON_OWNER_PROOFS_UNAVAILABLE" in r["reason_codes"] for r in results) else [],
        "cells": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed-root", required=True, type=Path)
    parser.add_argument("--neutral-root", required=True, type=Path)
    parser.add_argument("--rows-file", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    if bool(args.rows_file) != bool(args.evidence_root):
        parser.error("--rows-file and --evidence-root must be supplied together")
    try:
        report = replay(args.sealed_root, args.neutral_root, rows_file=args.rows_file, evidence_root=args.evidence_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 1 if report["counts"].get("REFUSE") else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
