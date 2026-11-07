"""Scoped Q3/2026 successor. It does not open the currency-refresh contract.

``financial_evidence_currency_refresh/v1`` still admits only FY2025 and
2026-H1/2026-Q2. Issuer IR still has no unreviewed-quarterly document type, so
this module does not call ``admit()`` and does not write the official document
store. A retained PDF can become a shadow research row only when an admitted
host served it, the text layer is not source-faithful (amounts are not
repaired), and the income identities cross-foot. ``official_fact_admitted``
stays false. Nine-month figures stay on their own period label.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from stocklookup_core.financial.q3_2026_research_freshness import classify_document

CONTRACT_VERSION = "q3_2026_successor_research/v1"
HPG_HOSTS = frozenset({"file.hoaphat.com.vn", "www.hoaphat.com.vn", "hoaphat.com.vn"})
HPG_CONSOLIDATED_Q3_URL = (
    "https://file.hoaphat.com.vn/hoaphat-com-vn/2026/11/bao-cao-tai-chinh-hop-nhat-quy-iii-2026.pdf"
)
HPG_CONSOLIDATED_Q3_SHA256 = "22a4061c9816d11121816377ea78ae99cf68928a75aa8bdcb15e7ded1bbf5ec9"
HPG_CONSOLIDATED_Q3_BYTES = 7200670
# One mixed token from the pypdf extract of PDF page 6. It is evidence that the
# text layer remaps digits. It is not an amount and it is not repaired.
HPG_TEXT_LAYER_SNIPPET = "62.214.t87.236.97 6"
FOOT_CODES = ("01", "02", "10", "11", "20", "50", "51", "52", "60", "61", "62")
DISPLAY_METRICS = {"10": "revenue", "60": "net_income", "61": "attributable_net_income"}
_AMOUNTISH = re.compile(r"[0-9A-Za-z][0-9A-Za-z.]{4,}")

# Visual read of PDF page 6 (printed page 5), Mẫu B 02-DN/HN, consolidated,
# signed by management on 29 October 2026. Not a byte-native span.
HPG_Q3_2026_LINES = {
    "01": 62669083327239, "02": 454896090263, "10": 62214187236976,
    "11": 50291718592341, "20": 11922468644635, "50": 9108749304090,
    "51": 822816533926, "52": 20472307198, "60": 8265460462966,
    "61": 8217339610974, "62": 48120851992,
}
HPG_9M_2026_LINES = {
    "01": 171539239621771, "02": 1265302783241, "10": 170273936838530,
    "11": 139498612392469, "20": 30775324446061, "50": 27055617351061,
    "51": 3409198027423, "52": -99433606445, "60": 23745852930083,
    "61": 23582361859679, "62": 163491070404,
}


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def text_layer_fidelity(page_text: str) -> dict[str, Any]:
    """A mixed digit/letter amount token means the encoding is not source-faithful.

    The token is reported as a count only. This function never rewrites it into
    a number.
    """
    tokens = _AMOUNTISH.findall(page_text or "")
    mixed = [token for token in tokens if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token)]
    return {
        "faithful": not mixed and bool((page_text or "").strip()),
        "examined": bool((page_text or "").strip()),
        "mixed_token_count": len(mixed),
        "reason_codes": [] if not mixed and (page_text or "").strip() else (
            ["TEXT_LAYER_NOT_EXAMINED"] if not (page_text or "").strip()
            else ["TEXT_LAYER_NOT_SOURCE_FAITHFUL_NO_REPAIR"]
        ),
    }


def income_cross_foot(lines: Mapping[str, int]) -> list[str]:
    """Check the printed income identities. A failure blocks the shadow row."""
    if any(code not in lines or type(lines[code]) is not int for code in FOOT_CODES):
        return ["INCOME_CROSS_FOOT_INPUT_INCOMPLETE"]
    reasons = []
    if lines["10"] != lines["01"] - lines["02"]:
        reasons.append("LINE_10_DOES_NOT_FOOT_01_MINUS_02")
    if lines["20"] != lines["10"] - lines["11"]:
        reasons.append("LINE_20_DOES_NOT_FOOT_10_MINUS_11")
    if lines["60"] != lines["50"] - lines["51"] - lines["52"]:
        reasons.append("LINE_60_DOES_NOT_FOOT_50_MINUS_51_MINUS_52")
    if lines["60"] != lines["61"] + lines["62"]:
        reasons.append("LINE_60_DOES_NOT_FOOT_61_PLUS_62")
    return reasons


def source_receipt(*, ticker: str, source_url: str, pdf_bytes: bytes, observed_at: str) -> dict[str, Any]:
    """Record one download without adopting it into the official store."""
    parsed = urlsplit(source_url or "")
    host = (parsed.hostname or "").lower()
    pdf = bytes(pdf_bytes or b"")
    reasons = [
        "OUT_OF_FINANCIAL_EVIDENCE_CURRENCY_REFRESH_SCOPE",
        "UNREVIEWED_QUARTERLY_DOCUMENT_TYPE_NOT_DECLARED_FOR_ISSUER_IR",
    ]
    if str(ticker or "").upper() != "HPG" or host not in HPG_HOSTS:
        reasons.append("NO_ADMITTED_HOST_FOR_THIS_STATEMENT")
    if not pdf.startswith(b"%PDF"):
        reasons.append("NOT_A_PDF")
    if not observed_at:
        reasons.append("OBSERVED_AT_MISSING")
    retained = not any(code in reasons for code in (
        "NO_ADMITTED_HOST_FOR_THIS_STATEMENT", "NOT_A_PDF", "OBSERVED_AT_MISSING"))
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": str(ticker or "").upper(),
        "source_url": source_url,
        "host": host,
        "sha256": _sha(pdf) if pdf else None,
        "byte_length": len(pdf),
        "observed_at": observed_at or None,
        "knowledge_available_at": observed_at or None,
        "official_store_adoption": "REFUSED",
        "official_fact_admitted": False,
        "retained_shadow": retained,
        "reason_codes": reasons,
    }


def bind_retained_hpg_statement(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the receipt only to the one consolidated PDF located on the IR index."""
    matched = (
        receipt.get("retained_shadow") is True
        and receipt.get("ticker") == "HPG"
        and receipt.get("source_url") == HPG_CONSOLIDATED_Q3_URL
        and receipt.get("sha256") == HPG_CONSOLIDATED_Q3_SHA256
        and receipt.get("byte_length") == HPG_CONSOLIDATED_Q3_BYTES
    )
    return {
        "status": "BOUND" if matched else "NOT_BOUND",
        "reason_codes": [] if matched else ["NOT_THE_RETAINED_HPG_CONSOLIDATED_Q3_STATEMENT"],
        "sha256": HPG_CONSOLIDATED_Q3_SHA256 if matched else None,
    }


