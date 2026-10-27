"""Bind a relocated Producer replay to the genuine read-only AI Core checkout.

Production sealing resolves the Consumer as the Producer checkout's sibling
``ai-core-private``. A scratch worktree is not that sibling. This module does
not change that production expression. It qualifies the workspace-profile
Consumer and, for a relocated root only, exposes it through a junction.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROFILE = Path(r"T:\StockLookup\production-v1\operator-config\workspace-v1.json")
PRODUCTION_PRODUCER = Path(r"T:\StockLookup\production-v1\stock-core-private")
CONSUMER_NAME = "ai-core-private"
ADMITTED_ORIGINS = ("stocklookup-ai-research", "ai-core-private")
CONTRACT = "current_daily_decision_research_contract"
SEAL_SOURCES = (
    ("canonical_daily_operation.py", '_git_head(root.parent / "ai-core-private")'),
    ("daily_research_session_operations.py", 'consumer_root = root.parent / "ai-core-private"'),
    ("daily_research_session_operations.py",
     "from builders.build_ticker_context import current_daily_decision_research_contract"),
    ("canonical_post_close_pipeline.py", '_git_head(root.parent / "ai-core-private")'),
    ("canonical_trusted_subset_release.py", 'from builders.build_ticker_context import verify_exact_session_bundle'),
)


class ConsumerDependencyError(RuntimeError):
    """The Producer-seal Consumer binding is missing, mismatched, or unqualified."""


def _reparse(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ConsumerDependencyError(f"CONSUMER_GIT_FAILED:{path}:{args[0]}:{detail}")
    return completed.stdout.strip()


def _origin_admitted(url: str) -> bool:
    tail = url.rstrip("/").removesuffix(".git")
    name = tail.split("/")[-1].split(":")[-1]
    return name in ADMITTED_ORIGINS


def qualify_consumer(profile_path: Path = PROFILE) -> dict:
    """The one production Consumer the workspace profile names. Fail closed otherwise."""
    if not profile_path.is_file() or _reparse(profile_path):
        raise ConsumerDependencyError("CONSUMER_PROFILE_MISSING:" + str(profile_path))
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        parent = Path(profile["parent"])
        declared = Path(profile["roles"]["consumer"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ConsumerDependencyError("CONSUMER_PROFILE_UNQUALIFIED:" + str(exc)) from exc
    if (profile.get("schema") != "stocklookup_workspace/v1" or not parent.is_absolute()
            or not parent.is_dir() or _reparse(parent)):
        raise ConsumerDependencyError("CONSUMER_PROFILE_UNQUALIFIED:parent")
    expected = (parent / CONSUMER_NAME).resolve()
    if (not declared.is_absolute() or declared.resolve() != expected or not expected.is_dir()
            or _reparse(expected)):
        raise ConsumerDependencyError("CONSUMER_PROFILE_UNQUALIFIED:" + str(declared))
    origin = _git(expected, "remote", "get-url", "origin")
    if not _origin_admitted(origin):
        raise ConsumerDependencyError("CONSUMER_ORIGIN_MISMATCH:" + origin)
    head = _git(expected, "rev-parse", "HEAD")
    if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
        raise ConsumerDependencyError("CONSUMER_HEAD_UNAVAILABLE:" + head)
    module = expected / "builders" / "build_ticker_context.py"
    if not module.is_file() or _reparse(module):
        raise ConsumerDependencyError("CONSUMER_CONTRACT_MISSING:" + str(module))
    source = module.read_text(encoding="utf-8")
    if f"def {CONTRACT}(" not in source or "def verify_exact_session_bundle(" not in source:
        raise ConsumerDependencyError("CONSUMER_CONTRACT_MISSING:symbol")
    local_imports = _local_builder_imports(source)
    missing = [name for name in local_imports if not _builder_module_exists(expected, name)]
    if missing:
        raise ConsumerDependencyError("CONSUMER_LOCAL_IMPORT_MISSING:" + ",".join(missing))
    return {
        "profile": str(profile_path),
        "consumer": str(expected),
        "origin": origin,
        "head": head,
        "branch": _git(expected, "rev-parse", "--abbrev-ref", "HEAD"),
        "module": str(module),
        "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "local_imports": local_imports,
    }


def _local_builder_imports(source: str) -> list[str]:
    """Non-stdlib modules the Consumer contract module imports. Same-path failures live here."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules = [node.module]
        for module in modules:
            top = module.split(".", 1)[0]
            if top in sys.stdlib_module_names or top in {"builders"}:
                if module.startswith("builders."):
                    names.append(module.split(".", 1)[1].split(".", 1)[0])
                continue
            names.append(top)
    return sorted(set(names))


