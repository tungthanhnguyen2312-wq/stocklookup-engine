"""Fact-local construction and global retained provenance regressions."""
from copy import deepcopy
import json

import pytest

from tools import run_dual_reader_transcription_admission as runner


def _replay_config(tmp_path, *, enabled=False, ticker=None):
    from pathlib import Path
    import hashlib
    config = json.loads((runner.ROOT / runner.dual.DUAL_READER_TTM_CONFIG_REL).read_bytes())
    config["enabled"] = enabled
    if ticker:
        specs = [s for s in runner.SPECS.values() if s["ticker"] == ticker]
        config["evidence_subdirs"] = [{"subdir": s["new_subdir"], "ticker": ticker,
            "reporting_period": s["reporting_period"], "approved_at": config["approved_at"],
            "rows_file": "dual_reader_admitted_rows.jsonl", "rows_sha256": "1" * 64,
            "document_sha256": s["document_sha256"], "proof_sha256": "2" * 64, "enabled": True} for s in specs]
    path = tmp_path / runner.dual.DUAL_READER_TTM_CONFIG_REL
    path.parent.mkdir(parents=True)
    raw = json.dumps(config).encode()
    path.write_bytes(raw)
    (path.parent / "owner_daily_capacity_qualification.json").write_text(json.dumps({
        "source_sha256": {runner.dual.DUAL_READER_TTM_CONFIG_REL: hashlib.sha256(raw).hexdigest()}}), encoding="utf-8")
    return path


