"""Bounded HOSE ex-date corporate-action qualification for HPG, PVD, SSI and POW.

Three steps, each explicit:

  --acquire  retain the finite HOSE originals below through the governed acquirer (network;
             one request at a time, each admitted by `config/official_source_registry.json`).
  --ocr      materialize the governed OCR sidecar for every page of those scans (local
             Tesseract, two fixed language configurations, no repair of any token).
  (default)  offline replay: re-hash the retained bytes, verify the sidecar, build reviewed
             observations, the existing ledger and the existing factor-chain cohort, and write
             the artifact.

No other issuer, source or document is in scope. Knowledge time is Producer's own receipt of
these bytes; a portal posting time or HTTP Last-Modified is never a knowledge clock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stocklookup_core.evidence.bitemporal_semantic_contract import (  # noqa: E402
    project_official_evidence_temporal_metadata, propagate_derived_knowledge)
from stocklookup_core.evidence.corporate_action_events import reviewed_scan_observation  # noqa: E402
from stocklookup_core.evidence.official_corporate_action_ledger import build_ledger  # noqa: E402
from stocklookup_core.evidence.official_document_acquisition import acquire  # noqa: E402
from stocklookup_core.evidence.official_document_ocr_handoff import replay as replay_ocr  # noqa: E402
from stocklookup_core.evidence.official_document_ocr_handoff import sha256_file  # noqa: E402
from stocklookup_core.evidence.qualified_corporate_action_factor_chain import build_factor_chain_cohort  # noqa: E402

EVIDENCE = ROOT / "operations-review/official-ca-hose-ex-date-qualification-v1-20261025"
RETENTION = EVIDENCE / "official_document_retention"
MANIFEST = RETENTION / "official_document_acquisition_manifest.json"
OCR_SIDECAR = EVIDENCE / "derived/hose_scan_ocr_sidecar.json"
OUTPUT = EVIDENCE / "official_ca_hose_ex_date_qualification_20261025.json"
OCR_LANGUAGES = ("vie", "vie+eng")
OCR_DPI = 300
GOVERNED_SESSIONS = tuple(json.loads((ROOT / "config/governed_trading_session_calendar_v1.json")
                                     .read_text(encoding="utf-8"))["sessions"])
_SIDECAR_ROW_FIELDS = ("document_id", "document_sha256", "page", "provenance", "status", "text",
                       "text_sha256", "stdout_sha256", "diagnostic", "citation_id")
_STATIC = "https://staticfile.hsx.vn/Uploads/UploadDocuments/"

#: The finite request set. Every URL is a HOSE original first located by GrokBot issue #51
#: (ai-agent-inbox bbc153fb); the locator is a lead, the retained bytes are the evidence.
ACQUISITION_REQUESTS = (
    {"ticker": "HPG", "document_class": "ex_right_notice", "hose_news_id": "2462408",
     "path": "2462408/20260515%20-%20HPG%20-%20Thong%20bao%201121%20tra%20co%20tuc%20bang%20co%20phieu.pdf"},
    {"ticker": "HPG", "document_class": "listing_change_notice", "hose_news_id": "2477123",
     "path": "2477123/20260706%20-%20HPG%20-%20Thong%20bao%20giao%20dich%20co%20phieu%20thay%20doi%20dang%20ky%20niem%20yet.pdf"},
    {"ticker": "HPG", "document_class": "corporate_action_notice", "hose_news_id": "2469047",
     "path": "2469047/20260604%20-%20HPG%20-%20Bao%20cao%20ket%20qua%20phat%20hanh%20co%20phieu%20tra%20co%20tuc%20nam%202025.pdf"},
    {"ticker": "PVD", "document_class": "ex_right_notice", "hose_news_id": "2474001",
     "path": "2474001/20260625%20-%20PVD%20-%20TB%201421ve%20ngay%20DKCC%20thuc%20hien%20phat%20hanh%20co%20phieu%20de%20tang%20von%20CP%20tu%20nguon%20VCSH.pdf"},
    {"ticker": "PVD", "document_class": "listing_change_notice", "hose_news_id": "2492067",
     "path": "2492067/20260825%20-%20PVD%20-%20TB%20thay%20doi%20NY%20va%20giao%20dich.pdf"},
    {"ticker": "PVD", "document_class": "corporate_action_notice", "hose_news_id": "2483453",
     "path": "2483453/20260728%20-%20PVD%20-%20CBTT%20Qd%20cua%20HdQT%20ve%20Bao%20cao%20ket%20qua%20phat%20hanh%20co%20phieu_Signed.pdf"},
    {"ticker": "PVD", "document_class": "amendment_or_supersession_notice", "hose_news_id": "2484275",
     "path": "2484275/20260729%20-%20PVD%20-%20Cap%20nhat%20Bao%20cao%20ket%20qua%20phat%20hanh%20co%20phieu_Signed.pdf"},
    {"ticker": "SSI", "document_class": "ex_right_notice", "hose_news_id": "2485374",
     "path": "2485374/20260730%20-%20SSI%20-%20TB%20ngay%20DKCC%20tra%20co%20tuc%202025%20bang%20tien%20va%20PH%20CP%20de%20tang%20von%20CP%20tu%20NV%20CSH.pdf"},
    {"ticker": "POW", "document_class": "listing_change_notice", "hose_news_id": "2430881",
     "path": "2430881/20260114%20-%20POW%20-%20TB%20so%2072%20vv%20giao%20dich%20chung%20khoan%20thay%20doi%20dang%20ky%20niem%20yet.pdf"},
)

#: SHA-256 of the same URLs as recorded by GrokBot #51's evidence manifest. Agreement is
#: corroboration that both retrievals saw one byte sequence, not a second source.
GROKBOT_51_SHA256 = {
    "2462408": "7051ea19b834737409f0e127440f166df888e8928fa9928c4c425ecaf2449f7c",
    "2477123": "12a009fb660f4918d4158db507c43a1b53c5bdb39a3a4201e510dcf3c95d5cce",
    "2474001": "4c1153c8286c56074e5fec8b1e301674988f4609061509f96d1eba3451f58f78",
    "2492067": "950148fd4391b2e90ec1cb3a1e2992fa8964cd9188e6e7dcb9965f0eba3679d7",
    "2485374": "4be4d1f807f789134b8ed883d8265a57a84e99a66ba69943c58d429962e01e1a",
    "2430881": "59a16702d0047c85ffbf2de5f06ab90d62ede992d107065c025403cf09ee0767",
}


def _field(page: int, printed: str, label: str) -> dict[str, Any]:
    return {"page": page, "printed": printed, "label": label}


#: Reviewed readings of the rendered scans, keyed by HOSE news id. Every `printed` token is
#: copied exactly as it appears on the cited page and is re-checked against the governed OCR
#: sidecar on every replay; no value is entered here. A document may recite several legs.
REVIEWS: dict[str, list[dict[str, Any]]] = {
    "2462408": [{  # HOSE 1121/TB-SGDHCM, 14/05/2026: record-date notice
        "event_type": "stock_dividend", "event_type_printed": "trả cổ tức",
        "fields": {
            "ex_date": _field(1, "25/05/2026", "Ngày giao dịch không hưởng quyền"),
            "record_date": _field(1, "26/05/2026", "Ngày đăng ký cuối cùng"),
            "stock_ratio": _field(1, "10%", "Tỷ lệ thực hiện"),
            "shares_planned": _field(1, "767.546.585", "Số lượng cổ phiếu dự kiến phát hành"),
        }}],
    "2477123": [{  # HOSE 1475/TB-SGDHCM, 06/07/2026, citing QĐ 560/QĐ-SGDHCM of 30/06/2026
        "event_type": "stock_dividend", "event_type_printed": "để trả cổ tức",
        "fields": {
            "shares_issued": _field(1, "767.498.665", "Số lượng chứng khoán thay đổi niêm yết"),
            "shares_after": _field(1, "8.442.964.520", "Số lượng chứng khoán sau khi thay đổi niêm yết"),
            "listing_effective_date": _field(1, "02/07/2026", "Ngày thay đổi niêm yết có hiệu lực"),
            "trading_date": _field(1, "15/07/2026", "Ngày giao dịch bổ sung của chứng khoán thay đổi niêm yết"),
        }}],
    "2469047": [{  # HPG 03/BC/2026-TDHP, 04/06/2026: issuer result report to the SSC
        "event_type": "stock_dividend", "event_type_printed": "trả cổ tức",
        "fields": {
            "shares_before": _field(1, "7.675.465.855", "Tổng số cổ phiếu đã phát hành (trước phát hành)"),
            "shares_outstanding_before": _field(1, "7.675.465.855", "Số lượng cổ phiếu đang lưu hành (trước phát hành)"),
            "shares_planned": _field(1, "767.546.585", "Số lượng cổ phiếu dự kiến phát hành"),
            "stock_ratio": _field(2, "100:10", "Tỷ lệ thực hiện quyền"),
            "shares_issued": _field(2, "767.498.665", "Tổng số cổ phiếu đã phân phối"),
            "fractional_shares_cancelled": _field(2, "47.920", "Số cổ phiếu xử lý phần lẻ (đã được hủy bỏ)"),
            "shares_after": _field(2, "8.442.964.520", "Tổng số cổ phiếu sau đợt phát hành"),
        }}],
    "2474001": [{  # HOSE 1421/TB-SGDHCM, 25/06/2026: record-date notice
        "event_type": "bonus_shares", "event_type_printed": "tăng vốn cổ phần từ",
        "fields": {
            "ex_date": _field(1, "14/07/2026", "Ngày giao dịch không hưởng quyền"),
            "record_date": _field(1, "15/07/2026", "Ngày đăng ký cuối cùng"),
            "stock_ratio": _field(1, "66,9%", "Tỷ lệ thực hiện"),
            "shares_planned": _field(1, "371.883.724", "Số lượng cổ phiếu dự kiến phát hành"),
        }}],
    "2492067": [{  # HOSE 1775/TB-SGDHCM, 25/08/2026, citing QĐ 669/QĐ-SGDHCM of 20/08/2026
        "event_type": "bonus_shares", "event_type_printed": "từ nguồn vốn chủ sở hữu",
        "fields": {
            "shares_issued": _field(1, "371.862.185", "Số lượng chứng khoán thay đổi niêm yết"),
            "shares_after": _field(1, "928.158.191", "Số lượng chứng khoán niêm yết sau khi thay đổi niêm yết"),
            "listing_effective_date": _field(1, "24/8/2026", "Ngày thay đổi niêm yết có hiệu lực"),
            "trading_date": _field(1, "07/9/2026", "Ngày giao dịch của chứng khoán thay đổi niêm yết"),
        }}],
    "2484275": [{  # PVD correction of 29/07/2026 enclosing the revised result report
        "event_type": "bonus_shares", "event_type_printed": "tăng vốn cổ phần từ nguồn vốn chủ sở hữu",
        "fields": {
            "shares_before": _field(6, "556.296.006", "Tổng số cổ phiếu đã phát hành (trước phát hành)"),
            "shares_outstanding_before": _field(6, "555.880.006", "Số lượng cổ phiếu đang lưu hành"),
            "treasury_shares_before": _field(6, "416.000", "Số lượng cổ phiếu quỹ"),
            "shares_planned": _field(6, "371.883.724", "Số lượng cổ phiếu dự kiến phát hành"),
            "stock_ratio": _field(6, "66,9%", "Tỷ lệ thực hiện quyền"),
            "shares_issued": _field(6, "371.862.185", "Tổng số cổ phiếu đã phân phối (đính chính)"),
            "fractional_shares_cancelled": _field(6, "21.447,03", "Số cổ phiếu xử lý phần lẻ"),
            "shares_after": _field(7, "928.158.191", "Tổng số cổ phiếu sau đợt phát hành"),
        }}],
    "2485374": [  # HOSE 1634/TB-SGDHCM, 30/07/2026: one ex-date, two legs
        {"event_type": "cash_dividend", "event_type_printed": "bằng tiền",
         "fields": {
             "ex_date": _field(1, "17/08/2026", "Ngày giao dịch không hưởng quyền"),
             "record_date": _field(1, "18/08/2026", "Ngày đăng ký cuối cùng"),
             "cash_amount_per_share": _field(1, "1.000", "01 cổ phiếu được nhận 1.000 đồng"),
             "payment_date": _field(1, "14/09/2026", "Ngày thanh toán"),
         }},
        {"event_type": "bonus_shares", "event_type_printed": "tăng vốn cổ phần từ nguồn vốn chủ sở hữu",
         # The page prints 500.219.550 planned shares, but both governed reads give
         # `500.²19.550`; an OCR token is never repaired, so the count is not cited.
         "warnings": ["shares_planned_unreadable_in_every_governed_ocr_read"],
         "fields": {
             "ex_date": _field(1, "17/08/2026", "Ngày giao dịch không hưởng quyền"),
             "record_date": _field(1, "18/08/2026", "Ngày đăng ký cuối cùng"),
             "stock_ratio": _field(1, "5:1", "Tỷ lệ thực hiện"),
         }}],
    "2430881": [{  # HOSE 72/TB-SGDHCM, 14/01/2026, citing QĐ 29/QĐ-SGDHCM of 09/01/2026
        "event_type": None, "event_type_printed": "trả cổ tức và tăng vốn cổ phần",
        "warnings": ["combined_stock_dividend_and_bonus_legs_not_separable_in_document"],
        "fields": {
            "shares_issued": _field(1, "444.949.496", "Số lượng chứng khoán thay đổi niêm yết (hai đợt gộp)"),
            "shares_after": _field(1, "2.786.821.096", "Số lượng chứng khoán sau khi thay đổi niêm yết"),
            "listing_effective_date": _field(1, "13/01/2026", "Ngày thay đổi niêm yết có hiệu lực"),
            "trading_date": _field(1, "27/01/2026", "Ngày giao dịch của chứng khoán thay đổi niêm yết"),
        }}],
}

#: The 29/07/2026 notice states that its enclosed revised report replaces the 28/07/2026 one.
#: Only the "total distributed" line changed; the superseded report contributes no observation.
SUPERSESSIONS = ({
    "superseded_hose_news_id": "2483453", "superseding_hose_news_id": "2484275",
    "superseded_token": _field(3, "371.883.632,03", "Tổng số cổ phiếu đã phân phối (bản 28/7/2026)"),
    "corrected_token": _field(1, "371.862.185", "Tổng số cổ phiếu đã phân phối (thông tin đính chính)"),
    "unchanged_token": _field(8, "371.862.185", "Số cổ phiếu thực tế phân phối (bản 28/7/2026, báo cáo kèm theo)"),
},)


def acquisition_specs() -> list[dict[str, str]]:
    # `published_at` is deliberately omitted: no publication clock is retained in these
    # bytes, and a portal posting time read elsewhere is not Producer evidence.
    return [{"ticker": row["ticker"], "document_class": row["document_class"], "reporting_period": "2026",
             "source_id": "hose", "source_authority": "exchange", "canonical_url": _STATIC + row["path"],
             "discovery_provenance": f"grokbot_issue_51_locator:hose_news_id={row['hose_news_id']}"}
            for row in ACQUISITION_REQUESTS]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _news_id(record: Mapping[str, Any]) -> str:
    return str(record["discovery_provenance"]).rsplit("=", 1)[1]


def _records() -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = {_news_id(row): row for row in manifest["records"]}
    if set(records) != {row["hose_news_id"] for row in ACQUISITION_REQUESTS}:
        raise ValueError("retained_manifest_does_not_match_request_set")
    return records


def materialize_ocr() -> dict[str, Any]:
    """Every page of every retained scan, once per fixed language configuration."""
    import fitz
    from annual_financial_ocr_materialization import render_and_ocr

    sidecar: dict[str, Any] = {"schema_version": "1.0.0", "render_dpi": OCR_DPI, "psm": 6,
                               "languages": list(OCR_LANGUAGES), "documents": {}}
    for news_id, record in sorted(_records().items()):
        page_count = len(fitz.open(RETENTION / record["relative_path"]))
        sidecar["documents"][record["document_id"]] = {
            language: render_and_ocr(record, root=RETENTION, pages=range(1, page_count + 1),
                                     language=language, psm=6, dpi=OCR_DPI)
            for language in OCR_LANGUAGES}
        print(f"ocr {news_id} {record['ticker']} pages={page_count}", flush=True)
    OCR_SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    OCR_SIDECAR.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar


def load_ocr_pages(sidecar: Mapping[str, Any], record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The verified sidecar rows of one document; identities are recomputed, never trusted."""
    rows: list[dict[str, Any]] = []
    for language in OCR_LANGUAGES:
        result = sidecar["documents"][record["document_id"]][language]
        if result["document_sha256"] != record["sha256"]:
            raise ValueError("ocr_sidecar_bound_to_other_bytes")
        for page in result["pages"]:
            if hashlib.sha256(str(page["text"]).encode()).hexdigest() != page["text_sha256"]:
                raise ValueError("ocr_text_hash_mismatch")
            replay_ocr([{key: page[key] for key in _SIDECAR_ROW_FIELDS if key in page}])
            rows.append(dict(page))
    return rows


