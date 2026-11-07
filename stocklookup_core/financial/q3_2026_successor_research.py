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