def test_replay_ttm_off_never_reads_landing(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("OFF loaded retained evidence")
    monkeypatch.setattr(runner.dual, "load_admitted_rows", forbidden)
    report = runner.replay_ttm(_replay_config(tmp_path), "2026-11-28", ["POW", "NVL"])
    assert report == {"state": "OFF", "records": {}, "network_used": False}


@pytest.mark.parametrize("ticker", ["POW", "NVL", "HAH", "BWE"])
def test_replay_ttm_missing_registered_three_period_evidence_blocks_entire_branch(tmp_path, ticker):
    path = _replay_config(tmp_path, enabled=True, ticker=ticker)
    report = runner.replay_ttm(path, "2026-11-28", [ticker], evidence_root=tmp_path)
    assert report["state"] == "INTEGRITY_BLOCKED"
    assert report["network_used"] is False
    for method_id in ("P/E_TTM", "P/S_TTM"):
        method = report["records"][ticker]["methods"][method_id]
        assert method["status"] == "INPUT_BLOCKED" and method["value"] is None


def test_replay_ttm_rejects_nvl_restated_vintage_before_loading(tmp_path):
    import hashlib
    path = _replay_config(tmp_path, enabled=True, ticker="NVL")
    config = json.loads(path.read_bytes())
    prior = next(e for e in config["evidence_subdirs"] if e["reporting_period"] == "2025-H1")
    prior["document_sha256"] = next(e["document_sha256"] for e in config["evidence_subdirs"] if e["reporting_period"] == "2026-H1")
    raw = json.dumps(config).encode()
    path.write_bytes(raw)
    pin = path.parent / "owner_daily_capacity_qualification.json"
    pin.write_text(json.dumps({"source_sha256": {runner.dual.DUAL_READER_TTM_CONFIG_REL: hashlib.sha256(raw).hexdigest()}}))
    assert runner.replay_ttm(path, "2026-11-28", ["NVL"], evidence_root=tmp_path)["reason"] == "ADMISSION_SPEC_IDENTITY_MISMATCH"


def test_replay_ttm_registry_approval_is_not_retroactive(tmp_path):
    report = runner.replay_ttm(_replay_config(tmp_path, enabled=True), "2026-11-25", ["POW", "NVL"])
    assert report["state"] == "PRE_APPROVAL_CUTOFF" and report["records"] == {}


def _table():
    return {"issuer_literal": "synthetic", "form_reference_literal": "B02-DN/HN",
            "currency_unit_literal": "VND",
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
        # A printed loss "(digits)" on 60/61 is supported (see test below); other vocabulary is not.
        cells[0].update(sign_literal="minus", raw_value_literal="123")
    else:
        cells[0]["raw_value_literal"] = "UNREADABLE"
    rows, rejections = _build(table)
    assert [r["line_code"] for r in rows] == ["10", "60"]
    assert rejections[0]["line_code"] == "61"
    if case != "unparsable":
        assert rejections[0]["reason_codes"] == [reason]
    else:
        assert rejections[0]["reason_codes"]


def test_parenthesized_profit_loss_builds_negative_row_but_revenue_sign_is_refused():
    table = _table()
    table["rows"][-1]["cells"][0].update(sign_literal="parentheses", raw_value_literal="123")
    rows, rejections = _build(table)
    parent = [r for r in rows if r["line_code"] == "61"]
    assert len(parent) == 1 and parent[0]["normalized_value"] < 0
    assert parent[0]["raw_value_text"] == "(123)" and not rejections
    table = _table()
    revenue = next(r for r in table["rows"] if r["line_code_literal"] == "10")
    revenue["cells"][0].update(sign_literal="parentheses")
    rows, rejections = _build(table)
    assert "10" not in [r["line_code"] for r in rows]
    assert rejections[0]["reason_codes"] == ["SIGNED_CELL_NOT_SUPPORTED_BY_THIS_RUN:10"]


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
        raw["input"]["printed_page"] = "Trang 11"
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


def test_runner_accepts_only_exact_trang_prefix_binding(tmp_path):
    spec = _raw_pair(tmp_path)
    path = tmp_path / "gemini.json"
    raw = json.loads(path.read_text())
    numeric = runner.dual.printed_page_identity(spec["printed_page"])
    spec["printed_page"] = numeric
    raw["input"]["printed_page"] = "Trang " + numeric
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert len(runner._validate_readings(spec=spec, reader_root=tmp_path,
        observed_at="2026-11-24T00:00:00Z", completed="2026-11-25T12:30:00+07:00")) == 2
    raw["input"]["printed_page"] = "Trang  " + numeric
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="READER_INPUT_BINDING_MISMATCH"):
        runner._validate_readings(spec=spec, reader_root=tmp_path,
            observed_at="2026-11-24T00:00:00Z", completed="2026-11-25T12:30:00+07:00")


def test_runner_binds_identical_reader_unit_without_repairing_metadata():
    first, second = _table(), _table()
    first["currency_unit_literal"] = second["currency_unit_literal"] = "Đơn vị tính: Đồng Việt Nam"
    rows, rejected = _build(first, second)
    assert not rejected and len(rows) == 3
    assert all(r["source_unit_scale"] == 1 and r["currency"] == "VND" for r in rows)
    second["currency_unit_literal"] += " "
    with pytest.raises(ValueError, match="READERS_UNIT_LITERAL_NOT_IDENTICAL_EXPLICIT_VND"):
        _build(first, second)

# Registration tests use synthetic bytes only; HL executes the retained replay.
@pytest.mark.parametrize("spec_id,sha,page", [
    ("HAH-2025-P13", "2648374e2e6c60403a353f36456a88f4c34675f1cb4ff3cd6a5adc5d0b90f1b1", 13),
    ("HAH-2025-H1-P12", "a36ae93c0c3434d3e47c36f5d6de07ca6623db880b01c850a0bdd9855a45837b", 12),
    ("HAH-2026-H1-P13", "913d92bec2564ad9efa15db114e34419d21e4b466bf51964ddca941682cf7291", 13),
    ("BWE-2025-P12", "9e028ec5b6e612767068d0ba25c83c1350a86e55753a61fda7625fae26c4dcf9", 12),
    ("BWE-2025-H1-P12", "acb48684fcf4d14266f2bd0ca684331d7b69e2953a50f612e9004cb055cb92c8", 12),
    ("BWE-2026-H1-P12", "6e19b66271a6cf87be38791ffb2c29985b13930b12dfd72399909ffde2c9cdef", 12),
])
def test_hah_bwe_exact_spec_bindings(tmp_path, spec_id, sha, page):
    from stocklookup_core.evidence.official_ocr_layout_proof import layout_for
    spec = runner.SPECS[spec_id]
    assert (spec["document_sha256"], spec["source_page"]) == (sha, page)
    assert layout_for(sha)["statement_pages"] == (page,)
    assert spec["original_subdir"] == "acquisition-batch3-20261126"
    assert spec["new_subdir"].endswith("-20261126")
    assert spec["readings"][1][0] == "gpt"
    # HAH 2025-H1: first ChatGPT reading disagreed on scope/period wording; the cross-family
    # condition-5 third reading (new conversation, same prompt) agrees and is the admitted pair.
    expected = "/chatgpt-r2/chatgpt-reader.raw.json" if spec_id == "HAH-2025-H1-P12" else "/chatgpt/chatgpt-reader.raw.json"
    assert spec["readings"][1][1].endswith(expected)
    refs = []
    for family, relative, retained in spec["readings"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = {"contract_version": runner.dual.RAW_VERSION,
               "model_family": "openai-chatgpt" if family == "gpt" else "anthropic-claude",
               "reader_id": family, "method": "DIRECT_PAGE_IMAGE", "independent_input": True,
               "saw_other_reader_output": False, "recorded_at": "2026-11-26T08:58:00+07:00",
               "input": {k: spec[k] for k in ("document_sha256", "document_id", "source_page", "printed_page", "image_sha256")}}
        path.write_text(json.dumps(raw), encoding="utf-8")
        refs.append((path, raw))
    args = dict(spec=spec, reader_root=tmp_path, observed_at="2026-11-26T00:00:00Z",
                completed="2026-11-26T10:00:00+07:00")
    assert len(runner._validate_readings(**args)) == 2
    path, raw = refs[1]
    for field, bad in (("document_sha256", "0" * 64), ("source_page", page + 1), ("image_sha256", "0" * 64)):
        altered = deepcopy(raw)
        altered["input"][field] = bad
        path.write_text(json.dumps(altered), encoding="utf-8")
        with pytest.raises(ValueError, match="READER_INPUT_BINDING_MISMATCH"):
            runner._validate_readings(**args)
    altered = deepcopy(raw)
    altered["model_family"] = "openai-chatgpt-other"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="READER_CONTRACT_OR_FAMILY_MISMATCH"):
        runner._validate_readings(**args)