def _document(record: Mapping[str, Any], document_type: str) -> dict[str, Any]:
    return {"document_id": record["document_id"], "ticker": record["ticker"], "document_type": document_type,
            "content_sha256": record["sha256"], "source_id": record["source_id"],
            "source_authority": record["source_authority"], "source_url": record["canonical_url"],
            "observed_at": record["observed_at"], "published_at": None,
            "discovery_provenance": record["discovery_provenance"]}


def resolve_knowledge(records_by_document: Mapping[str, Mapping[str, Any]]):
    """Knowledge cutoff of a ledger entry: the latest Producer receipt among its documents.

    No retained byte carries a publication clock, so each document resolves to its own first
    observation (forward-only); the entry is knowable once every document it rests on is. The
    factor-chain cutoff is an instant. The research session that instant falls in is resolved
    only against the governed calendar (`config/governed_trading_session_calendar_v1.json`);
    when the calendar does not reach it, the session stays unresolved and says so.
    """
    def resolver(entry: Mapping[str, Any]) -> tuple[str | None, list[str]]:
        projections = [project_official_evidence_temporal_metadata({
            "document_id": doc_id, "sha256": records_by_document[doc_id]["sha256"], "source_authority": "exchange",
            "published_at": None, "observed_at": records_by_document[doc_id]["observed_at"],
            "qualification_state": "QUALIFIED"}, governed_sessions=GOVERNED_SESSIONS)["knowledge_resolution"]
            for doc_id in entry["source_document_ids"]]
        reasons = sorted({str(item["knowledge_time_status"]) for item in projections}
                         | {str(item["historical_reconstruction_scope"]) for item in projections}
                         | {str(warning) for item in projections for warning in item.get("warnings") or ()})
        instants = [item.get("knowledge_available_at") for item in projections]
        if not instants or any(not value for value in instants) or any(
                item["knowledge_time_status"] == "KNOWLEDGE_UNKNOWN" for item in projections):
            return None, reasons
        derived = propagate_derived_knowledge(required_inputs=projections).to_dict()
        if derived["knowledge_time_status"] == "KNOWLEDGE_UNKNOWN":
            reasons.append("knowledge_research_session_unresolved_outside_governed_calendar")
        return max(instants, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))), sorted(set(reasons))
    return resolver


