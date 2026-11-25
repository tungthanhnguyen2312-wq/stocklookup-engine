"""Retain an operator-supplied finite VSDC notice CSV through the governed acquirer."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.evidence.official_document_acquisition import (
    acquire, validate_vsdc_notice_list, _declared_interval,
)
from stocklookup_core.evidence.official_source_registry import load_registry

CLASSES = {"registration_change": "corporate_action_notice",
           "record_date_notice": "last_registration_date_notice"}
COLUMNS = {"ticker", "notice_kind", "url", "published", "title", "venue_from_crawl"}


def plan(path: Path, *, registry=None) -> tuple[list[dict], dict]:
    registry = load_registry() if registry is None else registry
    requests, rejected = [], []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not COLUMNS.issubset(reader.fieldnames or []):
            raise ValueError("CSV_REQUIRED_COLUMNS_MISSING")
        total = 0
        for number, row in enumerate(reader, 2):
            total += 1
            try:
                if None in row or any(row.get(key) is None for key in COLUMNS):
                    raise ValueError("CSV_ROW_WIDTH_INVALID")
                published = datetime.strptime(row["published"], "%d/%m/%Y").date()
                if not row["title"].strip():
                    raise ValueError("TITLE_EMPTY")
                if row["notice_kind"] not in CLASSES:
                    raise ValueError("UNSUPPORTED_NOTICE_KIND:" + row["notice_kind"])
                spec = {"ticker": row["ticker"].strip().upper(), "source_id": "vsdc",
                        "document_class": CLASSES[row["notice_kind"]],
                        "reporting_period": str(published.year), "canonical_url": row["url"],
                        # Crawl date has day precision only: never promote to publication time.
                        "discovery_provenance": {"method": "OPERATOR_FINITE_VSDC_NOTICE_CSV",
                            "csv_row": number, "published_date_from_crawl": row["published"],
                            "title": row["title"], "venue_from_crawl": row["venue_from_crawl"],
                            "authority": "DISCOVERY_ONLY_NOT_VENUE_OR_PUBLICATION_PROOF"}}
                validate_vsdc_notice_list([spec], registry=registry)
                requests.append(spec)
            except (ValueError, KeyError) as exc:
                rejected.append({"row": number, "ticker": row.get("ticker"), "reason": str(exc)})
    count = len(requests)
    interval = _declared_interval(registry, "vsdc")
    return requests, {"rows": total, "planned_requests": count,
        "unique_tickers": len({r["ticker"] for r in requests}), "rejected_rows": rejected,
        "minimum_wall_seconds": max(0, count - 1) * interval,
        "minimum_interval_seconds": interval,
        "timing_basis": "UNCACHED_ONE_ATTEMPT_NO_REDIRECTS_EXCLUDES_HTTP_DURATION",
        "execution_allowed": count > 0 and not rejected}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urls", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    requests, summary = plan(args.urls)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if not summary["execution_allowed"]:
        return 2
    if not args.dry_run:
        result = acquire(requests, args.destination, vsdc_operator_notice_list=True)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if all(row["state"] in {"retained", "cached_valid"} for row in result["outcomes"]) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
