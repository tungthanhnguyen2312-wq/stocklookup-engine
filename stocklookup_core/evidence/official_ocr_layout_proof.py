"""Scoped OCR layout proof for image-only official statements (Owner-approved corrective 2026-11-07).

Two admission checks assume a native text layer: document currency/unit declared on front pages 1-8,
and a cited ``label + value`` span that is contiguous in page text. An image-only VAS statement has no
text layer, declares ``Đơn vị: VND`` only on each statement page, and prints the line-code and note
columns between label and amount. For a document whose layout is registered here (no global
whitelist) the two checks are replaced by proofs that are at least as strict:

* a retained, content-addressed OCR proof (positioned tokens + rendered-image hashes + engine/config)
  bound to the document SHA, so every literal is replayable without re-running OCR;
* ``verify_statement_unit``: the table's own unit declaration (exact token ids, page, SHA, located above
  the table header), parsed to currency AND scale; any other parsed declaration on the statement pages
  or front pages that differs, or an undeclared page, blocks;
* ``verify_row``: label tokens, line-code token, value token and current-period header proven on one
  physical table row by coordinates: value inside the "current period" band under its header, line code
  in the line-code band on the value's row, no second amount in the current band on that row, a
  distinct comparative amount in the comparative band, exact raw text and sign.

Nothing here infers or repairs a value; ambiguous OCR stays blocked by the existing numeric policy.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

CONTRACT_VERSION = "official_ocr_layout_proof/v1"
PROOF_DIR = "ocr-layout-proofs"

# Registered, individually proven layouts. Adding a document is a reviewed change, never a pattern match.
LAYOUT_PROOFS: dict[str, dict[str, Any]] = {
    "9a2881a88ac8ca4cc5cd948b0fafa031ff30fd0332a372f362477a8a6b0c9968": {
        "ticker": "HPG", "reporting_period": "2026-H1", "statement_scope": "consolidated",
        "layout": "VAS_TT43_2026_INTERIM_CONSOLIDATED_B01a_B02a_B03a_COLUMN_MAJOR_OCR",
        "statement_pages": (9, 10, 11, 12, 13, 14),
        "current_headers": ("Kỳ này", "Số cuối kỳ"),
        "comparative_headers": ("Kỳ trước", "Số đầu kỳ"),
        "metric_line_codes": {"revenue": "10", "net_income": "60", "attributable_net_income": "61",
                              "total_assets": "280", "shareholders_equity": "400", "operating_cash_flow": "20"},
        "approval": "Owner approval 2026-11-07: scoped HPG H1/2026 admission contract corrective",
        # Verified at registration: no native text layer on any page (pypdf 6.14.2, 67/67 pages empty).
        "text_layer_verification": {"tool": "pypdf 6.14.2", "pages_checked": 67, "non_empty_pages": 0,
                                    "state": "NONE_VERIFIED", "verified_at": "2026-11-07"},
    },
}

_AMOUNT = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})+\)?$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def layout_for(document_sha256: str | None) -> dict[str, Any] | None:
    return LAYOUT_PROOFS.get(str(document_sha256 or ""))


def build_ocr_proof(*, document_sha256: str, materializations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Freeze the OCR tokens actually used for admission. Pages outside the registered layout are kept
    only for front-matter literals (period, scope, assurance, issuer)."""
    layout = layout_for(document_sha256)
    if layout is None:
        raise ValueError("OCR_LAYOUT_NOT_REGISTERED")
    pages: dict[str, Any] = {}
    engine, config = set(), set()
    for materialization in materializations:
        if materialization.get("document_sha256") != document_sha256:
            raise ValueError("OCR_PROOF_DOCUMENT_MISMATCH")
        for page in materialization.get("pages") or []:
            ocr = page.get("ocr_derived_text_evidence") or {}
            image = page.get("source_image_evidence") or {}
            if not ocr.get("tokens") or image.get("document_sha256") != document_sha256:
                raise ValueError("OCR_PROOF_PAGE_INCOMPLETE")
            engine.add(ocr.get("engine_version"))
            config.add(canonical_json(ocr.get("config")))
            pages[str(page["page_number"])] = {
                "rendered_image_sha256": image.get("rendered_image_sha256"),
                "ocr_adapters": page.get("ocr_adapters") or {},
                "tokens": [{k: t.get(k) for k in ("token_id", "raw_token_order", "text", "x0", "x1", "top", "bottom",
                                                    "tsv_hierarchy", "source_text")} for t in ocr["tokens"]],
            }
    if len(engine) != 1 or len(config) != 1:
        raise ValueError("OCR_PROOF_ENGINE_OR_CONFIG_NOT_UNIQUE")
    body = {"contract_version": CONTRACT_VERSION, "document_sha256": document_sha256, "layout": layout["layout"],
            "engine_version": engine.pop(), "ocr_config": json.loads(config.pop()), "pages": pages}
    return {**body, "proof_sha256": hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()}


