"""Build the current-session candlestick sidecar from a retained P3F9B exact-session snapshot.

Read-only on the snapshot; writes ``candlestick_patterns.json`` + ``.js`` (and a small
``candlestick_patterns.component.json`` build_info component) into ``--out-dir`` only.

    python tools/build_current_session_candlestick_projection.py \
        --snapshot <retained>/p3f9b-market-wide-exact-session-scaleout-YYYYMMDD/p3f9b_mva_exact_session_snapshot.json \
        --session YYYY-MM-DD --out-dir <scratch dir>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.tactical import candlestick_patterns as engine  # noqa: E402
from stocklookup_core.tactical import current_session_candlestick_projection as projection  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ticker", action="append", default=None)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    try:
        payload = projection.build_projection(snapshot, session=args.session, tickers=args.ticker,
                                              workers=args.workers)
    except projection.CandlestickProjectionError as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    del snapshot
    args.out_dir.mkdir(parents=True, exist_ok=True)
    engine.atomic_write_snapshot(payload, args.out_dir / "candlestick_patterns.json",
                                 args.out_dir / "candlestick_patterns.js")
    component = projection.component_state(payload, args.session)
    (args.out_dir / "candlestick_patterns.component.json").write_text(
        json.dumps(component, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": component["status"], "session": args.session,
                      "coverage": payload["coverage"], "patterns": payload["summary"]["total_patterns"],
                      "projection_identity": payload["projection_identity"],
                      "seconds": round(time.perf_counter() - started, 1)}, ensure_ascii=False))
    return 0 if component["status"] == "CURRENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