def visual_income_shadow(
    *,
    receipt: Mapping[str, Any],
    page_text: str,
    lines: Mapping[str, int],
    period_kind: str,
    period_label: str,
    pdf_page: int,
) -> dict[str, Any]:
    """One column of one statement. Official admission stays closed."""
    binding = bind_retained_hpg_statement(receipt)
    fidelity = text_layer_fidelity(page_text)
    foot = income_cross_foot(lines)
    classification = classify_document(document_kind=period_kind, period_label=period_label)
    reasons = list(classification["reason_codes"]) + list(binding["reason_codes"]) + list(fidelity["reason_codes"]) + foot
    nine_month_as_quarter = period_kind == "NINE_MONTH_CUMULATIVE" and str(period_label).endswith("-Q3")
    quarter_as_nine_month = period_kind == "Q3_STANDALONE_UNREVIEWED" and str(period_label).endswith("-9M")
    if nine_month_as_quarter or quarter_as_nine_month:
        reasons.append("PERIOD_KIND_DOES_NOT_MATCH_PERIOD_LABEL")
    if fidelity.get("faithful"):
        reasons.append("FAITHFUL_TEXT_REQUIRES_THE_ROW_MATCHER_NOT_A_VISUAL_SHADOW")
    display = []
    allowed = (
        binding["status"] == "BOUND"
        and not foot
        and not fidelity.get("faithful")
        and fidelity.get("examined")
        and not nine_month_as_quarter
        and not quarter_as_nine_month
        and period_kind in {"Q3_STANDALONE_UNREVIEWED", "NINE_MONTH_CUMULATIVE"}
        and pdf_page == 6
    )
    if allowed:
        for code, metric in DISPLAY_METRICS.items():
            display.append({
                "line_code": code,
                "canonical_metric": metric,
                "value_vnd": lines[code],
                "currency": "VND",
                "unit_scale": 1,
                "reporting_period": period_label,
                "period_kind": period_kind,
                "statement_scope": "consolidated",
                "audit_or_review_status": "unreviewed",
                "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE",
                "pdf_page": pdf_page,
                "official_fact_admitted": False,
                "valuation_use": "CLOSED",
                "existing_consumer_usable": False,
            })
    else:
        reasons.append("SHADOW_ROW_NOT_EMITTED")
    return {
        "contract_version": CONTRACT_VERSION,
        "classification": classification,
        "text_layer": fidelity,
        "cross_foot_reason_codes": foot,
        "official_fact_admitted": False,
        "valuation_use": "CLOSED",
        "candidate_only": True,
        "session_binding": "NOT_A_SEALED_SESSION_FACT",
        "nine_month_promoted_to_standalone_quarter": False,
        "shadow_rows": display,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def hpg_consolidated_statement_shadow(*, observed_at: str) -> dict[str, Any]:
    """The one retained HPG consolidated Q3/2026 chain, both period columns."""
    receipt = {
        "contract_version": CONTRACT_VERSION,
        "ticker": "HPG",
        "source_url": HPG_CONSOLIDATED_Q3_URL,
        "host": "file.hoaphat.com.vn",
        "sha256": HPG_CONSOLIDATED_Q3_SHA256,
        "byte_length": HPG_CONSOLIDATED_Q3_BYTES,
        "observed_at": observed_at,
        "knowledge_available_at": observed_at,
        "official_store_adoption": "REFUSED",
        "official_fact_admitted": False,
        "retained_shadow": True,
        "retention_note": "BYTES_RETAINED_OUTSIDE_GIT_SHA256_MEASURED",
        "reason_codes": [
            "OUT_OF_FINANCIAL_EVIDENCE_CURRENCY_REFRESH_SCOPE",
            "UNREVIEWED_QUARTERLY_DOCUMENT_TYPE_NOT_DECLARED_FOR_ISSUER_IR",
        ],
    }
    q3 = visual_income_shadow(
        receipt=receipt, page_text=HPG_TEXT_LAYER_SNIPPET, lines=HPG_Q3_2026_LINES,
        period_kind="Q3_STANDALONE_UNREVIEWED", period_label="2026-Q3", pdf_page=6,
    )
    nine = visual_income_shadow(
        receipt=receipt, page_text=HPG_TEXT_LAYER_SNIPPET, lines=HPG_9M_2026_LINES,
        period_kind="NINE_MONTH_CUMULATIVE", period_label="2026-9M", pdf_page=6,
    )
    rows = q3["shadow_rows"] + nine["shadow_rows"]
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": "HPG",
        "source_url": HPG_CONSOLIDATED_Q3_URL,
        "host": "file.hoaphat.com.vn",
        "sha256": HPG_CONSOLIDATED_Q3_SHA256,
        "byte_length": HPG_CONSOLIDATED_Q3_BYTES,
        "knowledge_available_at": observed_at,
        "document_date_printed": "2026-10-29",
        "publication_date": None,
        "statement_scope": "consolidated",
        "form": "B02-DN/HN",
        "assurance": "unreviewed_management_signed_no_review_report_in_front_matter",
        "pdf_page": 6,
        "printed_page": 5,
        "official_store_adoption": "REFUSED",
        "official_fact_admitted": False,
        "official_fact_admitted_count": 0,
        "valuation_use": "CLOSED",
        "existing_consumer_usable": False,
        "session_binding": "NOT_A_SEALED_SESSION_FACT",
        "press_release_used_as_statement": False,
        "parent_pdf_not_fetched": "https://file.hoaphat.com.vn/hoaphat-com-vn/2026/10/20261029-hpg-bctc-cong-ty-me-quy-3-2026-va-giai-trinh.pdf",
        "columns": {"2026-Q3": q3, "2026-9M": nine},
        "shadow_row_count": len(rows),
        "shadow_rows": rows,
    }