def verify_proof_identity(proof: Mapping[str, Any], *, document_sha256: str, proof_sha256: str | None) -> list[str]:
    body = {k: v for k, v in proof.items() if k != "proof_sha256"}
    actual = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    reasons = []
    if actual != proof.get("proof_sha256") or (proof_sha256 is not None and actual != proof_sha256):
        reasons.append("OCR_PROOF_HASH_MISMATCH")
    if proof.get("document_sha256") != document_sha256 or layout_for(document_sha256) is None:
        reasons.append("OCR_PROOF_DOCUMENT_OR_LAYOUT_MISMATCH")
    if proof.get("contract_version") != CONTRACT_VERSION:
        reasons.append("OCR_PROOF_CONTRACT_MISMATCH")
    return reasons


def page_text(proof: Mapping[str, Any], page_number: int) -> str:
    page = (proof.get("pages") or {}).get(str(page_number)) or {}
    lines: dict[tuple[int, int, int], list[str]] = {}
    for token in sorted(page.get("tokens") or [], key=lambda t: int(t.get("raw_token_order") or 0)):
        h = token.get("tsv_hierarchy") or {}
        lines.setdefault((int(h.get("block_num", 0)), int(h.get("par_num", 0)), int(h.get("line_num", 0))), []).append(
            str(token.get("text") or ""))
    return "\n".join(" ".join(words) for _, words in sorted(lines.items()))


def _tokens(proof: Mapping[str, Any], page_number: int) -> list[Mapping[str, Any]]:
    return list(((proof.get("pages") or {}).get(str(page_number)) or {}).get("tokens") or [])


def _overlap(a_top: float, a_bottom: float, b_top: float, b_bottom: float) -> float:
    height = min(a_bottom - a_top, b_bottom - b_top)
    return max(0.0, min(a_bottom, b_bottom) - max(a_top, b_top)) / height if height > 0 else 0.0


def _in_band(token: Mapping[str, Any], band: Mapping[str, Any] | None) -> bool:
    return bool(band) and float(token["x0"]) >= float(band["x0"]) - 2 and float(token["x1"]) <= float(band["x1"]) + 2


def _statement_declarations(proof: Mapping[str, Any], pages: Iterable[int], parse_unit) -> list[dict[str, Any]]:
    found = []
    for number in pages:
        for line in page_text(proof, number).splitlines():
            parsed = parse_unit(line)
            if parsed:
                found.append({"page": number, "text": line, "currency": parsed["currency"], "unit_scale": parsed["unit_scale"]})
    return found