def _builder_module_exists(consumer: Path, name: str) -> bool:
    base = consumer / "builders" / name
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def production_sibling_matches(qualified: dict) -> None:
    sibling = (PRODUCTION_PRODUCER.parent / CONSUMER_NAME).resolve()
    if sibling != Path(qualified["consumer"]).resolve() or _reparse(PRODUCTION_PRODUCER.parent / CONSUMER_NAME):
        raise ConsumerDependencyError("PRODUCTION_CONSUMER_MISMATCH:" + str(sibling))


def seal_sources_present(producer_root: Path) -> None:
    for relative, needle in SEAL_SOURCES:
        text = (producer_root / relative).read_text(encoding="utf-8")
        if needle not in text:
            raise ConsumerDependencyError("SEAL_SOURCE_EXPRESSION_CHANGED:" + relative)


def bind_relocated_consumer(producer_root: Path, genuine: Path) -> dict:
    """Point a relocated Producer's sibling expression at the genuine Consumer.

    A real directory is never replaced. An existing junction is accepted only
    when it already resolves to that Consumer.
    """
    genuine = genuine.resolve()
    link = producer_root.resolve().parent / CONSUMER_NAME
    if link.exists():
        if link.is_junction() and link.resolve() == genuine:
            return {"path": str(link), "created": False}
        raise ConsumerDependencyError("CONSUMER_SIBLING_OCCUPIED:" + str(link))
    if link.drive.lower() != genuine.drive.lower():
        raise ConsumerDependencyError("CONSUMER_JUNCTION_CROSS_VOLUME:" + str(link))
    subprocess.check_call(
        ["cmd", "/c", "mklink", "/J", str(link), str(genuine)], stdout=subprocess.DEVNULL)
    if not link.is_junction() or link.resolve() != genuine:
        raise ConsumerDependencyError("CONSUMER_JUNCTION_NOT_GENUINE:" + str(link))
    return {"path": str(link), "created": True}


def unbind_relocated_consumer(producer_root: Path, genuine: Path) -> None:
    """Remove only a junction to the genuine Consumer. Never delete the target."""
    link = producer_root.resolve().parent / CONSUMER_NAME
    if not link.exists():
        return
    if not link.is_junction() or link.resolve() != genuine.resolve():
        raise ConsumerDependencyError("REFUSE_UNBIND_NOT_GENUINE_JUNCTION:" + str(link))
    link.rmdir()


def _fixture_card() -> dict:
    session = "2026-10-26"
    ticker = "ABB"
    return {"tickers": {ticker: {"current_daily_decision_research": {
        "ticker": ticker,
        "is_actionable": False,
        "source_artifact_identity": "current_daily_decision_research_product:preflight-fixture",
        "source_session": session,
        "market_brief": {"source_market_session": session},
        "current_decision_state": {
            "is_actionable": False,
            "requires_human_review": True,
            "position_sizing_status": "NOT_EVALUATED",
            "entry_action": None,
        },
        "peer_context": {},
        "fundamental_context": {},
        "valuation_context": {},
        "scenario": {
            "probability_status": "UNKNOWN_UNCALIBRATED",
            "bear_case": {},
            "base_case": {},
            "bull_case": {},
        },
        "thesis_counter_thesis": {"thesis": [], "counter_thesis": [], "questions_to_verify": []},
        "authority_boundary": {"probability": "UNKNOWN_UNCALIBRATED"},
    }}}}