def issuer_blocker(*, ticker: str, reason_codes: list[str]) -> dict[str, Any]:
    if not reason_codes:
        raise ValueError("BLOCKER_REQUIRES_A_REASON")
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker,
        "status": "BLOCKED",
        "official_fact_admitted": False,
        "valuation_use": "CLOSED",
        "exact_statement_url": None,
        "reason_codes": list(reason_codes),
    }


# Exact visual review of HOSE PDF page 8, in FOOT_CODES order.
PAN_INCOME_COLUMNS = {
    "2026-Q3": (
        4111272326123, 53769711450, 4057502614673, 3302330076444, 755172538229,
        340839371347, 5258066320, -155310834, 335736615861, 195756189127, 139980426734,
    ),
    "2025-Q3": (
        5212102498828, 74001160129, 5138101338699, 4122954757832, 1015146580867,
        304850710456, 41579736668, -3107923193, 266378896981, 156192900845, 110185996136,
    ),
    "2026-9M": (
        11694900115257, 256760945596, 11438139169661, 9170431501769, 2267707667892,
        1483766186014, 108997134749, 11249172231, 1363519879034, 963087575991, 400432303042,
    ),
}
PAN_Q3_URL = (
    "https://staticfile.hsx.vn/Uploads/UploadDocuments/2508740/"
    "20261027%20-%20PAN%20-%20BCTC%20Hop%20nhat%20Q3%202026%20kem%20giai%20trinh%20%28signed%29.pdf"
)
PAN_Q3_SHA256 = "d7e1422fcda668eb640abbdc73f1194380241e81c6ed9d33a5ef6e3ead0366b1"