def verify_statement_unit(unit_evidence: Mapping[str, Any] | None, proof: Mapping[str, Any], *, source_page: int,
                          header_top: float | None, currency: str, unit_scale: int, parse_unit) -> list[str]:
    """The fact's own table declaration, bound by token ids/page/SHA, above the table header,
    consistent with every parsed declaration in the document (front and statement pages)."""
    layout = layout_for(proof.get("document_sha256")) or {}
    reasons: list[str] = []
    unit = dict(unit_evidence or {})
    evidence = dict(unit.get("evidence") or {})
    if unit.get("state") != "QUALIFIED" or not evidence:
        return ["STATEMENT_UNIT_EVIDENCE_MISSING"]
    page = int(evidence.get("continuation_of_page") or evidence.get("page_number") or -1)
    if page not in layout.get("statement_pages", ()) or int(evidence.get("page_number") or -1) != source_page:
        reasons.append("STATEMENT_UNIT_NOT_BOUND_TO_FACT_TABLE")
    if evidence.get("document_sha256") != proof.get("document_sha256"):
        reasons.append("STATEMENT_UNIT_DOCUMENT_MISMATCH")
    ids = list((evidence.get("source_span") or {}).get("token_ids") or [])
    by_id = {t.get("token_id"): t for t in _tokens(proof, page)}
    if not ids or any(i not in by_id for i in ids):
        reasons.append("STATEMENT_UNIT_TOKENS_NOT_IN_PROOF")
    else:
        text = " ".join(str(by_id[i].get("text") or "") for i in ids)
        if " ".join(text.split()) != " ".join(str(evidence.get("evidence_text") or "").split()):
            reasons.append("STATEMENT_UNIT_TEXT_NOT_IN_PROOF")
        if header_top is not None and any(float(by_id[i]["bottom"]) > float(header_top) for i in ids):
            reasons.append("STATEMENT_UNIT_NOT_ABOVE_TABLE_HEADER")
    if (evidence.get("currency"), evidence.get("unit_scale")) != (currency, unit_scale):
        reasons.append("STATEMENT_UNIT_VALUE_MISMATCH")
    declarations = _statement_declarations(proof, sorted(int(p) for p in (proof.get("pages") or {})), parse_unit)
    semantics = {(d["currency"], d["unit_scale"]) for d in declarations}
    if semantics != {(currency, unit_scale)}:
        reasons.append("STATEMENT_UNIT_DECLARATIONS_CONFLICT")
    declared_pages = {d["page"] for d in declarations}
    if page not in declared_pages:
        reasons.append("STATEMENT_UNIT_PAGE_UNDECLARED")
    return sorted(set(reasons))