def probe_bound_consumer(producer_root: Path, genuine: Path) -> dict:
    """Import and invoke the real contract through the production sibling expression."""
    code = r"""
import json, sys
from pathlib import Path
producer = Path(sys.argv[1])
genuine = Path(sys.argv[2]).resolve()
consumer = producer.resolve().parent / "ai-core-private"
sys.path.insert(0, str(consumer))
from builders.build_ticker_context import (
    current_daily_decision_research_contract, verify_exact_session_bundle)
card = json.loads(sys.argv[3])
ticker = "ABB"
accepted = current_daily_decision_research_contract(card, ticker)
malformed = current_daily_decision_research_contract({}, ticker)
source = Path(current_daily_decision_research_contract.__code__.co_filename).resolve()
loaded = []
for module in sys.modules.values():
    file_name = getattr(module, "__file__", None)
    if not file_name:
        continue
    path = Path(file_name).resolve()
    if path.is_relative_to(genuine):
        loaded.append(str(path.relative_to(genuine)).replace("\\", "/"))
print(json.dumps({
    "consumer": str(consumer),
    "resolved": str(consumer.resolve()),
    "source": str(source),
    "accepted_ticker": None if not isinstance(accepted, dict) else accepted.get("ticker"),
    "accepted_actionable": None if not isinstance(accepted, dict) else accepted.get("is_actionable"),
    "accepted_status": None if not isinstance(accepted, dict) else accepted.get("status"),
    "malformed_status": None if not isinstance(malformed, dict) else malformed.get("status"),
    "verify_present": callable(verify_exact_session_bundle),
    "loaded": sorted(set(loaded)),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code, str(producer_root), str(genuine), json.dumps(_fixture_card())],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ConsumerDependencyError("CONSUMER_IMPORT_FAILED:" + detail[-2000:])
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ConsumerDependencyError("CONSUMER_IMPORT_FAILED:unreadable probe") from exc
    if (Path(payload["resolved"]) != genuine.resolve()
            or not Path(payload["source"]).is_relative_to(genuine.resolve())):
        raise ConsumerDependencyError("CONSUMER_SOURCE_MISBOUND:" + payload.get("source", ""))
    if (payload.get("accepted_ticker") != "ABB" or payload.get("accepted_actionable") is not False
            or payload.get("accepted_status") == "malformed" or payload.get("malformed_status") != "malformed"
            or payload.get("verify_present") is not True):
        raise ConsumerDependencyError("CONSUMER_CONTRACT_REJECTED:" + json.dumps(payload, sort_keys=True))
    head = _git(Path(payload["consumer"]), "rev-parse", "HEAD")
    if head != _git(genuine, "rev-parse", "HEAD"):
        raise ConsumerDependencyError("CONSUMER_HEAD_MISBOUND:" + head)
    payload["head"] = head
    return payload


def assert_relocated_binding(producer_root: Path, profile_path: Path = PROFILE) -> dict:
    """Fail before a full replay when this relocated root cannot see the genuine Consumer."""
    qualified = qualify_consumer(profile_path)
    genuine = Path(qualified["consumer"])
    link = producer_root.resolve().parent / CONSUMER_NAME
    if not link.is_junction() or link.resolve() != genuine:
        raise ConsumerDependencyError("RELOCATED_CONSUMER_UNBOUND:" + str(link))
    probed = probe_bound_consumer(producer_root, genuine)
    return {"qualified": qualified, "probe": probed}


def preflight_producer_seal_consumer(producer_root: Path, *, profile_path: Path = PROFILE,
                                    fixture_parent: Path | None = None) -> dict:
    """Cheap seal-path check. No acquisition, IID materialization, or Producer."""
    qualified = qualify_consumer(profile_path)
    production_sibling_matches(qualified)
    seal_sources_present(producer_root)
    genuine = Path(qualified["consumer"])
    sibling = producer_root.resolve().parent / CONSUMER_NAME
    before = _git(genuine, "status", "--porcelain")
    module_before = (genuine / "builders" / "build_ticker_context.py").stat().st_mtime_ns
    if sibling.exists() and not (sibling.is_junction() and sibling.resolve() == genuine):
        raise ConsumerDependencyError("CONSUMER_SIBLING_OCCUPIED:" + str(sibling))
    parent = fixture_parent or Path(tempfile.mkdtemp(
        prefix="preseal-consumer-", dir=r"T:\StockLookup\scratch"))
    relocated = parent / "relocated-producer"
    created_parent = fixture_parent is None
    relocated.mkdir(parents=True, exist_ok=True)
    link = parent / CONSUMER_NAME
    try:
        binding = bind_relocated_consumer(relocated, genuine)
        probed = probe_bound_consumer(relocated, genuine)
    finally:
        if link.is_junction():
            link.rmdir()
        if created_parent:
            if relocated.exists():
                relocated.rmdir()
            if parent.exists():
                parent.rmdir()
    after = _git(genuine, "status", "--porcelain")
    module_after = (genuine / "builders" / "build_ticker_context.py").stat().st_mtime_ns
    if before != after or module_before != module_after:
        raise ConsumerDependencyError("CONSUMER_MUTATED")
    if probed["head"] != qualified["head"]:
        raise ConsumerDependencyError("CONSUMER_HEAD_MISBOUND:" + probed["head"])
    return {
        "status": "PASS",
        "producer_root": str(producer_root.resolve()),
        "relocated_sibling_existed": sibling.exists(),
        "qualified": qualified,
        "isolated_binding_created": binding["created"],
        "probe": {key: probed[key] for key in (
            "resolved", "source", "accepted_ticker", "accepted_status", "malformed_status", "head", "loaded")},
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: preseal_consumer_dependency.py PRODUCER_ROOT")
    try:
        print(json.dumps(preflight_producer_seal_consumer(Path(sys.argv[1])), indent=2))
    except ConsumerDependencyError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
