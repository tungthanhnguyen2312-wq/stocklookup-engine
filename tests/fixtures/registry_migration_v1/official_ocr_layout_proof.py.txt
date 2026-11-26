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

Ambiguous OCR stays blocked. HOL-08 adds only same-render baseline U+00B2 geometry proof;
raw tokens remain unchanged and no other numeric character is interpreted differently.
"""
from __future__ import annotations

import hashlib
import json
import re
import math
from statistics import median
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

# HOL-08: exact retained originals authorized for bounded operand replay. No source-family
# wildcard and no claim that an existing (possibly unqualified) text layer is absent.
for _sha, _ticker, _period, _pages in (
    ("f38c5f75becf7d3f145d27183eec81f119fd4f75e378b983a2763ddc3f7e0c07", "HPG", "2025", (7, 8, 9, 10, 11, 12)),
    ("309f86836d9f00b37e3cccb25da9e7ffd0dab6c531be995618542004acccdf1d", "PNJ", "2025", (7, 8, 9, 10, 11)),
    ("ebb7e9eead6404301473582fc879e63feb4ca09eecbc92ccf98dab63f97b7eb9", "HPG", "2025-H1", (10,)),
    ("12c40161cdb31ef603256892dbe70a2bba6a906c5b2e033ed281cb321466601c", "PNJ", "2025-H1", (10,)),
    ("eba4fad322c0a634f156a0f4345d72b47b6962842cadee55607cdd278fcdd577", "VRE", "2025-H1", (11,)),
):
    LAYOUT_PROOFS[_sha] = {
        "ticker": _ticker, "reporting_period": _period, "statement_scope": "consolidated",
        "layout": "VAS_EXACT_RETAINED_TWO_COLUMN_HOL08",
        "statement_pages": _pages, "current_headers": ("Kỳ này", "Năm nay", "2025", "30.6.2025"),
        "comparative_headers": ("Kỳ trước", "Năm trước", "2024", "30.6.2024"),
        "metric_line_codes": {"revenue": "10", "net_income": "60", "attributable_net_income": "61",
                              "total_assets": "270", "shareholders_equity": "400", "operating_cash_flow": "20"},
        "approval": "HL-20261124-HOL-08: exact retained annual and prior H1 operand replay",
    }

# Decision 2: exact originals only, bounded to the independently read income page.
# Text-layer descriptions are Head Leader observations, not executor verification:
# pypdf is unavailable in this sandbox. Presence never qualifies native text or
# bypasses the existing zero-native-candidate OCR fallback gate.
for _sha, _ticker, _period, _pages, _current, _comparative, _text_layer in (
    ("54077f6abf8f31ce54eb92fd92e00ae107fe30cb9fabac2829dfb911b49bcbe7", "POW", "2025", (11,),
     ("Current year",), ("Prior year",), "Native text layer reported: 60,233 characters over 26 pages"),
    ("e56815b230d3130816b1169055691d3dc6ce6b67af932a651db69b6da52045c1", "POW", "2025-H1", (11,),
     ("Current period",), ("Prior period",), "Scanned PDF reported: 419 extracted characters"),
    ("38f6bcd441d601fa94e2742ee7d6721c4f423110b656e90ba0f9e8ac2e123cd5", "POW", "2026-H1", (11,),
     ("Current period",), ("Prior period",), "Scanned PDF reported: 2,959 extracted characters"),
    ("618d514b355387ade90d2266f8f8c4c7098d94339592dc696d900482c96b4e6c", "NVL", "2025-H1", (12,),
     ("06 tháng đầu năm 2025",), ("06 tháng đầu năm 2024",), "Garbled OCR text layer reported"),
    ("20aa7254735542d470f12ada8d02786dfa5e673035274e42d3404352e266a007", "NVL", "2026-H1", (12,),
     ("06 tháng đầu năm 2026",), ("06 tháng đầu năm 2025 (Trình bày lại)",), "Garbled OCR text layer reported"),
    ("8a1cb94cbe9ef5d98550ef6ab734f54f99ecb9376f43c8aa4a3662cd6d5d0353", "NVL", "2025", (12,),
     ("Năm 2025",), ("Năm 2024",), "Garbled OCR text layer reported"),
):
    LAYOUT_PROOFS[_sha] = {
        "ticker": _ticker, "reporting_period": _period, "statement_scope": "consolidated",
        "layout": "VAS_EXACT_RETAINED_TWO_COLUMN_DECISION2_20261125",
        "statement_pages": _pages, "current_headers": _current, "comparative_headers": _comparative,
        "metric_line_codes": {"revenue": "10", "net_income": "60", "attributable_net_income": "61"},
        "approval": "Owner directive 2026-11-25 task 5: Decision 2 admission expansion (governed acquisition + dual-reader)",
        "text_layer_verification": {"tool": "pypdf unavailable in executor sandbox",
                                    "state": "HOST_VERIFICATION_REQUIRED", "reported_observation": _text_layer},
    }

# HL-20261126-CDX-26: exact retained income pages; no text-layer qualification.
for _sha, _ticker, _period, _pages, _current, _comparative in (
    ('2648374e2e6c60403a353f36456a88f4c34675f1cb4ff3cd6a5adc5d0b90f1b1', 'HAH', '2025', (13,), ('Năm nay',), ('Năm trước',)),
    ('a36ae93c0c3434d3e47c36f5d6de07ca6623db880b01c850a0bdd9855a45837b', 'HAH', '2025-H1', (12,), ('Kỳ này',), ('Kỳ trước',)),
    ('913d92bec2564ad9efa15db114e34419d21e4b466bf51964ddca941682cf7291', 'HAH', '2026-H1', (13,), ('Kỳ này',), ('Kỳ trước',)),
    ('9e028ec5b6e612767068d0ba25c83c1350a86e55753a61fda7625fae26c4dcf9', 'BWE', '2025', (12,), ('Năm 2025',), ('Năm 2024',)),
    ('acb48684fcf4d14266f2bd0ca684331d7b69e2953a50f612e9004cb055cb92c8', 'BWE', '2025-H1', (12,), ('06 tháng đầu năm 2025',), ('06 tháng đầu năm 2024',)),
    ('6e19b66271a6cf87be38791ffb2c29985b13930b12dfd72399909ffde2c9cdef', 'BWE', '2026-H1', (12,), ('06 tháng đầu năm 2026',), ('06 tháng đầu năm 2025',)),
):
    LAYOUT_PROOFS[_sha] = {
        "ticker": _ticker, "reporting_period": _period, "statement_scope": "consolidated",
        "layout": "VAS_EXACT_RETAINED_TWO_COLUMN_DECISION2_20261126",
        "statement_pages": _pages, "current_headers": _current, "comparative_headers": _comparative,
        "metric_line_codes": {"revenue": "10", "net_income": "60", "attributable_net_income": "61"},
        "approval": "HL-20261126-CDX-26: bounded Decision 2 HAH/BWE registrations only",
        "text_layer_verification": {"state": "HOST_VERIFICATION_REQUIRED"},
    }


_AMOUNT = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})+\)?$")

BASELINE_TWO_CONTRACT = "ocr_baseline_u00b2_geometry/v1"
BASELINE_TWO_TOLERANCE = 0.10


def baseline_two_value(token: Mapping[str, Any], rendered_image_sha256: str) -> tuple[str, dict | None]:
    """Only U+00B2, proven at baseline against other ASCII digits of this exact token.

    Coordinates are top-origin pixels of the same retained render. Raw text is never changed.
    Missing, malformed, raised, small or mixed-damage character evidence fails closed.
    """
    raw = str(token.get("text") or "")
    if "²" not in raw:
        return raw, None
    evidence = token.get("glyph_evidence") or {}
    if not isinstance(evidence, Mapping):
        return raw, None
    boxes = evidence.get("boxes") or []
    if not isinstance(boxes, list) or not all(isinstance(b, Mapping) for b in boxes):
        return raw, None
    if (not re.fullmatch(r"\(?-?[0-9²]{1,3}(?:[.,][0-9²]{3})+\)?", raw)
            or not re.fullmatch(r"[0-9a-f]{64}", str(rendered_image_sha256))
            or evidence.get("rendered_image_sha256") != rendered_image_sha256
            or evidence.get("contract_version") != "tesseract_makebox_same_render/v1"
            or not evidence.get("engine_version") or not evidence.get("config")
            or "".join(str(b.get("text", "")) for b in boxes) != raw):
        return raw, None
    try:
        for b in boxes:
            if not all(math.isfinite(float(b[k])) for k in ("x0", "x1", "top", "bottom")):
                return raw, None
            if not (float(token["x0"]) - 1 <= float(b["x0"]) < float(b["x1"]) <= float(token["x1"]) + 1
                    and float(token["top"]) - 1 <= float(b["top"]) < float(b["bottom"]) <= float(token["bottom"]) + 1):
                return raw, None
        digits = [b for b in boxes if b["text"] in "0123456789"]
        if len(digits) < 3 or any(float(a["x1"]) > float(b["x0"]) + 1 for a, b in zip(boxes, boxes[1:])):
            return raw, None
        reference = {"top": median(float(b["top"]) for b in digits),
                     "bottom": median(float(b["bottom"]) for b in digits),
                     "height": median(float(b["bottom"]) - float(b["top"]) for b in digits)}
        tolerance = reference["height"] * BASELINE_TWO_TOLERANCE
        for b in boxes:
            if b["text"] == "²" and any(abs(v - reference[k]) > tolerance for k, v in (
                    ("top", float(b["top"])), ("bottom", float(b["bottom"])),
                    ("height", float(b["bottom"]) - float(b["top"])))):
                return raw, None
    except (KeyError, TypeError, ValueError):
        return raw, None
    normalized = raw.replace("²", "2")
    return normalized, {"contract_version": BASELINE_TWO_CONTRACT, "raw_value": raw,
        "normalized_value_text": normalized, "token_id": token.get("token_id"),
        "median_ascii_digit_box": reference, "tolerance_fraction": BASELINE_TWO_TOLERANCE,
        "tolerance_pixels": tolerance, "glyph_evidence": evidence,
        "rendered_image_sha256": rendered_image_sha256}


def numeric_token_value(raw: str, tokens: Iterable[Mapping[str, Any]], image_sha: str,
                        bbox: Mapping[str, Any]) -> tuple[str, dict | None]:
    try:
        matches = [t for t in tokens if t.get("text") == raw
                   and all(abs(float(t.get(k, -99999)) - float(bbox.get(k, -999))) <= 1
                           for k in ("x0", "x1", "top", "bottom"))]
    except (TypeError, ValueError):
        return raw, None
    return baseline_two_value(matches[0], image_sha) if len(matches) == 1 else (raw, None)


def bound_numeric_value(row: Mapping[str, Any], proof: Mapping[str, Any] | None) -> str:
    raw = str(row.get("raw_value_text") or "")
    ref = row.get("ocr_layout_proof") or {}
    if not proof or not ref.get("proof_sha256") or verify_proof_identity(
            proof, document_sha256=row.get("document_sha256"), proof_sha256=ref["proof_sha256"]):
        return raw
    page_number = row.get("source_page") or (row.get("source_lineage") or {}).get("source_page")
    page = (proof.get("pages") or {}).get(str(page_number)) or {}
    return numeric_token_value(raw, page.get("tokens") or [], page.get("rendered_image_sha256"),
        (row.get("ocr_row_object") or {}).get("current_value_bbox") or {})[0]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def layout_for(document_sha256: str | None) -> dict[str, Any] | None:
    return LAYOUT_PROOFS.get(str(document_sha256 or ""))


EXACT_REGISTERED_ISSUER_NAMES = {
    'HAH': (
        {'literal': 'CÔNG TY CỔ PHẦN VẬN TẢI VÀ XẾP DỠ HẢI AN',
         'provenance': {'document_sha256': '2648374e2e6c60403a353f36456a88f4c34675f1cb4ff3cd6a5adc5d0b90f1b1',
                        'source_page': 13,
                        'image_sha256': 'fb88447f588c83f8fdaf70368bb1675bc32c769468b40469a2a3f1cc6536cd2b',
                        'source_host': 'haiants.vn',
                        'description': 'Exact statement-page issuer literal agreed by retained Claude and '
                                       'ChatGPT blind readings',
                        'reader_files': [{'relative_path': 'blind-input-hah-fy2025-p13/claude/claude-reader.raw.json',
                                          'sha256': '6c1a076eab659c46d8b4f99917d66b8faca035a6eba55148cd3b2401b06f047d'},
                                         {'relative_path': 'blind-input-hah-fy2025-p13/chatgpt/chatgpt-reader.raw.json',
                                          'sha256': 'c98c12f150b0568cadc47d537f558a20bc69526501cafb44257ce1dbfeb7c145'}]}},
        {'literal': 'CÔNG TY CỔ PHẦN VẬN TẢI VÀ XẾP DỠ HẢI AN',
         'provenance': {'document_sha256': 'a36ae93c0c3434d3e47c36f5d6de07ca6623db880b01c850a0bdd9855a45837b',
                        'source_page': 12,
                        'image_sha256': '88ca5b22455b8b6b3d4758c8686860a585cf956ac0ea0bd35d66f5f26a19dd4b',
                        'source_host': 'haiants.vn',
                        'description': 'Exact statement-page issuer literal agreed by retained Claude and '
                                       'ChatGPT blind readings',
                        'reader_files': [{'relative_path': 'blind-input-hah-2025h1-p12/claude/claude-reader.raw.json',
                                          'sha256': '9417ba392697766847d29872315fa128c68e04408608ca5d782bdfa40c1919a6'},
                                         {'relative_path': 'blind-input-hah-2025h1-p12/chatgpt-r2/chatgpt-reader.raw.json',
                                          'sha256': '7cdc2915f5065a8ab22e46510d14fe60c5a48e3dcc4ce42bbe346fad353baaeb'}]}},
        {'literal': 'CÔNG TY CỔ PHẦN VẬN TẢI VÀ XẾP DỠ HẢI AN',
         'provenance': {'document_sha256': '913d92bec2564ad9efa15db114e34419d21e4b466bf51964ddca941682cf7291',
                        'source_page': 13,
                        'image_sha256': '98c8c1933a343a7049466db937e6399cc3d6076bc3efefade9a1647316370ec6',
                        'source_host': 'haiants.vn',
                        'description': 'Exact statement-page issuer literal agreed by retained Claude and '
                                       'ChatGPT blind readings',
                        'reader_files': [{'relative_path': 'blind-input-hah-2026h1-p13/claude/claude-reader.raw.json',
                                          'sha256': 'd6e89317797626b68fe095eb44af9f38d630cd0e081bcbc8976c7d3f73bdbad0'},
                                         {'relative_path': 'blind-input-hah-2026h1-p13/chatgpt/chatgpt-reader.raw.json',
                                          'sha256': 'a8f0a08ead429e90caeabad413af1dc17744d303f2e4e6cb747bca544059ca71'}]}},
    ),
    'BWE': (
        {'literal': 'Công ty CP - Tổng Công ty Nước - Môi trường Bình Dương',
         'provenance': {'document_sha256': '9e028ec5b6e612767068d0ba25c83c1350a86e55753a61fda7625fae26c4dcf9',
                        'source_page': 12,
                        'image_sha256': 'fa7896a2f4a352ff7435c9b2daf0b8269d3b293b38ef7661798a1f061588902b',
                        'source_host': 'www.biwase.com.vn',
                        'description': 'Exact statement-page issuer literal agreed by retained Claude and '
                                       'ChatGPT blind readings',
                        'reader_files': [{'relative_path': 'blind-input-bwe-fy2025-p12/claude/claude-reader.raw.json',
                                          'sha256': 'c64abe2e55ba35242953de9bcb7bf4418bc5c632300e392008a0198c0454d18f'},
                                         {'relative_path': 'blind-input-bwe-fy2025-p12/chatgpt/chatgpt-reader.raw.json',
                                          'sha256': '1a228f64043041541536363c4e932c2766f34a1b4c5f7b932b3063b6f40f80e9'}]}},
        {'literal': 'Công ty CP - Tổng Công ty Nước - Môi trường Bình Dương',
         'provenance': {'document_sha256': 'acb48684fcf4d14266f2bd0ca684331d7b69e2953a50f612e9004cb055cb92c8',
                        'source_page': 12,
                        'image_sha256': 'e7950cad0cc38eb6e9e4ed16f7d12a21eb168f8ac4e62f5428db933f6dba17a6',
                        'source_host': 'www.biwase.com.vn',
                        'description': 'Exact statement-page issuer literal agreed by retained Claude and '
                                       'ChatGPT blind readings',
                        'reader_files': [{'relative_path': 'blind-input-bwe-2025h1-p12/claude/claude-reader.raw.json',
                                          'sha256': '0af0725d2f6c2a5fd9cea83a5ebc44b4e1e6fee87cdcca459f6faaa5275f8058'},
                                         {'relative_path': 'blind-input-bwe-2025h1-p12/chatgpt/chatgpt-reader.raw.json',
                                          'sha256': '172e64c3f4c845dad1c42e7dfe0c5b88aa590f7a36e33f6c13d5e54a25092749'}]}},
        {'literal': 'Công ty CP - Tổng Công ty Nước - Môi trường Bình Dương',
         'provenance': {'document_sha256': '6e19b66271a6cf87be38791ffb2c29985b13930b12dfd72399909ffde2c9cdef',
                        'source_page': 12,
                        'image_sha256': '259e24d077202a6cff9e7c6040142c7fc16444cd42f99d0ecda481bbc63a8ee2',
                        'source_host': 'www.biwase.com.vn',
                        'description': 'Exact statement-page issuer literal agreed by retained Claude and '
                                       'ChatGPT blind readings',
                        'reader_files': [{'relative_path': 'blind-input-bwe-2026h1-p12/claude/claude-reader.raw.json',
                                          'sha256': '24b8185dc72ef2cee49bba18a7cf1b9f4f7b078afc59debb360932468ebae05a'},
                                         {'relative_path': 'blind-input-bwe-2026h1-p12/chatgpt/chatgpt-reader.raw.json',
                                          'sha256': 'aabf4bf5d0c543d873ab1b5a6de7ddbfda935a9c30b40f8b83398be6d3e7c240'}]}},
    ),
    "POW": ({"literal": "PETROVIETNAM POWER CORPORATION",
             "provenance": {"document_sha256": "3b06425b3d79803f9e7bf634c8bfd600f4aca998bcd15dabcd95ffb04877afbc",
                            "source_page": 7, "source_host": "pvpower.vn",
                            "description": "English charter amendment 8, foreign language name"}},),
}


def exact_registered_issuer_name(ticker: str, literal: str) -> bool:
    return any(item["literal"] == literal for item in EXACT_REGISTERED_ISSUER_NAMES.get(ticker, ()))


def retained_issuer_name_matches(row, proof, text: str) -> bool:
    """Exact registered originals may print their full legal name instead of ticker.

    No fuzzy letters, abbreviation, host or caller-selected issuer establishes this.
    The original bytes, source manifest and issuer host remain separately required.
    """
    from stocklookup_core.evidence.financial_row_identity import _identity_fold
    names = {'HPG': 'cong ty co phan tap doan hoa phat',
             'PNJ': 'cong ty co phan vang bac da quy phu nhuan',
             'VRE': 'cong ty co phan vincom retail',
             'NVL': 'cong ty co phan tap doan dau tu dia oc no va'}
    sha = row.get('document_sha256')
    layout = layout_for(sha) or {}
    ref = row.get('ocr_layout_proof') or {}
    ticker = row.get('ticker')
    exact_name = any(re.search(r'(?<!\w)' + re.escape(item['literal']) + r'(?!\w)', text)
                     for item in EXACT_REGISTERED_ISSUER_NAMES.get(ticker, ()))
    return bool(proof and layout.get('ticker') == ticker
                and not verify_proof_identity(proof, document_sha256=sha, proof_sha256=ref.get('proof_sha256'))
                and (exact_name or (ticker in names and re.search(r'\b'+re.escape(names[ticker])+r'\b', _identity_fold(text)))))


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
                **({'native_failure_evidence': page['native_failure_evidence']}
                   if page.get('native_failure_evidence') else {}),
                "tokens": [{k: t.get(k) for k in ("token_id", "raw_token_order", "text", "x0", "x1", "top", "bottom",
                                                    "tsv_hierarchy", "source_text", "glyph_evidence")
                            if k != "glyph_evidence" or k in t} for t in ocr["tokens"]],
            }
    if len(engine) != 1 or len(config) != 1:
        raise ValueError("OCR_PROOF_ENGINE_OR_CONFIG_NOT_UNIQUE")
    body = {"contract_version": CONTRACT_VERSION, "document_sha256": document_sha256, "layout": layout["layout"],
            "engine_version": engine.pop(), "ocr_config": json.loads(config.pop()), "pages": pages}
    if any(t.get("glyph_evidence") for p in pages.values() for t in p["tokens"]):
        body["numeric_glyph_policy"] = {"contract_version": BASELINE_TWO_CONTRACT,
            "tolerance_fraction": BASELINE_TWO_TOLERANCE, "minimum_ascii_reference_digits": 3,
            "coordinate_tolerance_pixels": 1, "normalized_characters": {"²": "2"}}
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
    for page in (proof.get("pages") or {}).values():
        for token in page.get("tokens") or []:
            glyph = token.get("glyph_evidence")
            if glyph and (not isinstance(glyph, Mapping)
                          or glyph.get("engine_version") != proof.get("engine_version")
                          or glyph.get("config") != proof.get("ocr_config")):
                reasons.append("OCR_GLYPH_ENGINE_OR_CONFIG_MISMATCH")
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
    image_sha = ((proof.get("pages") or {}).get(str(source_page)) or {}).get("rendered_image_sha256")
    current_amounts = [t for t in on_row if _in_band(t, cur_band)
                       and _AMOUNT.match(baseline_two_value(t, image_sha)[0])]
    if len(current_amounts) != 1:
        reasons.append("ADJACENT_AMOUNT_AMBIGUITY")
    comparative = [t for t in on_row if _in_band(t, cmp_band)
                   and _AMOUNT.match(baseline_two_value(t, image_sha)[0])]
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
        numeric_raw, _ = baseline_two_value(token, image_sha)
        if parse_amount(numeric_raw) * int(unit_scale) != int(value):
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
