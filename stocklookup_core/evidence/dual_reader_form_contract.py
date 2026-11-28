"""Bounded non-corporate Decision 2 identities; no independent admission path.

Only printed literals retained by the November 28 cold readers are registered.
EVF has candidate row identities but NO evidenced form literal: admission is
deliberately disabled. This module never supplies corporate revenue or EPS.
"""
from __future__ import annotations

import hashlib
import json
from types import MappingProxyType

CONTRACT_VERSION = "dual_reader_form_identity/v1"

# Descriptive candidates only. Both sealed EVF readers record form/scope null.
# The total operating-income row has no printed code; no code is invented.
EVF_CANDIDATE_ROWS = (
    ("I", "Thu nhập lãi thuần", "credit_net_interest_income"),
    ("IX", "Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng",
     "credit_operating_profit_before_provisions"),
    ("X", "Chi phí dự phòng rủi ro tín dụng", "credit_provision_expense"),
    ("XI", "Tổng lợi nhuận trước thuế", "credit_profit_before_tax"),
    ("XIII", "Lợi nhuận sau thuế", "credit_profit_after_tax"),
)
EVF_FORM_LITERALS = ()

# Numeric outline prefixes have already been split by the existing verifier.
# Roman section prefixes are part of the literal and remain significant.
FORM_ROWS = MappingProxyType({
    "B02-CTCK/HN": (
        ("90", "IX. TỔNG LỢI NHUẬN KẾ TOÁN TRƯỚC THUẾ", "securities_profit_before_tax"),
        ("200", "XI. LỢI NHUẬN KẾ TOÁN SAU THUẾ TNDN", "securities_profit_after_tax"),
        ("201", "Lợi nhuận sau thuế phân bổ cho chủ sở hữu", "securities_profit_allocated_to_owners"),
        ("202", "Lợi nhuận sau thuế trích các Quỹ", "securities_profit_appropriated_to_funds"),
    ),
    "B02a-CTCK/HN": (
        ("90", "VIII. TỔNG LỢI NHUẬN KẾ TOÁN TRƯỚC THUẾ", "securities_profit_before_tax"),
        ("200", "X. LỢI NHUẬN KẾ TOÁN SAU THUẾ TNDN", "securities_profit_after_tax"),
        ("201", "Lợi nhuận sau thuế phân bổ cho chủ sở hữu", "securities_profit_allocated_to_owners"),
        ("202", "Lợi nhuận sau thuế trích các Quỹ", "securities_profit_appropriated_to_funds"),
    ),
})

# These exact note literals establish only the original current-column basis.
# No approved rate/amount, post-appropriation basis or comparative is inferred.
_BASIS_NOTES = MappingProxyType({
    ("B02-CTCK/HN", "2025"): (
        "B05-CTCK/HN", "Năm nay",
        "Lợi nhuận sau thuế phân bổ cho cổ đông sở hữu cổ phiếu phổ thông - VND",
        "Báo cáo năm 2025 được tính trên cơ sở chưa gồm tỷ lệ trích lập các quỹ do chưa có đủ thông tin.",
        "tại ngày 31 tháng 12 năm 2025 và cho năm tài chính kết thúc cùng ngày"),
    ("B02a-CTCK/HN", "2026-H1"): (
        "B05a-CTCK/HN", "Cho giai đoạn tài chính sáu tháng kết thúc ngày 30 tháng 6 năm 2026",
        "Lợi nhuận sau thuế phân bổ cho cổ đông sở hữu cổ phiếu phổ thông – VND",
        "Báo cáo cho giai đoạn tài chính kết thúc ngày 30 tháng 6 năm 2026 được tính trên cơ sở chưa gồm tỷ lệ trích lập các quỹ do chưa có đủ thông tin.",
        "tại ngày 30 tháng 6 năm 2026 và cho giai đoạn tài chính sáu tháng kết thúc cùng ngày"),
})


def row_identity(form_literal, statement_family, period, line_code, label, metric):
    """Exact family/code/label/metric match. This is not fact qualification."""
    if statement_family != "income_statement" or not isinstance(period, str):
        return False
    if form_literal == "B02-CTCK/HN" and period != "2025":
        return False
    if form_literal == "B02a-CTCK/HN" and period not in {"2025-H1", "2026-H1"}:
        return False
    return (str(line_code), label, metric) in FORM_ROWS.get(form_literal, ())