def pan_consolidated_statement_shadow(*, pdf_bytes: bytes) -> dict[str, Any]:
    """Materialize display-only observations for the exact visually reviewed filing."""
    if _sha(pdf_bytes) != PAN_Q3_SHA256:
        raise ValueError("PAN_RETAINED_PDF_DOES_NOT_MATCH")

    rows = []
    rejected_columns = {}
    for period, values in PAN_INCOME_COLUMNS.items():
        lines = dict(zip(FOOT_CODES, values, strict=True))
        reasons = income_cross_foot(lines)
        if reasons:
            rejected_columns[period] = reasons
            continue
        for code, metric in DISPLAY_METRICS.items():
            rows.append({
                "metric": metric, "period": period, "value": lines[code],
                "unit": "VND", "pdf_page": 8, "line_code": code,
            })

    point_in_time = "2026-09-30"
    for metric, period, value, unit, page in (
        ("total_equity", point_in_time, 9414380321367, "VND", 7),
        ("noncontrolling_interest", point_in_time, 3855460149352, "VND", 7),
        ("issued_shares", point_in_time, 258072996, "shares", 34),
        ("treasury_shares", point_in_time, 7399830, "shares", 34),
        ("outstanding_shares", point_in_time, 250673166, "shares", 34),
        ("net_inventory", point_in_time, 4331055601966, "VND", 26),
        ("net_inventory", "2025-12-31", 3179033807421, "VND", 26),
        ("operating_cash_flow", "2026-9M", -619520988619, "VND", 9),
        ("receivables_cash_movement", "2026-9M", -2803360221257, "VND", 9),
        ("inventory_cash_movement", "2026-9M", -1099450415124, "VND", 9),
        ("pretax_disposal_gain", "2026-9M", 561507166021, "VND", 36),
    ):
        rows.append({"metric": metric, "period": period, "value": value, "unit": unit, "pdf_page": page})

    amounts = {(row["metric"], row["period"]): row["value"] for row in rows}
    equity = amounts["total_equity", point_in_time] - amounts["noncontrolling_interest", point_in_time]
    shares = amounts["outstanding_shares", point_in_time]
    if amounts["issued_shares", point_in_time] - amounts["treasury_shares", point_in_time] != shares:
        raise ValueError("PAN_SHARE_NOTE_DOES_NOT_RECONCILE")
    price = 16900
    return {
        "ticker": "PAN",
        "source_url": PAN_Q3_URL,
        "sha256": PAN_Q3_SHA256,
        "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE",
        "source_role": "EXCHANGE_HOSTED_ISSUER_DISCLOSURE_ATTACHMENT",
        "issuer_disclosure_date": "2026-10-27",
        "publication_precision": "DATE_ONLY",
        "retained_at": "2026-11-07T09:01:04Z",
        "audit_or_review_status": "unreviewed",
        "statement_scope": "consolidated",
        "session_binding": "NOT_A_SEALED_SESSION_FACT",
        "official_fact_admitted": False,
        "valuation_use": "CLOSED",
        "existing_consumer_usable": False,
        "observations": rows,
        "rejected_income_columns": rejected_columns,
        "revenue_yoy_pct": round(100 * (amounts["revenue", "2026-Q3"] / amounts["revenue", "2025-Q3"] - 1), 2),
        "parent_profit_yoy_pct": round(100 * (
            amounts["attributable_net_income", "2026-Q3"] / amounts["attributable_net_income", "2025-Q3"] - 1
        ), 2),
        "common_shareholder_pb": "UNAVAILABLE",
        "book_sensitivity": {
            "kind": "CROSS_DATE_ILLUSTRATION",
            "book_date": point_in_time,
            "reference_price_session": "2026-11-06",
            "reference_price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
            "reference_price_source": "decision:PAN:5339b11b31869af6",
            "reference_price_vnd": price,
            "quarter_end_shares": shares,
            "derived_equity_excluding_nci_vnd": equity,
            "illustrative_multiple": price * shares / equity,
            "reason_codes": [
                "RECONCILED_PARENT_EQUITY_METHOD_NOT_ADMITTED",
                "SHARE_CONTINUITY_THROUGH_PRICE_SESSION_UNPROVEN",
                "RAW_PRICE_BASIS_NOT_BOUND",
            ],
        },
    }


