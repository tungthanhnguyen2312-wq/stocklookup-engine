"""Auditor-page continuation and subset refresh preserve authority boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from tests.test_reviewed_interim_canonical_ingress import _materialization, REVIEW_PAGE
from official_financial_assurance_evidence import resolve_document_assurance_evidence, validate_assurance_claim
from tools.run_reviewed_interim_canonical_ingress import write_outputs
from financial_evidence_currency_refresh import PUBLIC_FACTS, PUBLIC_PRECEDENCE

TITLE = "BÁO CÁO KIỂM TOÁN ĐỘC LẬP báo cáo tài chính hợp nhất"
OPINION = "Ý kiến của Kiểm toán viên báo cáo tài chính hợp nhất đã phản ánh trung thực trên các khía cạnh trọng yếu theo chuẩn mực Việt Nam"

EN_TITLE = "INDEPENDENT AUDITORS' REPORT We have audited the consolidated financial statements"
EN_OPINION = ("Opinion In our opinion the consolidated financial statements present fairly "
              "in all material respects in accordance with Vietnamese Accounting Standards")
EN_REVIEW = ("REPORT ON REVIEW OF INTERIM FINANCIAL INFORMATION "
             "We have reviewed the interim consolidated financial information in accordance with "
             "Standard on Review Engagements 2410. We do not express an audit opinion")


@pytest.mark.parametrize("texts,status", [((EN_TITLE + " " + EN_OPINION,), "audited"),
    ((EN_TITLE, EN_OPINION), "audited"),
    ((EN_TITLE, "INDEPENDENT AUDITORS' REPORT (Continued) " + EN_OPINION), "audited"),
    ((EN_REVIEW,), "reviewed"),
    ((EN_REVIEW.replace("interim consolidated financial information", "interim consolidated financial statements"),), "reviewed")])
def test_bounded_english_report_classes(texts, status):
    result = resolve_document_assurance_evidence(_materialization(*texts))
    assert result["state"] == "QUALIFIED"
    assert result["audit_or_review_status"] == status


@pytest.mark.parametrize("texts", [
    (EN_TITLE,), (EN_OPINION,), (EN_TITLE, "unrelated", EN_OPINION),
    (EN_TITLE.replace("INDEPENDENT", "DEPENDENT"), EN_OPINION),
    (EN_TITLE, EN_OPINION.replace("Opinion In", "Summary In")),
    (EN_TITLE, EN_OPINION.replace("present fairly", "might present fairly")),
    (EN_TITLE, EN_OPINION + " We do not express an audit opinion"),
    (EN_TITLE, "INDEPENDENT AUDITORS' REPORT " + EN_OPINION),
    (EN_REVIEW.replace("ON REVIEW", "ON PREVIEW"),),
    (EN_REVIEW.replace("2410", "2411"),),
    (EN_REVIEW.replace("2410", "24100"),),
    (EN_REVIEW.replace("interim consolidated financial", "interim consolidated financially"),),
    (EN_REVIEW.replace("interim consolidated", "interim separate"),),
    (EN_REVIEW.replace("Review Engagements", "Audit Engagements"),),
    (EN_REVIEW + " We do not express a review conclusion",),
    ("Management discusses review of interim financial information and 2410",),
])
def test_english_near_miss_unrelated_and_negative_reports_refused(texts):
    assert resolve_document_assurance_evidence(_materialization(*texts))["state"] == "BLOCKED"


@pytest.mark.parametrize("vn,en", [
    ("Ý kiến ngoại trừ", "Qualified opinion"),
    ("Ý kiến trái ngược", "Adverse opinion"),
    ("Từ chối đưa ra ý kiến", "Disclaimer of opinion"),
    ("Vấn đề cần nhấn mạnh", "Emphasis of matter"),
])
def test_english_modifications_keep_vietnamese_assurance_status_treatment(vn, en):
    # This owner classifies assurance kind, not opinion quality or valuation fitness.
    vietnamese = resolve_document_assurance_evidence(_materialization(TITLE + " chúng tôi đã kiểm toán " + vn))
    english = resolve_document_assurance_evidence(_materialization(EN_TITLE + " " + EN_OPINION + " " + en))
    assert english["audit_or_review_status"] == vietnamese["audit_or_review_status"]
    vietnamese = resolve_document_assurance_evidence(_materialization(REVIEW_PAGE + " " + vn))
    english = resolve_document_assurance_evidence(_materialization(EN_REVIEW + " " + en))
    assert english["audit_or_review_status"] == vietnamese["audit_or_review_status"]

@pytest.mark.parametrize("texts,opinion_page", [((TITLE + " " + OPINION,), 1), ((TITLE, OPINION), 2)])
def test_literal_opinion_same_or_immediately_next_page(texts, opinion_page):
    result = resolve_document_assurance_evidence(_materialization(*texts))
    assert result["state"] == "QUALIFIED"
    assert result["audit_or_review_status"] == "audited"
    assert result["opinion_evidence"]["page_number"] == opinion_page
    assert result["opinion_evidence"]["rendered_image_sha256"] == hashlib.sha256(texts[opinion_page-1].encode()).hexdigest()
    assert result["opinion_evidence"]["token_ids"]

@pytest.mark.parametrize("texts", [
    (TITLE,), (OPINION,), (TITLE, "unrelated", OPINION),
    (TITLE.replace("ĐỘC", "BỘC"), OPINION),
    (TITLE.replace("hợp nhất", "riêng"), OPINION),
    (TITLE, OPINION.replace("hợp nhất", "riêng")),
    (TITLE, OPINION.replace("Kiểm toán viên", "Ban điều hành")),
    (TITLE, OPINION.replace("đã phản ánh", "sẽ phản ánh")),
    (TITLE, OPINION + " Chúng tôi không đưa ra ý kiến kiểm toán"),
    (TITLE, "BÁO CÁO KIỂM TOÁN ĐỘC LẬP " + OPINION.replace("hợp nhất", "riêng")),
])
def test_report_or_scope_missing_or_unrelated_page_blocks(texts):
    assert resolve_document_assurance_evidence(_materialization(*texts))["state"] == "BLOCKED"


def test_missing_page_does_not_bridge_and_review_conflict_blocks():
    m = _materialization(TITLE, OPINION)
    m["pages"][1]["page_number"] = 3
    assert resolve_document_assurance_evidence(m)["state"] == "BLOCKED"
    assert resolve_document_assurance_evidence(_materialization(TITLE, OPINION, REVIEW_PAGE))["reason"] == "ASSURANCE_STATUS_AMBIGUOUS"


def test_opinion_page_hash_changes_evidence_and_other_source_claim_rejected():
    m = _materialization(TITLE, OPINION)
    first = resolve_document_assurance_evidence(m)
    m["pages"][1]["source_image_evidence"]["rendered_image_sha256"] = "different-image"
    assert resolve_document_assurance_evidence(m)["evidence_id"] != first["evidence_id"]
    with pytest.raises(ValueError, match="ASSURANCE_EVIDENCE_DOES_NOT_SUPPORT_STATUS"):
        validate_assurance_claim("audited", first, document_sha256="b" * 64)


def test_subset_refresh_preserves_other_issuers_same_year_and_all_other_periods(tmp_path):
    old = [{"ticker": t, "reporting_period": p, "canonical_metric": "revenue", "value": n}
           for n, (t, p) in enumerate((("HPG", "2025"), ("PNJ", "2025"), ("PVD", "2025"), ("PNJ", "2026-H1")))]
    prior = [{"key": {"ticker": r["ticker"], "period": r["reporting_period"]}, "status": "NOT_COMPARABLE"} for r in old]
    for name, rows in ((PUBLIC_FACTS, old), (PUBLIC_PRECEDENCE, prior)):
        (tmp_path / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf8")
    refreshed = {**old[1], "value": 42}
    result = {"report": {"documents": [{"ticker": "PNJ", "reporting_period": "2025"}]},
              "overlay_rows": [refreshed], "precedence_rows": [prior[1]]}
    untouched = copy.deepcopy(result)
    originals = {name:(tmp_path/name).read_bytes() for name in (PUBLIC_FACTS,PUBLIC_PRECEDENCE)}
    with pytest.raises(ValueError, match="CANDIDATE_NOT_ADMITTED"):
        write_outputs(result, tmp_path, preserve_other_documents=True)
    rows = [json.loads(line) for line in (tmp_path / PUBLIC_FACTS).read_text().splitlines()]
    assert len(rows) == 4
    assert rows == old
    assert all((tmp_path/name).read_bytes()==content for name,content in originals.items())
    assert len((tmp_path / PUBLIC_PRECEDENCE).read_text().splitlines()) == 4
    assert result == untouched


def test_retained_source_anchor_spans_and_new_facts_stay_historical_context():
    from tests.test_current_official_evidence_projection import baseline
    import market_wide_current_fundamental_research as fundamental
    from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import _financial_input
    from stocklookup_core.decision.current_research_decision_packet import _valuation
    from ai_research_session_delivery import _compact_context
    root = Path(__file__).resolve().parents[1] / "derived/financial-evidence-currency-refresh-v1"
    sources = json.loads((root / "retained_annual_assurance_source_tokens.json").read_text(encoding="utf8"))
    for source in sources:
        materialization = {"document_sha256": source["document_sha256"],
            "materialization_id": source["materialization_id"], "pages": source["selected_pages"]}
        result = resolve_document_assurance_evidence(materialization)
        assert result["state"] == "QUALIFIED"
        assert result["page_number"] == source["assurance"]["page_number"]
        assert result["opinion_evidence"]["page_number"] == source["assurance"]["opinion_evidence"]["page_number"]
    rows = [json.loads(line) for line in (root / PUBLIC_FACTS).read_text(encoding="utf8").splitlines()]
    new = [r for r in rows if r["period_type"] == "annual" and r["ticker"] in {"PNJ", "PVD"}]
    assert len(new) == 6
    original = baseline()
    early = fundamental.project_session(baseline=original, official_rows=new,
        session="2026-10-07", cutoff="2026-10-07T15:00:00+07:00")
    assert all(not r["official_field_context"] for r in early["records"].values())
    later = fundamental.project_session(baseline=original, official_rows=new,
        session="2026-10-08", cutoff="2026-10-08T15:00:00+07:00")
    # Exact pinned v2 retained rows remain historical context; edited copies would not.
    assert sum(len(r["official_field_context"]) for r in later["records"].values()) == 6
    for ticker, record in later["records"].items():
        assert record["metrics"] == original["records"][ticker]["metrics"]
        for field in record["official_field_context"]:
            assert field["temporal_status"] == "HISTORICAL_OFFICIAL_FACT"
            assert field["valuation_use"] == "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT"
        if ticker in {"PNJ", "PVD"}:
            financial = _financial_input(record, later)
            assert _valuation({"financial_input": financial})["official_field_context"] == record["official_field_context"]
            assert _compact_context(ticker, {"product": {}}, {"fundamental": later})["fundamental_context"]["official_field_context"] == record["official_field_context"]


EN_REVIEW_FS = ("REPORT ON REVIEW OF INTERIM CONSOLIDATED FINANCIAL STATEMENTS "
                "We conducted our review in accordance with Vietnamese Standard on Review Engagements "
                "VSRE 2410 on the interim consolidated financial statements. We do not express an audit opinion")


def test_english_review_titled_by_statements_with_vsre_2410_is_reviewed():
    # Deloitte Vietnam's English report wording (POW 2025-H1 / 2026-H1).
    result = resolve_document_assurance_evidence(_materialization(EN_REVIEW_FS))
    assert result["state"] == "QUALIFIED"
    assert result["audit_or_review_status"] == "reviewed"


@pytest.mark.parametrize("text", [
    EN_REVIEW_FS.replace("INTERIM CONSOLIDATED FINANCIAL STATEMENTS", "INTERIM SEPARATE FINANCIAL STATEMENTS", 1)
                .replace("interim consolidated financial statements", "interim separate financial statements"),
    EN_REVIEW_FS.replace("VSRE 2410", "VSRE 2411"),
    EN_REVIEW_FS.replace("VSRE 2410", "VSA 2410"),
    EN_REVIEW_FS.replace("ON REVIEW", "ON PREVIEW"),
    EN_REVIEW_FS.replace("REPORT ON REVIEW OF INTERIM CONSOLIDATED FINANCIAL STATEMENTS",
                         "REPORT ON AUDIT OF INTERIM CONSOLIDATED FINANCIAL STATEMENTS"),
])
def test_english_review_statements_title_near_misses_refused(text):
    assert resolve_document_assurance_evidence(_materialization(text))["state"] == "BLOCKED"


def test_vsre_citation_split_by_ocr_artifact_requires_both_exact_literals():
    split = EN_REVIEW_FS.replace("Vietnamese Standard on Review Engagements VSRE 2410",
                                 "Vietnamese Standards on Review Engagements el VSRE 2410")
    assert resolve_document_assurance_evidence(_materialization(split))["audit_or_review_status"] == "reviewed"
    for broken in (split.replace("VSRE 2410", "VSRE 2411"),
                   split.replace("Vietnamese Standards on Review Engagements", "Vietnamese Standards on Audit Engagements"),
                   split.replace("Vietnamese Standards on Review Engagements el ", "")):
        assert resolve_document_assurance_evidence(_materialization(broken))["state"] == "BLOCKED", broken