def verify_appropriation_basis(row, note, *, proof, source_record, families,
                               family_aliases, time, input_binding_matches,
                               signed_cell_literal, recognize_scope):
    """Replay a same-PDF note solely to classify code 201's basis.

    No note fact, EPS or share count is admitted. The exact unestimated-funds
    disclosure and identical numerator must be read by both income families.
    Missing timestamps, unknown families and caller-only basis claims refuse.
    """
    def fail(code):
        return {"valid": False, "reason_codes": ["DUAL_READER_" + code]}
    rule = _BASIS_NOTES.get((row.get("form_reference_literal"), row.get("reporting_period")))
    if not rule or not note or not row.get("appropriation_basis"):
        return fail("APPROPRIATION_BASIS_UNPROVEN")
    try:
        ref = proof["appropriation_note"]
        image = ref["page_image"]
        sha = row["document_sha256"]
        if (hashlib.sha256(note["image_bytes"]).hexdigest() != image["sha256"]
                or image not in source_record.get("page_image_bindings", [])
                or type(image["source_page"]) is not int or image["source_page"] < 1
                or not str(image["printed_page"])):
            return fail("APPROPRIATION_NOTE_BINDING_MISMATCH")
        refs, payloads = ref["readings"], note["raw_reader_bytes"]
        if (len(refs) != 2 or len(payloads) != 2
                or refs[0]["sha256"] == refs[1]["sha256"]
                or refs[0]["relative_path"] == refs[1]["relative_path"]):
            return fail("APPROPRIATION_BASIS_UNPROVEN")
        seen_families, ids, selections = [], [], []
        for entry, payload in zip(refs, payloads):
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                return fail("APPROPRIATION_NOTE_HASH_MISMATCH")
            raw = json.loads(payload)
            family = family_aliases.get(str(raw["model_family"]).lower())
            if (not family or raw["contract_version"] != "independent_image_reading/v1"
                    or raw["method"] != "DIRECT_PAGE_IMAGE" or raw["independent_input"] is not True
                    or raw["saw_other_reader_output"] is not False or not raw["reader_id"]):
                return fail("APPROPRIATION_BASIS_UNPROVEN")
            if not input_binding_matches(raw["input"], {
                    "document_sha256": sha, "document_id": proof["document_id"],
                    "image_sha256": image["sha256"], "source_page": image["source_page"],
                    "printed_page": image["printed_page"]}):
                return fail("APPROPRIATION_NOTE_BINDING_MISMATCH")
            if not (time(source_record["observed_at"]) <= time(raw["recorded_at"])
                    <= time(entry["retained_at"]) < time(proof["comparison_started_at"])
                    <= time(proof["admission_completed_at"])):
                return fail("APPROPRIATION_NOTE_TIME_ORDER_INVALID")
            table = raw["table"]
            columns = [c for c in table["columns"] if c["label_literal"] == rule[1]]
            rows = [r for r in table["rows"] if r["row_label_literal"] == rule[2]]
            quotes = [q for q in raw["prose_observations"] if q["quote_literal"] == rule[3]]
            if (table["form_reference_literal"] != rule[0]
                    or table["issuer_literal"] != row["issuer_literal"]
                    or table["period_caption_literal"] != rule[4]
                    or recognize_scope(table["scope_literal"])["statement_scope"] != row["statement_scope"]
                    or len(columns) != 1 or columns[0]["role"] != "current"
                    or len(rows) != 1 or len(quotes) != 1 or quotes[0]["uncertainty"] != []):
                return fail("APPROPRIATION_BASIS_UNPROVEN")
            cells = [c for c in rows[0]["cells"] if c["column_id"] == columns[0]["column_id"]]
            if (len(cells) != 1 or cells[0]["uncertainty"] != []
                    or signed_cell_literal(cells[0]["raw_value_literal"], cells[0]["sign_literal"])
                    != row["raw_value_text"]):
                return fail("APPROPRIATION_NOTE_NUMERATOR_MISMATCH")
            selections.append((table["scope_literal"], table["period_caption_literal"],
                               columns[0], rows[0]["line_code_literal"], cells[0]))
            seen_families.append(family)
            ids.append(raw["reader_id"])
        if (sorted(seen_families) != sorted(families) or len(set(ids)) != 2
                or len(set(seen_families)) != 2):
            return fail("APPROPRIATION_BASIS_UNPROVEN")
        if selections[0] != selections[1]:
            return fail("APPROPRIATION_NOTE_LITERAL_DISAGREEMENT")
        basis = "PRE_FUND_APPROPRIATION_UNESTIMATED"
        if row["appropriation_basis"] != basis:
            return fail("APPROPRIATION_BASIS_MISMATCH")
        return {"valid": True, "reason_codes": [], "appropriation_basis": {
            "basis": basis, "reporting_vintage": "ORIGINAL_CURRENT_COLUMN",
            "document_sha256": sha, "reporting_period": row["reporting_period"],
            "column_id": row["column_id"], "column_label_literal": row["current_period_label"],
            "note_page_image": image, "note_literal": rule[3],
            "raw_sha256": [r["sha256"] for r in refs]}}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return fail("APPROPRIATION_BASIS_UNPROVEN")