# Printed cash-flow codes. Line 16 is absent on this statement and is not invented.
_OCF_ADJUSTMENT = ("1", "2", "3", "04", "05", "6", "7")
_OCF_BRIDGE = ("8", "09", "10", "11", "12", "13", "14", "15", "17")


def operating_cash_flow_cross_foot(lines: Mapping[str, int]) -> list[str]:
    """Reconcile indirect operating cash flow without using an income-statement column."""
    needed = (*_OCF_ADJUSTMENT, *_OCF_BRIDGE, "20")
    if any(code not in lines or type(lines[code]) is not int for code in needed):
        return ["OPERATING_CASH_FLOW_CROSS_FOOT_INPUT_INCOMPLETE"]
    reasons = []
    if lines["8"] != sum(lines[code] for code in _OCF_ADJUSTMENT):
        reasons.append("LINE_08_DOES_NOT_FOOT_ADJUSTMENTS")
    if lines["20"] != sum(lines[code] for code in _OCF_BRIDGE):
        reasons.append("LINE_20_DOES_NOT_FOOT_OPERATING_BRIDGE")
    return reasons


POW_Q3_URL = (
    "https://staticfile.hsx.vn/Uploads/UploadDocuments/2510748/"
    "20261030%20-%20POW%20-%20BCTC%20HN%20Q3.2026.pdf"
)
POW_Q3_SHA256 = "c423af37737c4fb9ec1df98ff7b0145488f103a9667db5215aacd848ac12bcfb"
# Visual read of PDF page 8, Mẫu B 02-DN/HN. FOOT_CODES order. The text layer is not used.
POW_INCOME_COLUMNS = {
    "2026-Q3": (
        16772209338395, 35309657, 16772174028738, 14460963526725, 2311210502013,
        2414031200864, 264579538441, 76335415657, 2073116246766, 1859571515433, 213544731334,
    ),
    "2025-Q3": (
        7855188738891, 0, 7855188738891, 6564435636945, 1290753101946,
        1011826163428, 63448641579, 0, 948377521849, 809300749571, 139076772278,
    ),
    "2026-9M": (
        49405538196735, 35309657, 49405502887078, 40704201296076, 8701301591002,
        7743502646042, 768090471308, 76846458593, 6898565716142, 6434493112525, 464072603617,
    ),
    "2025-9M": (
        25404267937149, 0, 25404267937149, 22129728253869, 3274539683280,
        2332117178740, 154529139499, -4385813849, 2181973853090, 1856808001611, 325165851479,
    ),
}
# Visual read of PDF page 10, Mẫu B 03-DN/HN, indirect method. Nine-month columns only.
POW_OCF_COLUMNS = {
    "2026-9M": {
        "1": 7743502646042, "2": 2914951688624, "3": -187835162208, "04": -91338511310,
        "05": -1106693891039, "6": 1569009965027, "7": 0, "8": 10841596735136,
        "09": -10695294079903, "10": -516740475711, "11": 4485469971400, "12": 60934634228,
        "13": 0, "14": -685789088103, "15": -527074441481, "17": -224122149460,
        "20": 2738981106106,
    },
    "2025-9M": {
        "1": 2332117178740, "2": 2133062844670, "3": 336710508500, "04": 266135429886,
        "05": -635500696480, "6": 411031425707, "7": 0, "8": 4843556691023,
        "09": 1453805734294, "10": -469338827413, "11": -2905408694950, "12": 1177734207429,
        "13": 0, "14": -380417324190, "15": -125156592660, "17": -180544591090,
        "20": 3414230602443,
    },
}