def verify_row(row_object: Mapping[str, Any] | None, proof: Mapping[str, Any], *, metric: str, source_page: int,
               line_code: str, raw_value: str, value: int, unit_scale: int, parse_amount) -> list[str]:
    """Same-row proof by OCR coordinates; replaces the contiguous label+value string check.

    ``parse_amount`` is the existing accounting-integer parser, injected by the root-level caller.
    """
    layout = layout_for(proof.get("document_sha256")) or {}
    row = dict(row_object or {})
    reasons: list[str] = []
    if source_page not in layout.get("statement_pages", ()):
        return ["ROW_PAGE_OUTSIDE_REGISTERED_LAYOUT"]
    tokens = _tokens(proof, source_page)
    if not tokens or not row:
        return ["ROW_PROOF_MISSING"]
    bands = ((row.get("column_bands") or {}).get("bands") or {})
    header = ((row.get("column_bands") or {}).get("header_evidence") or {})
    identities = header.get("period_identities") or {}
    cur_band, cmp_band, code_band = bands.get("current_period_value"), bands.get("comparative_period_value"), bands.get("line_code")
    vbox, row_box = row.get("current_value_bbox") or {}, row.get("row_bbox") or {}
    if not (cur_band and cmp_band and code_band and vbox and row_box):
        return ["ROW_GEOMETRY_MISSING"]
    expected = (layout.get("metric_line_codes") or {}).get(metric)
    if expected is None or str(line_code) != expected or str(row.get("line_code")) != expected:
        reasons.append("ROW_LINE_CODE_NOT_EXPECTED_FOR_METRIC")
    by_order = {int(t["raw_token_order"]): t for t in tokens}
    # Current-period header: exact registered text, its own tokens in the proof, above the row.
    current = identities.get("current") or {}
    if (current.get("raw_text") not in layout.get("current_headers", ())
            or row.get("current_period_label") != current.get("raw_text")):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_REGISTERED")
    header_tokens = [by_order.get(int(o)) for o in current.get("source_token_orders") or []]
    if not header_tokens or any(t is None for t in header_tokens) or " ".join(t["text"] for t in header_tokens) != current.get("raw_text"):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_IN_PROOF")
    elif max(float(t["bottom"]) for t in header_tokens) > float(vbox["top"]):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_ABOVE_ROW")
    elif not (float(cur_band["x0"]) - 2 <= min(float(t["x0"]) for t in header_tokens)
              and max(float(t["x1"]) for t in header_tokens) <= float(cur_band["x1"]) + 2):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_OVER_VALUE_COLUMN")
    # Value token: exact text and exact box, inside the current band, not inside the comparative band.
    value_tokens = [t for t in tokens if str(t.get("text")) == raw_value
                    and abs(float(t["x0"]) - float(vbox["x0"])) <= 1 and abs(float(t["top"]) - float(vbox["top"])) <= 1]
    if len(value_tokens) != 1:
        reasons.append("VALUE_TOKEN_NOT_UNIQUE_IN_PROOF")
        return sorted(set(reasons))
    token = value_tokens[0]
    if not _in_band(token, cur_band) or _in_band(token, cmp_band):
        reasons.append("VALUE_NOT_IN_CURRENT_PERIOD_COLUMN")
    on_row = [t for t in tokens if _overlap(float(t["top"]), float(t["bottom"]), float(token["top"]), float(token["bottom"])) >= 0.5]
    # Line code on the value's own physical row, inside the line-code band.
    codes = [t for t in on_row if _in_band(t, code_band) and str(t["text"]).strip() == str(line_code)]
    if len(codes) != 1:
        reasons.append("LINE_CODE_NOT_ON_VALUE_ROW")
    # No second amount in the current column on that row; a distinct comparative amount present.
    current_amounts = [t for t in on_row if _in_band(t, cur_band) and _AMOUNT.match(str(t["text"]))]
    if len(current_amounts) != 1:
        reasons.append("ADJACENT_AMOUNT_AMBIGUITY")
    comparative = [t for t in on_row if _in_band(t, cmp_band) and _AMOUNT.match(str(t["text"]))]
    if len(comparative) != 1 or comparative[0]["text"] != row.get("comparative_raw_value"):
        reasons.append("COMPARATIVE_COLUMN_NOT_PROVEN")
    # Label tokens: exact fragments, label band, inside the row box, and one of them on the value's line band.
    orders = [int(o) for o in row.get("label_source_token_orders") or []]
    labels = [by_order.get(o) for o in orders]
    if not labels or any(t is None for t in labels) or [t["text"] for t in labels] != list(row.get("raw_label_fragments") or []):
        reasons.append("LABEL_TOKENS_NOT_IN_PROOF")
    else:
        if any(not _in_band(t, bands.get("label")) for t in labels):
            reasons.append("LABEL_OUTSIDE_LABEL_COLUMN")
        if any(float(t["top"]) < float(row_box["top"]) - 3 or float(t["bottom"]) > float(row_box["bottom"]) + 3 for t in labels):
            reasons.append("LABEL_OUTSIDE_ROW")
        bounds = (row.get("physical_line_reconstruction") or {}).get("row_baseline_bounds") or []
        if len(bounds) != 2 or not (float(bounds[0]) <= (float(token["top"]) + float(token["bottom"])) / 2 <= float(bounds[1])):
            reasons.append("VALUE_OUTSIDE_ROW_BASELINE")
    # Exact amount and sign.
    try:
        if parse_amount(raw_value) * int(unit_scale) != int(value):
            reasons.append("VALUE_PARSE_MISMATCH")
        if (raw_value.startswith("(") and raw_value.endswith(")")) != (int(value) < 0):
            reasons.append("VALUE_SIGN_MISMATCH")
    except (ValueError, TypeError):
        reasons.append("VALUE_PARSE_MISMATCH")
    return sorted(set(reasons))


def statement_unit_metadata_claims(proof: Mapping[str, Any], front_pages: Iterable[int], parse_unit) -> dict[str, Any] | None:
    """Document currency/unit claims sourced from statement-page declarations (registered layout only).

    Every statement page must declare, all parsed declarations (including any on front pages) must agree,
    otherwise None (stays blocked)."""
    layout = layout_for(proof.get("document_sha256"))
    if layout is None:
        return None
    statement = _statement_declarations(proof, [p for p in layout["statement_pages"] if str(p) in (proof.get("pages") or {})], parse_unit)
    front = _statement_declarations(proof, [p for p in front_pages if str(p) in (proof.get("pages") or {})], parse_unit)
    semantics = {(d["currency"], d["unit_scale"]) for d in statement + front}
    pages_declared = {d["page"] for d in statement}
    # Each fact's own table declaration is enforced by verify_statement_unit; here every parsed
    # declaration in the document must agree, and at least one statement page must declare.
    if len(semantics) != 1 or not statement:
        return None
    currency, unit_scale = semantics.pop()
    first = sorted(statement, key=lambda d: d["page"])[0]
    return {"currency": currency, "unit_scale": unit_scale, "page": first["page"], "text": first["text"],
            "declared_pages": sorted(pages_declared)}