def _verify_retained(records: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    documents = []
    for news_id, record in sorted(records.items()):
        if sha256_file(RETENTION / record["relative_path"]) != record["sha256"]:
            raise ValueError(f"retained_document_hash_mismatch:{news_id}")
        retention = record["temporal_retention"]
        documents.append({
            "hose_news_id": news_id, "ticker": record["ticker"], "document_class": record["document_class"],
            "document_id": record["document_id"], "canonical_url": record["canonical_url"],
            "sha256": record["sha256"], "content_length": record["content_length"],
            "extraction_status": record["extraction_status"], "producer_receipt_at": record["observed_at"],
            "http_last_modified": retention.get("http_last_modified"),
            "http_last_modified_role": "SERVER_FILE_CLOCK_NOT_PUBLICATION_OR_KNOWLEDGE_TIME",
            "grokbot_51_sha256_agreement": (None if news_id not in GROKBOT_51_SHA256
                                            else GROKBOT_51_SHA256[news_id] == record["sha256"]),
        })
    return documents


def load_sidecar() -> dict[str, Any]:
    return json.loads(OCR_SIDECAR.read_text(encoding="utf-8"))


def build_observations(sidecar: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]] | None = None,
                       reviews: Mapping[str, list[Mapping[str, Any]]] = REVIEWS) -> list[dict[str, Any]]:
    """Reviewed observations from the tracked manifest and sidecar; needs no PDF bytes."""
    records = records if records is not None else _records()
    observations: list[dict[str, Any]] = []
    for news_id, rows in sorted(reviews.items()):
        record = records[news_id]
        pages = load_ocr_pages(sidecar, record)
        for review in rows:
            observations.append(reviewed_scan_observation(_document(record, record["document_class"]), review, pages))
    return observations