def pow_reviewed_page_research() -> dict[str, Any]:
    """Rows read from the retained POW pages. Callers still have to match the PDF SHA."""
    rows = []
    rejected_columns = {}
    for period, values in POW_INCOME_COLUMNS.items():
        lines = dict(zip(FOOT_CODES, values, strict=True))
        reasons = income_cross_foot(lines)
        if reasons:
            rejected_columns[period] = reasons
            continue
        for code, metric in DISPLAY_METRICS.items():
            rows.append({
                "metric": metric, "period": period, "value": lines[code],
                "unit": "VND", "pdf_page": 8, "line_code": code,
            })

    for period, lines in POW_OCF_COLUMNS.items():
        reasons = operating_cash_flow_cross_foot(lines)
        if reasons:
            rejected_columns[period + ":operating_cash_flow"] = reasons
            continue
        rows.append({
            "metric": "operating_cash_flow", "period": period, "value": lines["20"],
            "unit": "VND", "pdf_page": 10, "line_code": "20",
        })

    amounts = {(row["metric"], row["period"]): row["value"] for row in rows}
    current_ocf = amounts.get(("operating_cash_flow", "2026-9M"))
    prior_ocf = amounts.get(("operating_cash_flow", "2025-9M"))
    ocf_yoy = None
    if isinstance(current_ocf, int) and isinstance(prior_ocf, int) and prior_ocf:
        ocf_yoy = round(100 * (current_ocf / prior_ocf - 1), 2)
    return {
        "ticker": "POW",
        "source_url": POW_Q3_URL,
        "sha256": POW_Q3_SHA256,
        "research_kind": "COMPARATIVE_INCOME_AND_OPERATING_CASH_FLOW",
        "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE",
        "source_role": "EXCHANGE_HOSTED_ISSUER_DISCLOSURE_ATTACHMENT",
        "issuer_disclosure_date": "2026-10-30",
        "publication_precision": "DATE_ONLY",
        "document_signature_time": "2026-10-30T16:40:59+07:00",
        "retention": "LOCAL_PDF_SHA256_MATCHES_CODEX_CLOSEOUT_RECEIPT",
        "audit_or_review_status": "unreviewed",
        "statement_scope": "consolidated",
        "unit": "VND",
        "income_form": "B02-DN/HN",
        "cash_flow_form": "B03-DN/HN",
        "cash_flow_method": "INDIRECT",
        "period_start_printed": "2026-01-01",
        "period_end": "2026-09-30",
        "session_binding": "NOT_A_SEALED_SESSION_FACT",
        "official_fact_admitted": False,
        "official_store_adoption": "REFUSED",
        "valuation_use": "CLOSED",
        "common_shareholder_pb": "UNAVAILABLE",
        "existing_consumer_usable": False,
        "text_layer": "NOT_SOURCE_FAITHFUL_NO_REPAIR",
        "observations": rows,
        "rejected_income_columns": rejected_columns,
        "operating_cash_flow_yoy_pct": ocf_yoy,
        "loan_and_lease_lines_excluded": ["321", "339"],
    }