STATEMENT_UNIT_CITATION_KIND = "statement_page_unit_declaration"
REPLACED_BY_ROW_PROOF = ("VALUE_SPAN_NOT_IN_RETAINED_DOCUMENT",)
REPLACED_BY_UNIT_PROOF = ("RETAINED_UNIT_SCALE_NOT_EXPLICIT", "RETAINED_CURRENCY_NOT_EXPLICIT")


def proof_reference(proof: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION, "proof_sha256": proof["proof_sha256"],
            "relative_path": f"{PROOF_DIR}/{proof['document_sha256']}/{proof['proof_sha256']}.json"}


def apply_layout_proof(row: Mapping[str, Any], proof: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None,
                       reasons: list[str], missing: list[str], *, parse_amount, parse_unit) -> tuple[list[str], list[str]]:
    """Replace exactly the two text-layer checks with coordinate proofs; never remove any other reason.

    Applies only to a row that carries an ``ocr_layout_proof`` reference for a registered layout.
    Any failed proof adds its own reason codes; an unavailable proof keeps the fact UNKNOWN.
    """
    ref = row.get("ocr_layout_proof")
    sha = str(row.get("document_sha256") or "")
    layout = layout_for(sha)
    if not isinstance(ref, Mapping) or layout is None:
        return reasons, missing
    if proof is None:
        return reasons, missing + ["OCR_LAYOUT_PROOF_UNAVAILABLE"]
    proof_reasons = verify_proof_identity(proof, document_sha256=sha, proof_sha256=ref.get("proof_sha256"))
    if (row.get("ticker"), row.get("reporting_period"), row.get("statement_scope")) != (
            layout["ticker"], layout["reporting_period"], layout["statement_scope"]):
        proof_reasons.append("OCR_LAYOUT_SCOPE_MISMATCH")
    row_object = row.get("ocr_row_object") or {}
    lineage = row.get("source_lineage") or {}
    source_page = row.get("source_page") if row.get("source_page") is not None else lineage.get("source_page")
    line_code = row.get("line_code") if row.get("line_code") is not None else lineage.get("line_code")
    try:
        proof_reasons += verify_row(row_object, proof, metric=str(row.get("canonical_metric")),
                                    source_page=int(source_page or -1), line_code=str(line_code),
                                    raw_value=str(row.get("raw_value_text") or ""), value=int(row.get("normalized_value")),
                                    unit_scale=int(row.get("source_unit_scale") or 0), parse_amount=parse_amount)
    except (TypeError, ValueError, KeyError):
        proof_reasons.append("ROW_PROOF_MALFORMED")
    claims = (metadata or {}).get("metadata_claims") or {}
    statement_unit_claims = [name for name in ("currency", "unit_scale")
                             if (((claims.get(name) or {}).get("evidence_span") or {}).get("citation_kind")
                                 == STATEMENT_UNIT_CITATION_KIND)]
    if statement_unit_claims:
        header_top = ((((row_object.get("column_bands") or {}).get("header_evidence") or {}).get("bbox") or {}).get("top"))
        proof_reasons += verify_statement_unit(row.get("ocr_unit_evidence"), proof, source_page=int(source_page or -1),
                                               header_top=header_top, currency=str(row.get("currency")),
                                               unit_scale=int(row.get("source_unit_scale") or 0), parse_unit=parse_unit)
    if proof_reasons:
        return sorted(set(reasons + proof_reasons)), missing
    replaced = set(REPLACED_BY_ROW_PROOF) | (set(REPLACED_BY_UNIT_PROOF) if statement_unit_claims else set())
    return [r for r in reasons if r not in replaced], missing