def knowledge_resolver():
    return resolve_knowledge({record["document_id"]: record for record in _records().values()})


def build_artifact(sidecar: Mapping[str, Any] | None = None) -> dict[str, Any]:
    records = _records()
    documents = _verify_retained(records)
    sidecar = sidecar if sidecar is not None else load_sidecar()
    by_document = {record["document_id"]: record for record in records.values()}
    observations = build_observations(sidecar, records)

    supersessions = []
    for row in SUPERSESSIONS:
        old, new = records[row["superseded_hose_news_id"]], records[row["superseding_hose_news_id"]]
        old_pages, new_pages = load_ocr_pages(sidecar, old), load_ocr_pages(sidecar, new)
        for token, pages in ((row["superseded_token"], old_pages), (row["unchanged_token"], old_pages),
                             (row["corrected_token"], new_pages)):
            if not any(token["printed"] in r["text"] for r in pages if int(r["page"]) == token["page"]):
                raise ValueError("supersession_token_absent_from_governed_ocr")
        supersessions.append({"superseded_document_id": old["document_id"], "superseding_document_id": new["document_id"],
                              **{key: row[key] for key in ("superseded_token", "corrected_token", "unchanged_token")},
                              "effect": "superseded report excluded from observations; executed count unchanged"})

    ledger = build_ledger(observations)
    cohort = build_factor_chain_cohort(ledger, knowledge_cutoff_resolver=resolve_knowledge(by_document))
    unlinked = {row["observation_id"]: row for row in ledger["unlinked_observations"]}
    outcomes = {}
    for event in cohort["events"]:
        chain = event["factor_chain"]
        entry = next(e for e in ledger["entries"] if e["event_id"] == event["event_id"])
        outcomes[f"{event['ticker']}:{event['event_type']}:{entry.get('ex_date') or 'NO_EX_DATE'}:{entry['event_id'][:12]}"] = {
            "classification": event["classification"], "status": chain["status"],
            "ex_date": chain["ex_date"], "record_date": chain["record_date"],
            "adjustment_factor": chain["adjustment_factor"], "knowledge_cutoff": chain["knowledge_cutoff"],
            "reason_codes": chain["reason_codes"], "source_document_ids": chain["source_document_ids"],
            "historical_pit_eligible_on_or_before_ex_date": False,
            "known_from": "PRODUCER_RECEIPT_FORWARD_ONLY" if chain["knowledge_cutoff"] else None,
        }
    for observation in observations:
        if observation["observation_id"] in unlinked:
            outcomes[f"{observation['ticker']}:{observation['event_type'] or 'COMBINED_LEGS'}:"
                     f"{observation.get('ex_date') or 'NO_EX_DATE'}:{observation['observation_id'][:12]}"] = {
                "classification": "NOT_A_LEDGER_ENTRY", "status": "NOT_QUALIFIED",
                "ledger_reason": unlinked[observation["observation_id"]]["reason"],
                "lifecycle_state": observation["lifecycle_state"],
                "ex_date": observation.get("ex_date"), "record_date": observation.get("record_date"),
                "cash_amount_per_share": observation.get("cash_amount_per_share"),
                "reason_codes": sorted(["no_share_change_identity_for_ledger_link"]
                                       + ([] if observation.get("ex_date") else ["missing_explicit_official_ex_date"])
                                       + list(observation["warnings"])),
            }
    qualified = cohort["qualified_count"]
    return {
        "contract_version": "official_ca_hose_ex_date_qualification/v1",
        "milestone": "OFFICIAL_CORPORATE_ACTION_EVENT_EVIDENCE_PIT_BLOCKER_CLOSURE",
        "scope": {"tickers": ["HPG", "PVD", "SSI", "POW"], "source": "hose", "documents": len(records),
                  "lead_source": "ai-agent-inbox#51 bbc153fb42adbd9294125eac5e236a16f927ac0c (leads only)"},
        "authority_boundary": {
            "offline_scope_factor_chain_qualified_count": qualified,
            "knowledge_basis": "PRODUCER_RECEIPT_2026_10_25_FORWARD_ONLY",
            "historical_pit_eligible": False, "pit_backtest_eligible": False, "execution_replay_eligible": False,
            "active_universe": "UNKNOWN", "applicable_corporate_action_coverage": "UNKNOWN",
            "event_free_interval_proven": False, "observed_market_ratio_used_as_factor": False,
            "cash_adjustment_policy": "NONE", "authority_promotion": False,
            "authority_state": ledger["authority_state"],
        },
        "documents": documents,
        "ocr_sidecar": {"path": OCR_SIDECAR.relative_to(ROOT).as_posix(), "languages": list(OCR_LANGUAGES),
                        "render_dpi": OCR_DPI, "sha256": hashlib.sha256(_canonical(sidecar).encode("utf-8")).hexdigest()},
        "observations": observations,
        "supersessions": supersessions,
        "ledger": ledger,
        "factor_chain_cohort": cohort,
        "event_outcomes": dict(sorted(outcomes.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true", help="retain the finite HOSE originals (network)")
    parser.add_argument("--ocr", action="store_true", help="materialize the governed OCR sidecar (local Tesseract)")
    args = parser.parse_args(argv)
    if args.acquire:
        print(json.dumps(acquire(acquisition_specs(), RETENTION), ensure_ascii=False, indent=2))
        return 0
    if args.ocr:
        materialize_ocr()
        return 0
    artifact = build_artifact()
    artifact["artifact_sha256"] = hashlib.sha256(_canonical(artifact).encode("utf-8")).hexdigest()
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(json.dumps({key: value["classification"] for key, value in artifact["event_outcomes"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
