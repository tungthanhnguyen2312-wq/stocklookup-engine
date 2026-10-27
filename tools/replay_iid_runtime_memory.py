"""Retained-only enrichment qualification; never run the Daily/publication entrypoint.

The parent uses the production 7/8-GiB guard and its real reserve probes. The
child permits writes only below a new experiment directory and denies network
and subprocess creation. No T0 capture, acquisition, or publication is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import CodeType

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def file_digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def reference_iid(args, pipeline, level2, sandbox):
    """Run the unchanged baseline builder over its persisted, verified inputs.

    This separate parity phase has no obsolete engine/semantic/raw input graphs
    from orchestration. It is explicitly not a whole-enrichment capacity proof.
    """
    from stocklookup_core.decision.integrated_investment_decision_product import build_artifact
    from stocklookup_core.tactical.market_wide_relative_volume_research import build_artifact as volume
    from daily_official_liquidity_rollforward import load_for_daily_consumer, status_path
    paths = level2.session_artifact_paths(args.reference_root, args.session)
    load = lambda key: pipeline._load(paths[key])
    snapshot = load("exact_session_snapshot")
    requested_at = snapshot["requested_at"]
    participation = volume(candidates=sorted(snapshot["records"]), records=snapshot["records"],
        session=args.session, requested_at=f"{args.session}T15:00:00+07:00")
    del snapshot
    financial = load("financial_analysis_product")
    opportunity = load("opportunity_prioritization")
    queue, _ = pipeline.resolve_current_session_priority_queue(
        args.session, opportunity=opportunity, triage=load("session_triage"))
    official = load_for_daily_consumer(session=args.session,
        candidate_paths=(paths["official_liquidity"],),
        component_status_paths=(status_path(paths["official_liquidity"]),), allow_network=False)
    artifact = build_artifact(session=args.session, requested_at=requested_at,
        technical_structure_artifact=load("market_structure_breakout_v3_projection"),
        financial_analysis_artifact=financial["financial_analysis_product"],
        financial_peer_materialization_artifact=financial,
        historical_context_artifact=pipeline._load(pipeline.enrichment_output_path(args.reference_root, args.session, "historical_context")),
        current_valuation_artifact=load("current_valuation_evaluated"),
        relative_volume_artifact=participation, market_sector_artifact=load("sector_leadership"),
        legacy_decision_artifact=opportunity, priority_queue_artifact=queue,
        technical_coverage_disposition_artifact=load("technical_coverage_disposition"),
        momentum_artifact=load("tactical_momentum_context"),
        tactical_confirmation_artifact=load("tactical_confirmation_context"),
        tactical_boundaries_artifact=load("tactical_confirmation_invalidation_boundaries"),
        corporate_intelligence_artifact=pipeline._load(pipeline.enrichment_output_path(args.reference_root, args.session, "corporate_intelligence_axis")),
        operational_fundamental_integration_artifact=load("operational_fundamental_context_integration"),
        liquidity_research_artifact=load("liquidity_research"),
        official_liquidity_artifact=official.get("artifact"),
        entity_applicability_artifact=load("current_research_entity_applicability"))
    destination = level2.session_artifact_paths(sandbox, args.session)["integrated_investment_decision_product"]
    pipeline._write_json(destination, artifact, capture_iid_receipt=True)
    return {"integrated_investment_decision_product": {"status": "BUILT", "artifact": artifact}}


def child(args):
    if args.code_root is not None:
        sys.path.insert(0, str(args.code_root.resolve()))
    import psutil
    import canonical_post_close_pipeline as pipeline
    import daily_session_level2_package as level2

    out = args.experiment.resolve()
    sandbox = out / "sandbox"
    sandbox.mkdir()
    (sandbox / "config").mkdir()
    shutil.copy2(args.registry, sandbox / "config/daily_research_session_input_registry.json")
    paths = level2.session_artifact_paths(args.evidence, args.session)
    # Include exact frozen optional selections as well as canonical session inputs.
    selected = list(paths.values())
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    selection = (registry.get("sessions") or {}).get(args.session) or {}
    selected += [args.evidence / row["path"] for row in selection.values()
                 if isinstance(row, dict) and row.get("path")]
    copied = {}
    for source in selected:
        relative = source.relative_to(args.evidence)
        if not source.is_file():
            source = args.registry.resolve().parents[1] / relative
        if not source.is_file() or "prospective-" in source.parent.name:
            continue
        target = sandbox / relative
        if not target.resolve().is_relative_to(sandbox.resolve()):
            raise ValueError("REPLAY_INPUT_PATH_ESCAPES_SANDBOX")
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        before = file_digest(source)
        shutil.copy2(source, target)
        assert file_digest(target) == before
        copied[str(source)] = {"bytes": source.stat().st_size, "sha256": before}
    (out / "input-manifest.json").write_text(json.dumps(copied, indent=2), encoding="utf-8")
    pipeline.frozen_optional_session_inputs(sandbox, args.session)

    # All retained reads, including sources discovered by governed resolvers, are
    # fingerprinted before the first read. Protect production via the audit hook.
    reads = {}
    violations = []
    auditing = False
    def refuse(reason):
        nonlocal auditing
        violations.append(reason)
        auditing = True
        try:
            (out / "offline-violations.json").write_text(json.dumps(violations), encoding="utf-8")
        finally:
            auditing = False
        raise RuntimeError(reason)
    def audit(event, values):
        nonlocal auditing
        if auditing:
            return
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            refuse("OFFLINE_REPLAY_FORBIDDEN:" + event)
        if event == "sqlite3.connect" and "mode=ro" not in str(values[0]):
            if not Path(values[0]).resolve().is_relative_to(out):
                refuse("OFFLINE_REPLAY_SQLITE_REQUIRES_READ_ONLY_URI")
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(values[0])).resolve()
            flags = values[2]
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not path.is_relative_to(out):
                refuse("OFFLINE_REPLAY_WRITE_OUTSIDE_EXPERIMENT:" + str(path))
            if not writing and path.is_file() and path.is_relative_to(args.evidence) and str(path) not in reads:
                auditing = True
                try:
                    reads[str(path)] = {"bytes": path.stat().st_size, "sha256": file_digest(path)}
                    (out / "source-reads.json").write_text(json.dumps(reads, indent=2), encoding="utf-8")
                finally:
                    auditing = False
        if event in {"os.remove", "os.mkdir", "os.rmdir", "os.rename"}:
            for value in values[:2] if event == "os.rename" else values[:1]:
                if isinstance(value, (str, bytes, os.PathLike)) and not Path(os.fsdecode(value)).resolve().is_relative_to(out):
                    refuse("OFFLINE_REPLAY_MUTATION_OUTSIDE_EXPERIMENT:" + str(value))
    sys.addaudithook(audit)
    corporate_rollforward = None
    if args.corporate_overlay is not None:
        from corporate_currency_rollforward import CorporateCurrencyRollforwardResult
        from current_official_event_context import _verify
        overlay = pipeline._load(args.corporate_overlay)
        _verify(overlay, "RETAINED_CURRENT_CORPORATE_OVERLAY")
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        corporate_rollforward = CorporateCurrencyRollforwardResult(
            encode(overlay["receipt"]), encode(overlay["official_event_context"])
            if overlay.get("official_event_context") is not None else None, None)
    held_acquisition = None
    if args.hold_acquisition:
        held_acquisition = pipeline._load(level2.session_artifact_paths(sandbox, args.session)["exact_session_snapshot"])
    process = psutil.Process()
    started = time.perf_counter()
    trace_file = (out / "stages.jsonl").open("w", encoding="utf-8", buffering=1)
    def report(stage, **extra):
        memory = process.memory_info()
        trace_file.write(json.dumps({"stage": stage, "elapsed_seconds": round(time.perf_counter()-started, 3),
            "rss_bytes": memory.rss, "private_bytes": memory.private,
            "peak_rss_bytes": memory.peak_wset, "peak_committed_bytes": memory.peak_pagefile, **extra}) + "\n")
    # Python 3.12+ code-local monitoring does not trace builder interiors or
    # JSON encoder generator resumptions. A global trace greatly distorts them.
    code = next(value for value in pipeline.build_enrichment_components.__code__.co_consts
                if isinstance(value, CodeType) and value.co_name == "_integrated_investment_decision_product")
    codes = [code]
    if args.reference_root is not None:
        import market_wide_historical_research_context as history
        from stocklookup_core.valuation import current_research_valuation_context as valuation
        from stocklookup_core.financial import financial_analysis_product_projection as financial
        codes = [history.content_identity.__code__, valuation._research_identity.__code__, financial._identity.__code__]
    monitor = getattr(sys, "monitoring", None)
    if monitor is not None:
        monitor.use_tool_id(5, "retained-iid-memory")
        monitor.register_callback(5, monitor.events.LINE,
            lambda code, line: report(("VERIFY:" + Path(code.co_filename).name + ":" if args.reference_root else "IID:") + str(line)))
        for code in codes:
            monitor.set_local_events(5, code, monitor.events.LINE)
    def progress(value):
        report(value.get("subtask"), status=value.get("status"))
    try:
        if args.reference_root is not None:
            report("IID_REFERENCE_BEGIN")
            result = reference_iid(args, pipeline, level2, sandbox)
        else:
            result = pipeline.build_enrichment_components(sandbox, args.session,
                artifact_root=sandbox, retained_evidence_root=args.evidence,
                output_root=sandbox, runtime_root=args.runtime,
                corporate_currency_rollforward=corporate_rollforward,
                progress_callback=progress)
    finally:
        if monitor is not None:
            for code in codes:
                monitor.set_local_events(5, code, 0)
            monitor.register_callback(5, monitor.events.LINE, None)
            monitor.free_tool_id(5)
    if held_acquisition is not None:
        report("HELD_ACQUISITION", records=len(held_acquisition.get("records") or {}))
    if violations:
        raise RuntimeError("OFFLINE_REPLAY_VIOLATIONS:" + str(violations))
    iid = result.get("integrated_investment_decision_product") or {}
    report("FINISHED", outcomes={key: {k:v for k,v in row.items() if k in {"status", "reason"}}
                                for key,row in result.items() if isinstance(row, dict)})
    if iid.get("status") != "BUILT":
        raise RuntimeError("IID_NOT_BUILT:" + str(iid.get("reason")))
    artifact = iid["artifact"]
    summary = {"artifact_identity": artifact["artifact_identity"], "records": len(artifact["records"]),
               "status": "COMPLETED", "peak_committed_bytes": process.memory_info().peak_pagefile,
               "mode": "IID_REFERENCE_ONLY" if args.reference_root is not None else "FULL_ENRICHMENT",
               "held_acquisition": args.hold_acquisition,
               "code_root": str(args.code_root or ROOT)}
    (out / "child-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    trace_file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--session", default="2026-10-26")
    parser.add_argument("--code-root", type=Path, help="Optional baseline checkout; only analytical code is selected")
    parser.add_argument("--hold-acquisition", action="store_true", help="Retain the caller-owned acquisition snapshot throughout enrichment")
    parser.add_argument("--corporate-overlay", type=Path, help="Exact retained invocation overlay; no discovery/acquisition")
    parser.add_argument("--reference-root", type=Path, help="Parity only: call baseline IID over persisted enrichment inputs")
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.reference_root is not None and args.code_root is None:
        parser.error("--reference-root requires explicit --code-root for the baseline builder")
    if args.child:
        child(args)
        return
    for source in (args.evidence, args.runtime, args.registry.resolve().parents[1]):
        if args.experiment.resolve().is_relative_to(source.resolve()):
            raise ValueError("EXPERIMENT_MUST_BE_OUTSIDE_PROTECTED_SOURCE_ROOTS")
    args.experiment.mkdir(parents=True, exist_ok=False)
    from stocklookup_core.acquisition import feedback_resource_guard as guard
    from tools.check_owner_daily_host_preflight import windows_memory
    diagnostics = {}
    started = time.perf_counter()
    def probe():
        if time.perf_counter() - started > 1800:
            raise OSError("OFFLINE_REPLAY_DEADLINE_1800_SECONDS")
        return windows_memory()
    try:
        returncode = guard.run_capacity_guarded(
            [sys.executable, "-B", "-u", str(Path(__file__).resolve()), *sys.argv[1:], "--child"],
            cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            memory_probe=probe, on_diagnostics=diagnostics.update)
        diagnostics.update(returncode=returncode)
    except OSError as exc:
        diagnostics.update(reason=str(exc), returncode=1)
    diagnostics["wall_seconds"] = round(time.perf_counter()-started, 3)
    (args.experiment / "guard-result.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics), flush=True)
    raise SystemExit(diagnostics["returncode"])


if __name__ == "__main__":
    main()