EVF_Q3_SHA256 = "ace221dd37e1fd6e3036d6d5df431a43902246903b96a88b6a626dfcdf4b8475"
EVF_Q3_URL = (
    "https://www.evnfc.vn/storage/app/media/anh_ban_lanh_dao/"
    "20261026%20-%20EVF%20-%20Bao%20cao%20tai%20chinh%20Q3%202026%20soat%20xet%201.pdf"
)
EVF_DISCLOSURE_URL = "https://www.evnfc.vn/index.php/tin-co-dong/reviewed-financial-statements-q3-2026"
EVF_INCOME_LINES = (
    "interest_income", "interest_expense", "net_interest_income", "pre_provision_profit",
    "credit_loss_provision", "pretax_profit", "tax", "net_income",
)
# Visual read of PDF page 11 (printed page 10), million VND. Nine-month columns only.
EVF_INCOME_COLUMNS = {
    "2026-9M": {
        "interest_income": 5839452, "interest_expense": 4126903, "net_interest_income": 1712549,
        "pre_provision_profit": 1469579, "credit_loss_provision": 433809,
        "pretax_profit": 1035770, "tax": 200431, "net_income": 835339,
    },
    "2025-9M": {
        "interest_income": 4026565, "interest_expense": 2593169, "net_interest_income": 1433396,
        "pre_provision_profit": 1546421, "credit_loss_provision": 641834,
        "pretax_profit": 904587, "tax": 168374, "net_income": 736213,
    },
}


def finance_company_income_cross_foot(lines: Mapping[str, int]) -> list[str]:
    """Check the reviewed finance-company identities. This is not an industrial income statement."""
    if any(code not in lines or type(lines[code]) is not int for code in EVF_INCOME_LINES):
        return ["FINANCE_COMPANY_INCOME_CROSS_FOOT_INPUT_INCOMPLETE"]
    reasons = []
    if lines["net_interest_income"] != lines["interest_income"] - lines["interest_expense"]:
        reasons.append("NET_INTEREST_DOES_NOT_FOOT")
    if lines["pretax_profit"] != lines["pre_provision_profit"] - lines["credit_loss_provision"]:
        reasons.append("PRETAX_DOES_NOT_FOOT_PRE_PROVISION_MINUS_CREDIT_PROVISION")
    if lines["net_income"] != lines["pretax_profit"] - lines["tax"]:
        reasons.append("NET_INCOME_DOES_NOT_FOOT_PRETAX_MINUS_TAX")
    return reasons


