"""Materialize the read-only market-gate decision-quality evaluation (MARKET_GATE_DECISION_QUALITY_V1).

Never runs Daily, never acquires provider data and never writes under the retained root. Decision
facts come from each completed session's retained Daily brief, bound to its sealed T0 index; price
facts come from each exact-session snapshot, read one at a time and reduced to its own-session
close rows. Prints only counts and identities unless --output-dir is given.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import daily_session_level2_package as level2  # noqa: E402
import empirical_setup_outcome_calibration as calibration  # noqa: E402
import integrated_decision_prospective_feedback as feedback_bridge  # noqa: E402
import prospective_decision_outcome_feedback as feedback  # noqa: E402
import prospective_t0_seal_index as seal  # noqa: E402
from retained_evidence_catalog import guard_path  # noqa: E402

_T0_KEYS = ("ticker", "as_of_session", "decision_identity", "posture_condition_class", "tactical_phase", "trigger", "invalidation")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_immutable(path: Path, text: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def qualified_session_operations(root: Path) -> dict[str, dict]:
    """The same completed-session predicate as resolve_completed_market_observations."""
    operations = feedback._operation_manifests(root)
    result = {}
    for link in feedback._handoff_bundles(root, operations):
        manifest = (link.get("operation") or {}).get("manifest") or {}
        if (link["producer_completed"] and link["resolved_completed_session"] == link["session"] and
                manifest.get("market_session") == link["session"] and manifest.get("generation_context") == feedback._GENUINE_CONTEXT):
            if link["session"] in result and result[link["session"]]["operation_identity"] != link["operation_identity"]:
                raise ValueError("AMBIGUOUS_COMPLETED_OPERATION:" + link["session"])
            result[link["session"]] = link
    return result


def _seal_index(root: Path, session: str, operation_identity: str):
    found = []
    for path in sorted((root / "operations-review" / "prospective-decision-retention-v1" / session).glob("*/prospective_t0_seal_index.json")):
        index = seal.verify(_load(path), "prospective_t0_seal_index")
        receipt = seal.verify(_load(path.parent / "prospective_t0_snapshot_write_receipt.json"), "prospective_t0_snapshot_write_receipt")
        if receipt["index_identity"] != index["artifact_identity"] or receipt["session"] != session:
            raise ValueError("T0_SEAL_RECEIPT_BINDING_INVALID:" + session)
        if index.get("operation_identity") == operation_identity:
            found.append(index)
    if len(found) > 1:
        raise ValueError("AMBIGUOUS_T0_SEAL_INDEX:" + session)
    return found[0] if found else None


def _gated_t0_records(operation_dir: Path, tickers: set[str]) -> dict[str, dict]:
    """Stream the session's own delivery NDJSON once; keep only the gated tickers' decision rows."""
    path = operation_dir / "ai_research_full_universe.ndjson"
    records: dict[str, dict] = {}
    if not tickers or not path.is_file():
        return records
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("ticker") in tickers:
                decision = row.get("integrated_decision_v1") or {}
                if row["ticker"] in records:
                    raise ValueError("DUPLICATE_T0_DELIVERY_ROW:" + row["ticker"])
                records[row["ticker"]] = {key: decision.get(key) for key in _T0_KEYS}
    return records


def build(root: Path, *, policy_version: str, evaluated_as_of: str | None = None) -> tuple[dict, dict]:
    root = Path(root).resolve()
    links = qualified_session_operations(root)
    inputs, sources = [], {"briefs": {}, "seal_indexes": {}, "t0_delivery_rows": {}, "price_snapshots": {}, "missing": []}
    for session, link in sorted(links.items()):
        operation_dir = root / "operations-review" / "daily-research-session-operations-v1" / session / link["operation_identity"].split(":")[-1]
        brief_path = operation_dir / "daily_integrated_decision_brief_artifact.json"
        if not brief_path.is_file():
            sources["missing"].append({"session": session, "reason": "BRIEF_ARTIFACT_NOT_RETAINED"})
            continue
        guard_path(root, brief_path, session_identity=session)
        brief = _load(brief_path)
        if (brief.get("daily_operation_identity") != link["operation_identity"] or
                brief.get("integrated_investment_decision_product_identity") != link["artifact_identity"]):
            raise ValueError("BRIEF_OPERATION_BINDING_MISMATCH:" + session)
        rows = (brief.get("daily_integrated_decision_brief") or {}).get("decision_surface_index", {}).get("rows") or []
        gated = {row["ticker"] for row in rows if row.get("posture_condition_class") == calibration.MARKET_GATE_CONDITION_CLASS}
        index = _seal_index(root, session, link["operation_identity"])
        t0_records = _gated_t0_records(operation_dir, gated)
        inputs.append(calibration.market_gate_session_input(brief, seal_index=index, t0_records=t0_records))
        sources["briefs"][session] = brief.get("artifact_identity")
        sources["seal_indexes"][session] = (index or {}).get("artifact_identity")
        if gated:
            sources["t0_delivery_rows"][session] = sorted(t0_records)
        del brief
    scoped = sorted(item["session"] for item in inputs if item["policy_version"] == policy_version)
    if not scoped:
        raise ValueError("NO_DECISION_SESSION_IN_POLICY_SCOPE")
    chain = feedback_bridge.governed_session_chain(root, cohort_session=scoped[0])
    price_sessions = sorted(day for day in set(chain) | {item["session"] for item in inputs} if day >= scoped[0])
    snapshots = {}
    for session in price_sessions:
        path = level2.session_artifact_paths(root, session)["exact_session_snapshot"]
        if not path.is_file():
            sources["missing"].append({"session": session, "reason": "EXACT_SESSION_PRICE_SNAPSHOT_NOT_RETAINED"})
            continue
        guard_path(root, path, session_identity=session)
        snapshot = _load(path)
        if snapshot.get("resolved_completed_session") == session:
            snapshots[session] = calibration.project_exact_session_price_rows(snapshot)
            sources["price_snapshots"][session] = snapshot.get("snapshot_identity")
        else:
            sources["missing"].append({"session": session, "reason": "PRICE_SNAPSHOT_SESSION_MISMATCH"})
        del snapshot
        gc.collect()
    evaluation = calibration.build_market_gate_evaluation(
        inputs, chain=chain, price_snapshots=snapshots, policy_version=policy_version,
        evaluated_as_of=evaluated_as_of or max(item["session"] for item in inputs))
    return evaluation, sources


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="retained evidence root (read-only)")
    parser.add_argument("--output-dir", help="write evaluation, Vietnamese summary and source receipt here")
    parser.add_argument("--policy-version", default="v2")
    parser.add_argument("--evaluated-as-of")
    args = parser.parse_args(argv)
    evaluation, sources = build(Path(args.root), policy_version=args.policy_version, evaluated_as_of=args.evaluated_as_of)
    summary = {"artifact_identity": evaluation["artifact_identity"], "cohort_identity": evaluation["cohort_identity"],
               "case_counts": evaluation["case_counts"], "gate_episodes": [(e["session"], e["gated_count"]) for e in evaluation["gate_episodes"]],
               "evidence_verdict": evaluation["evidence_verdict"]["state"], "missing": sources["missing"]}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if args.output_dir:
        out = Path(args.output_dir)
        _write_immutable(out / "market_gate_decision_quality.json", json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _write_immutable(out / "market_gate_decision_quality_vi.md", calibration.render_market_gate_summary_vi(evaluation))
        _write_immutable(out / "market_gate_decision_quality_sources.json", json.dumps(
            {"evaluation_identity": evaluation["artifact_identity"], **sources}, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
