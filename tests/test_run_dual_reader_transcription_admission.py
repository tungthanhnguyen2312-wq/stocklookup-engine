"""Fact-local construction and global retained provenance regressions."""
from copy import deepcopy
import json

import pytest

from tools import run_dual_reader_transcription_admission as runner


def _table():
    return {"issuer_literal": "synthetic", "form_reference_literal": "B02-DN/HN",
            "statement_title_literal": "Consolidated income statement",
            "columns": [{"column_id": "c1", "label_literal": "2025"}],
            "rows": [{"line_code_literal": code, "row_label_literal": metric,
                      "cells": [{"column_id": "c1", "raw_value_literal": "123", "sign_literal": "unsigned"}]}
                     for metric, code in runner.METRICS]}


def _build(first, second=None):
    rejections = []
    evidence = {"document_metadata": {"metadata_claims": {"currency": {"value": "VND"},
                  "unit_scale": {"value": 1}}}, "audit_or_review_status": "audited",
                "observed_at": "2026-11-24T00:00:00Z", "source_family": "issuer_ir",
                "assurance_evidence": {}, "ocr_layout_proof": {}}
    rows = runner.build_rows(spec=runner.NVL_2025_P12, document_evidence=evidence,
        raw_table=first, other_tables=() if second is None else (second,),
        proof_ref={"relative_path": "synthetic", "proof_sha256": "synthetic"},
        knowledge_available_at="2026-11-25T12:30:00+07:00", subdir="synthetic", rejections=rejections)
    return rows, rejections


@pytest.mark.parametrize("reader", [0, 1])
def test_duplicate_parent_row_is_local_to_code_61(reader):
    tables = [_table(), _table()]
    tables[reader]["rows"].append(deepcopy(tables[reader]["rows"][-1]))
    rows, rejections = _build(*tables)
    assert [r["line_code"] for r in rows] == ["10", "60"]
    assert rejections == [{"canonical_metric": "attributable_net_income", "line_code": "61",
                            "state": "BLOCKED", "reason_codes": ["ROW_NOT_UNIQUE:61"]}]


@pytest.mark.parametrize("case,reason", [("missing", "CELL_NOT_UNIQUE:61"),
    ("duplicate", "CELL_NOT_UNIQUE:61"), ("signed", "SIGNED_CELL_NOT_SUPPORTED_BY_THIS_RUN:61"),
    ("unparsable", "AMOUNT_LITERAL_INVALID")])
def test_unsupported_parent_cell_does_not_abort_other_facts(case, reason):
    table = _table()
    cells = table["rows"][-1]["cells"]
    if case == "missing":
        cells.clear()
    elif case == "duplicate":
        cells.append(deepcopy(cells[0]))
    elif case == "signed":
        cells[0].update(sign_literal="parentheses", raw_value_literal="(123)")
    else:
        cells[0]["raw_value_literal"] = "UNREADABLE"
    rows, rejections = _build(table)
    assert [r["line_code"] for r in rows] == ["10", "60"]
    assert rejections[0]["line_code"] == "61"
    if case != "unparsable":
        assert rejections[0]["reason_codes"] == [reason]
    else:
        assert rejections[0]["reason_codes"]


def _raw_pair(tmp_path):
    spec = deepcopy(runner.NVL_2025_P12)
    refs = []
    for index, family in enumerate(("claude", "gemini")):
        name = f"{family}.json"
        raw = {"contract_version": runner.dual.RAW_VERSION, "model_family": family,
               "reader_id": family, "method": "DIRECT_PAGE_IMAGE", "independent_input": True,
               "saw_other_reader_output": False, "recorded_at": "2026-11-25T08:10:00+07:00",
               "input": {key: spec[key] for key in ("document_sha256", "document_id", "source_page", "printed_page")}}
        raw["input"]["image_sha256"] = spec["image_sha256"]
        (tmp_path / name).write_text(json.dumps(raw), encoding="utf-8")
        refs.append((family, name, "2026-11-25T08:15:00+07:00"))
    spec["readings"] = refs
    return spec


@pytest.mark.parametrize("case,reason", [("document", "READER_INPUT_BINDING_MISMATCH"),
    ("printed_page", "READER_INPUT_BINDING_MISMATCH"),
    ("independence", "READER_INDEPENDENCE_NOT_PROVEN"),
    ("timestamp", "RAW_NOT_RETAINED_BEFORE_COMPARISON")])
def test_global_provenance_failures_refuse_entire_batch_before_writes(tmp_path, case, reason):
    readers = tmp_path / "readers"
    readers.mkdir()
    spec = _raw_pair(readers)
    path = readers / "claude.json"
    raw = json.loads(path.read_text())
    if case == "document":
        raw["input"]["document_sha256"] = "0" * 64
    elif case == "printed_page":
        raw["input"]["printed_page"] = "10"
    elif case == "independence":
        raw["saw_other_reader_output"] = True
    else:
        raw["recorded_at"] = "2026-11-25T09:00:00+07:00"
    path.write_text(json.dumps(raw), encoding="utf-8")
    original = tmp_path / spec["original_subdir"]
    original.mkdir()
    source = {"sha256": spec["document_sha256"], "document_id": spec["document_id"],
              "ticker": spec["ticker"], "reporting_period": spec["reporting_period"],
              "acquisition_status": "retained", "observed_at": "2026-11-24T00:00:00Z"}
    (original / runner.MANIFEST).write_text(json.dumps({"records": [source]}), encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        runner.run(landing_root=tmp_path, reader_root=readers,
                   document_evidence_path=tmp_path / "unused.json", ocr_layout_proof_path=tmp_path / "unused-proof.json",
                   admission_completed_at="2026-11-25T12:30:00+07:00", spec=spec)
    assert not (tmp_path / spec["new_subdir"]).exists()


def test_six_specs_preserve_literal_pages_and_retained_comparison_times():
    specs = [s for s in runner.SPECS.values() if s["ticker"] in ("POW", "NVL")]
    assert len(specs) == 6 and len({s["new_subdir"] for s in specs}) == 6
    assert runner.NVL_2025_H1_P12["printed_page"] == "10"
    assert runner.NVL_2026_H1_P12["printed_page"] == "Trang 10"
    assert runner.NVL_2025_P12["comparison_started_at"] == "2026-11-25T08:15:17+07:00"