def evf_reviewed_page_research() -> dict[str, Any]:
    """Nine-month reviewed rows. There is no standalone third-quarter column on the page."""
    rows = []
    rejected_columns = {}
    for period, lines in EVF_INCOME_COLUMNS.items():
        reasons = finance_company_income_cross_foot(lines)
        if reasons:
            rejected_columns[period] = reasons
            continue
        for metric in EVF_INCOME_LINES:
            rows.append({
                "metric": metric, "period": period, "value": lines[metric],
                "unit": "MILLION_VND", "pdf_page": 11,
            })
    amounts = {(row["metric"], row["period"]): row["value"] for row in rows}

    def _yoy(metric: str):
        current = amounts.get((metric, "2026-9M"))
        prior = amounts.get((metric, "2025-9M"))
        if not isinstance(current, int) or not isinstance(prior, int) or not prior:
            return None
        return round(100 * (current / prior - 1), 2)

    return {
        "ticker": "EVF",
        "source_url": EVF_Q3_URL,
        "disclosure_url": EVF_DISCLOSURE_URL,
        "sha256": EVF_Q3_SHA256,
        "research_kind": "REVIEWED_NINE_MONTH_FINANCE_COMPANY",
        "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE",
        "source_role": "ISSUER_SITE_DISCLOSURE_PDF_HOST_NOT_AN_APPROVED_OFFICIAL_ROUTE",
        "entity_class": "finance_company",
        "commercial_bank": False,
        "issuer_disclosure_date": "2026-10-26",
        "publication_precision": "DATE_ONLY",
        "statement_signed_date": "2026-10-22",
        "reviewer": "A&C Auditing and Consulting Co., Ltd.",
        "review_report_number": "2.0010/27/TC-AC",
        "review_standard": "VSA_2410",
        "review_pdf_page": 6,
        "audit_or_review_status": "reviewed",
        "review_scope": "POSITION_AT_2026-09-30_AND_NINE_MONTHS_ENDED_THAT_DATE",
        "standalone_quarter_column": False,
        "statement_scope": "separate",
        "statement_scope_basis": "COVER_AND_INCOME_TITLE_DO_NOT_SAY_CONSOLIDATED",
        "unit": "MILLION_VND",
        "income_form": "B03a/TCTD",
        "period_start_printed": "2026-01-01",
        "period_end": "2026-09-30",
        "session_binding": "NOT_A_SEALED_SESSION_FACT",
        "official_fact_admitted": False,
        "official_store_adoption": "REFUSED",
        "valuation_use": "CLOSED",
        "common_shareholder_pb": "UNAVAILABLE",
        "existing_consumer_usable": False,
        "industrial_ratios": "NOT_APPLICABLE",
        "normalized_eps": "NOT_COMPUTED",
        "observations": rows,
        "rejected_income_columns": rejected_columns,
        "net_income_yoy_pct": _yoy("net_income"),
        "pre_provision_profit_yoy_pct": _yoy("pre_provision_profit"),
        "credit_loss_provision_yoy_pct": _yoy("credit_loss_provision"),
    }


def evf_reviewed_statement_shadow(*, pdf_bytes: bytes) -> dict[str, Any]:
    """Bind the reviewed finance-company filing. Official admission stays closed."""
    if _sha(pdf_bytes) != EVF_Q3_SHA256:
        raise ValueError("EVF_RETAINED_PDF_DOES_NOT_MATCH")
    return evf_reviewed_page_research()


def pow_consolidated_statement_shadow(*, pdf_bytes: bytes) -> dict[str, Any]:
    """Research rows from the exact HOSE POW filing. A failed income column stays out."""
    if _sha(pdf_bytes) != POW_Q3_SHA256:
        raise ValueError("POW_RETAINED_PDF_DOES_NOT_MATCH")
    return pow_reviewed_page_research()
