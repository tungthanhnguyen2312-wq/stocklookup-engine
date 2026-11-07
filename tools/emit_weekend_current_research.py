"""Emit the current-research artifacts for the 2026-11-07 successor chain.

The HPG PDF stays outside git. When the retained file is on this machine the
emitter checks its SHA-256 before writing. Nothing here is an official fact
and nothing is bound to the sealed 2026-11-06 Daily.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.decision.market_close_current_research import (  # noqa: E402
    current_research_artifact, weekend_source_closures_20261107,
)
from stocklookup_core.financial.q3_2026_successor_research import (  # noqa: E402
    HPG_CONSOLIDATED_Q3_BYTES, HPG_CONSOLIDATED_Q3_SHA256, hpg_consolidated_statement_shadow, issuer_blocker,
    evf_reviewed_statement_shadow, pan_consolidated_statement_shadow, pow_consolidated_statement_shadow,
    ssi_consolidated_statement_shadow,
)
from stocklookup_core.valuation.common_shareholder_book_comparison import research_dependency  # noqa: E402

OBSERVED_AT = "2026-11-07T10:51:54+07:00"
RETAINED_PDF = Path(r"T:\StockLookup\scratch\grok-weekend-continuation-20261107\hpg-q3-2026-consolidated.pdf")
POSTHOC_BENCHMARK = {
    "index": "VNINDEX", "session": "2026-11-06", "close": 1725.36, "previous_close": 1740.73,
    "previous_session": "2026-11-05",
    "source_identity": "dnse_index_return_series/4cf91c602cb69b01a5acfb1bf6e772806a5ee09f7b22d9a0d216f8b78340511e",
    "knowledge_available_at": "2026-11-07T09:49:56+07:00",
    "authority": "DNSE_CURRENT_STATE_REPUBLISHED_INDEX_NOT_HOSE_ADMINISTRATOR",
}


def _check_retained_pdf() -> None:
    if not RETAINED_PDF.is_file():
        return
    payload = RETAINED_PDF.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != HPG_CONSOLIDATED_Q3_SHA256 or len(payload) != HPG_CONSOLIDATED_Q3_BYTES:
        raise SystemExit("RETAINED_PDF_DOES_NOT_MATCH")


def q3_artifact(*, pan_pdf: Path | None = None, pan_separate_pdf: Path | None = None,
                 pow_pdf: Path | None = None, evf_pdf: Path | None = None,
                 ssi_pdf: Path | None = None, hpg_alternate_pdf: Path | None = None) -> dict:
    hpg = hpg_consolidated_statement_shadow(
        observed_at=OBSERVED_AT,
        alternate_pdf_bytes=hpg_alternate_pdf.read_bytes() if hpg_alternate_pdf else None,
    )
    pan = (pan_consolidated_statement_shadow(
        pdf_bytes=pan_pdf.read_bytes(),
        separate_pdf_bytes=pan_separate_pdf.read_bytes() if pan_separate_pdf else None,
    ) if pan_pdf else research_dependency(ticker="PAN"))
    pow_statement = (pow_consolidated_statement_shadow(pdf_bytes=pow_pdf.read_bytes())
                     if pow_pdf else issuer_blocker(ticker="POW", reason_codes=[
                         "EXACT_Q3_PDF_LOCATED_SOURCE_BYTES_UNVERIFIED"]))
    ssi = (ssi_consolidated_statement_shadow(pdf_bytes=ssi_pdf.read_bytes()) if ssi_pdf else issuer_blocker(
        ticker="SSI", reason_codes=["EXACT_Q3_PDF_LOCATED_SOURCE_BYTES_UNVERIFIED"]))
    issuers = {
        "HPG": hpg,
        "PAN": pan,
        "SSI": ssi,
        "EVF": (evf_reviewed_statement_shadow(pdf_bytes=evf_pdf.read_bytes()) if evf_pdf else issuer_blocker(
            ticker="EVF", reason_codes=["EXACT_Q3_DISCLOSURE_LOCATED_ISSUER_HOST_NOT_ADMITTED"])),
        "POW": pow_statement,
    }
    observation_count = sum(len(item.get("observations", [])) for item in issuers.values() if isinstance(item, dict))
    return {
        "contract_version": "q3_2026_successor_research/v1",
        "knowledge_available_at": OBSERVED_AT,
        "session_binding": "NOT_A_SEALED_SESSION_FACT",
        "official_fact_admitted_count": 0,
        "shadow_row_count": hpg["shadow_row_count"],
        "observation_count": observation_count,
        "issuers": issuers,
    }


def main() -> int:
    _check_retained_pdf()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("q3_path", nargs="?", type=Path)
    parser.add_argument("market_path", nargs="?", type=Path)
    parser.add_argument("--pan-pdf", type=Path, help="Retained exact PAN consolidated Q3 filing")
    parser.add_argument("--pow-pdf", type=Path, help="Retained exact POW consolidated Q3 filing")
    parser.add_argument("--evf-pdf", type=Path, help="Retained exact EVF reviewed nine-month filing")
    parser.add_argument("--ssi-pdf", type=Path, help="Retained exact SSI consolidated Q3 filing")
    parser.add_argument("--pan-separate-pdf", type=Path, help="Retained exact PAN separate Q3 filing")
    parser.add_argument("--hpg-alternate-pdf", type=Path, help="HPG 29 Oct consolidated PDF, not a replacement")
    args = parser.parse_args()
    q3 = q3_artifact(
        pan_pdf=args.pan_pdf, pan_separate_pdf=args.pan_separate_pdf, pow_pdf=args.pow_pdf,
        evf_pdf=args.evf_pdf, ssi_pdf=args.ssi_pdf, hpg_alternate_pdf=args.hpg_alternate_pdf,
    )
    q3_path, market_path = args.q3_path, args.market_path
    market = current_research_artifact(benchmark=POSTHOC_BENCHMARK, closures=weekend_source_closures_20261107())
    text_q3 = json.dumps(q3, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    text_market = json.dumps(market, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if market_path:
        market_path.write_text(text_market, encoding="utf-8")
    if q3_path:
        q3_path.write_text(text_q3, encoding="utf-8")
        print(
            f"official_facts={q3['official_fact_admitted_count']} "
            f"shadow_rows={q3['shadow_row_count']} observations={q3['observation_count']}"
        )
        return 0
    sys.stdout.write(text_q3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
