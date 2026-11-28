"""Deterministic private-Git transport for already-authoritative daily AI artifacts."""
from __future__ import annotations
import gzip, hashlib, io, json, re, subprocess
from pathlib import Path
from typing import Any, Mapping
from stocklookup_core.evidence.field_identity import stable_id

CONTRACT_VERSION = "stocklookup_ai_handoff_publication/v2"
REQUIRED = ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json")
STRUCTURED_FINANCIAL_CONTEXT = "structured_financial_research_context.json"
_SESSION_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STRUCTURED_FINANCIAL_CONTRACT = "structured_financial_daily_context/v1"
OPPORTUNITY_QUEUE = "daily_opportunity_decision_queue_artifact.json"
CORE_REQUIRED = tuple(name for name in REQUIRED if name != OPPORTUNITY_QUEUE)
OPERATION_MANIFEST = "run_manifest.json"
QUEUE_NOT_DECLARED = "NOT_DECLARED_BY_SEALED_OPERATION"
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2}|/)")

class HandoffPublicationError(ValueError): pass

# GitHub refuses any blob above 100 MB (GH001; Daily 2026-11-27 sealed a 125.85 MB
# ai_research_session_bundle.json). Package files above this margin are STORED as
# deterministic gzip ``<name>.gz``; ``files``/``handoff_build_id`` keep the original-bytes
# sha256, so package identity never depends on storage. HANDOFF_STORAGE.json records the
# encoding. Builds with no oversize file are byte-identical to before (no sidecar).
GIT_STORED_FILE_LIMIT_BYTES = 95 * 1024 * 1024
STORAGE_SIDECAR = "HANDOFF_STORAGE.json"
STORAGE_CONTRACT = "stocklookup_ai_handoff_storage/v1"
def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
def _copy_verified(source: Path, destination: Path, expected_sha: str) -> None:
    digest = hashlib.sha256()
    with source.open("rb") as original, destination.open("xb") as copied:
        while chunk := original.read(1024 * 1024):
            digest.update(chunk)
            copied.write(chunk)
    if digest.hexdigest() != expected_sha:
        raise HandoffPublicationError("HANDOFF_SOURCE_CHANGED_DURING_COPY:" + destination.name)


def _entry_size(entry: Any) -> int:
    return len(entry) if isinstance(entry, (bytes, bytearray)) else entry.stat().st_size


def _write_gzip_verified(entry: Any, destination: Path, expected_sha: str) -> dict[str, Any]:
    """Deterministic gzip (mtime 0, no embedded name) while hashing the ORIGINAL bytes."""
    original = hashlib.sha256()
    size = 0
    with destination.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as packed:
            if isinstance(entry, (bytes, bytearray)):
                original.update(entry)
                packed.write(entry)
                size = len(entry)
            else:
                with entry.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        original.update(chunk)
                        packed.write(chunk)
                        size += len(chunk)
    if original.hexdigest() != expected_sha:
        raise HandoffPublicationError("HANDOFF_SOURCE_CHANGED_DURING_COPY:" + destination.name)
    return {"encoding": "gzip", "stored_name": destination.name, "original_sha256": expected_sha,
            "original_bytes": size, "stored_sha256": sha(destination)}


def _gunzip_sha(data_or_path: Any) -> str:
    digest = hashlib.sha256()
    if isinstance(data_or_path, (bytes, bytearray)):
        handle = gzip.GzipFile(fileobj=io.BytesIO(data_or_path), mode="rb")
    else:
        handle = gzip.open(data_or_path, "rb")
    with handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stored_storage(target: Path) -> dict[str, Any]:
    path = target / STORAGE_SIDECAR
    if not path.is_file():
        return {}
    storage = json.loads(path.read_text(encoding="utf-8"))
    if storage.get("schema_version") != STORAGE_CONTRACT or not isinstance(storage.get("files"), dict):
        raise HandoffPublicationError("HANDOFF_STORAGE_SIDECAR_INVALID")
    return storage["files"]


def _stored_original_sha(target: Path, name: str, storage: Mapping[str, Any]) -> str | None:
    """Original-bytes sha256 of a package file as stored in an immutable build directory."""
    record = storage.get(name)
    if record is not None:
        stored = target / str(record.get("stored_name") or "")
        if record.get("encoding") != "gzip" or stored.name != name + ".gz" or not stored.is_file():
            raise HandoffPublicationError("HANDOFF_STORAGE_RECORD_INVALID:" + name)
        if sha(stored) != record.get("stored_sha256"):
            raise HandoffPublicationError("HANDOFF_STORED_FILE_HASH_MISMATCH:" + name)
        return _gunzip_sha(stored)
    return sha(target / name) if (target / name).is_file() else None


def _git(repo: Path, *args: str) -> str:
    result=subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True,encoding="utf-8")
    if result.returncode: raise HandoffPublicationError("GIT_"+args[0].upper()+":"+(result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()
def _git_bytes(repo: Path, *args: str) -> bytes:
    result=subprocess.run(["git","-C",str(repo),*args],capture_output=True,check=False)
    if result.returncode:
        raise HandoffPublicationError("GIT_"+args[0].upper()+":"+result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout
def _unsafe(value: Any) -> bool:
    return _unsafe_pointer(value) is not None
def _unsafe_pointer(value: Any, pointer: str = "") -> str | None:
    """Locate private paths without confusing the governed DNSE route with a file.

    The exact snapshot source descriptor carries a root-relative HTTP endpoint. Only
    that known provider/dataset/endpoint tuple is a route; every sibling, dictionary
    key and nested value still passes through the filesystem-path guard. This is
    validation only: sealed bytes and their content identities remain unchanged.
    """
    if isinstance(value, str):
        return (pointer or "/") if _ABSOLUTE_PATH.match(value.strip()) else None
    if isinstance(value, dict):
        dnse_route = (value.get("provider") == "DNSE" and value.get("dataset") == "DNSE_OHLC_1D"
                      and value.get("endpoint") == "/price/ohlc")
        for key, entry in value.items():
            if isinstance(key, str) and _ABSOLUTE_PATH.match(key.strip()):
                return pointer + "/<unsafe-key>"
            if key == "endpoint" and dnse_route:
                continue
            token = str(key).replace("~", "~0").replace("/", "~1")
            rejected = _unsafe_pointer(entry, pointer + "/" + token)
            if rejected is not None:
                return rejected
    if isinstance(value, list):
        for index, entry in enumerate(value):
            rejected = _unsafe_pointer(entry, pointer + "/" + str(index))
            if rejected is not None:
                return rejected
    return None
def _manifest_lineage(manifest: Any, producer_checkpoint: str) -> dict[str, Any]:
    if not isinstance(manifest, Mapping): raise HandoffPublicationError("HANDOFF_MANIFEST_NOT_OBJECT")
    res = {"producer_checkpoint":producer_checkpoint,"producer_head":manifest.get("producer_head"),"operation_identity":manifest.get("operation_identity"),"daily_product_identity":manifest.get("daily_product_identity")}
    if manifest.get("integrated_investment_decision_product_identity"):
        res["integrated_investment_decision_product_identity"] = manifest.get("integrated_investment_decision_product_identity")
    return res
def _financial_lineage(parsed: Mapping[str, Any]) -> str | None:
    """Validate the optional compact V2 identity chain without publishing its full replay."""
    primary = parsed.get("ai_research_session_bundle.json") or {}
    manifest = parsed.get("ai_research_bundle_manifest.json") or {}
    financial = primary.get("financial_analysis") if isinstance(primary, Mapping) else None
    if not isinstance(financial, Mapping): return None
    source_identity = financial.get("source_context_identity")
    if source_identity is None: return None
    summary = financial.get("market_summary") or {}
    if (not isinstance(summary, Mapping) or summary.get("source_context_identity") != source_identity
            or manifest.get("financial_analysis_source_context_identity") != source_identity):
        raise HandoffPublicationError("HANDOFF_FINANCIAL_ANALYSIS_IDENTITY_CHAIN_INVALID")
    return str(source_identity)
def _unavailable_financial_context(reason: str) -> dict[str, Any]:
    body = {
        "availability": "UNAVAILABLE",
        "attachment_role": "POST_SESSION_CURRENT_RESEARCH",
        "contract_version": _STRUCTURED_FINANCIAL_CONTRACT,
        "execution_eligible": False,
        "financial_v2_authority_unchanged": "2026-09-05.1",
        "historical_pit": "UNKNOWN",
        "is_actionable": False,
        "official_fact_admitted": False,
        "reason_codes": [reason],
        "sealed_session_evidence": False,
        "valuation_use": "CLOSED",
    }
    body["context_sha256"] = stable_id({key: value for key, value in body.items() if key != "context_sha256"})
    return body
def _financial_context_rejection(payload: Mapping[str, Any]) -> str | None:
    if payload.get("contract_version") != _STRUCTURED_FINANCIAL_CONTRACT:
        return "STRUCTURED_FINANCIAL_CONTEXT_CONTRACT"
    if payload.get("availability") != "AVAILABLE":
        return "STRUCTURED_FINANCIAL_CONTEXT_NOT_AVAILABLE"
    closed = (
        payload.get("official_fact_admitted") is False
        and payload.get("historical_pit") == "UNKNOWN"
        and payload.get("valuation_use") == "CLOSED"
        and payload.get("sealed_session_evidence") is False
        and payload.get("attachment_role") == "POST_SESSION_CURRENT_RESEARCH"
        and payload.get("is_actionable") is False
        and payload.get("execution_eligible") is False
        and payload.get("financial_v2_authority_unchanged") == "2026-09-05.1"
    )
    if not closed:
        return "STRUCTURED_FINANCIAL_CONTEXT_AUTHORITY"
    identity = payload.get("research_identity")
    digest = payload.get("input_sha256")
    if not isinstance(identity, str) or not identity.startswith("structured_financial_research:"):
        return "STRUCTURED_FINANCIAL_CONTEXT_RESEARCH_IDENTITY"
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return "STRUCTURED_FINANCIAL_CONTEXT_INPUT_SHA"
    issuers = payload.get("issuers")
    if not isinstance(issuers, list) or not issuers:
        return "STRUCTURED_FINANCIAL_CONTEXT_ISSUERS"
    claimed = payload.get("context_sha256")
    body = {key: value for key, value in payload.items() if key != "context_sha256"}
    if claimed != stable_id(body):
        return "STRUCTURED_FINANCIAL_CONTEXT_SHA"
    return None
def _qualify_structured_financial_context(payload: Any, session: str) -> dict[str, Any] | None:
    """Omit the file for an ineligible session. An eligible unqualified file is UNAVAILABLE."""
    if not isinstance(payload, Mapping):
        return None
    eligible = payload.get("first_eligible_session")
    if not isinstance(eligible, str) or _SESSION_DATE.fullmatch(eligible) is None:
        return None
    if not isinstance(session, str) or _SESSION_DATE.fullmatch(session) is None or session < eligible:
        return None
    reason = _financial_context_rejection(payload)
    if reason or _unsafe_pointer(payload) is not None:
        return _unavailable_financial_context(reason or "STRUCTURED_FINANCIAL_CONTEXT_UNSAFE_PATH")
    return dict(payload)
def _load_structured_financial_context(source: Path, session: str) -> bytes | None:
    local = source / STRUCTURED_FINANCIAL_CONTEXT
    shared = source.parent.parent / STRUCTURED_FINANCIAL_CONTEXT
    path = local if local.is_file() else shared if shared.is_file() else None
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    qualified = _qualify_structured_financial_context(payload, session)
    if qualified is None:
        return None
    return (json.dumps(qualified, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def opportunity_queue_requirement(source: Path) -> dict[str, Any]:
    """Whether this operation's handoff must carry the opportunity decision queue.

    ``daily_research_session_operations.build_operation`` attaches the queue only when the
    session's governed registry selects both optional current inputs (official universe and
    event context); a completed session keeps its actual lock, including absent optionals. The
    sealed operation manifest (``run_manifest.json``) therefore decides: a declared queue is
    REQUIRED and must be that exact artifact; an undeclared queue must be absent (never borrowed
    from another operation) and is published as an explicit status. A source without a sealed
    manifest keeps the legacy contract: the queue file is required.
    """
    path = Path(source) / OPERATION_MANIFEST
    if not path.is_file():
        return {"status": "LEGACY_REQUIRED", "required": True, "identity": None}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HandoffPublicationError("HANDOFF_OPERATION_MANIFEST_UNREADABLE") from None
    outputs = manifest.get("outputs") if isinstance(manifest, Mapping) else None
    if not isinstance(outputs, Mapping):
        raise HandoffPublicationError("HANDOFF_OPERATION_MANIFEST_OUTPUTS_MISSING")
    declared = outputs.get("daily_opportunity_decision_queue")
    if declared:
        return {"status": "DECLARED", "required": True, "identity": str(declared)}
    return {"status": QUEUE_NOT_DECLARED, "required": False, "identity": None}
def required_files(source: Path) -> tuple[str, ...]:
    return REQUIRED if opportunity_queue_requirement(source)["required"] else CORE_REQUIRED
def _identity(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode("utf-8")).hexdigest()
def _presentation_observer_payload(session: str, attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Additive, presentation/research-observer state only -- never analytical decision
    authority. Derived entirely from the dedicated ``post_handoff_presentation_attestation``
    artifact; never reads or mutates sealed Producer evidence. See
    CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 3. A legitimately
    unavailable observer is published as an explicit UNAVAILABLE status here, never fabricated."""
    projection = attestation.get("presentation_projection") or {}
    velocity = attestation.get("signal_velocity") or {}
    foreign_flow = attestation.get("current_foreign_flow_enrichment") or {}
    flow_price = attestation.get("flow_price_divergence_shadow") or {}
    feedback = attestation.get("post_handoff_prospective_decision_feedback") or {}
    return {
        "schema_version": "post_handoff_presentation_state/v1",
        "authority_boundary": "PRESENTATION_RESEARCH_OBSERVER_STATE_NOT_ANALYTICAL_DECISION_AUTHORITY",
        "session": session,
        "sealed_producer_workspace_artifact_identity": attestation.get("sealed_producer_workspace_artifact_identity"),
        "post_handoff_presentation_status": projection.get("status"),
        "post_handoff_presentation_workspace_artifact_identity": projection.get("workspace_artifact_identity"),
        "post_handoff_presentation_lineage_status": projection.get("lineage_status"),
        "signal_velocity": {"status": velocity.get("status"), "identity": velocity.get("artifact_identity")},
        "current_foreign_flow_enrichment": {
            "status": foreign_flow.get("status"),
            "complete_count": foreign_flow.get("complete_count"),
            "requested_count": foreign_flow.get("requested_count"),
            "network_calls_made": foreign_flow.get("network_calls_made"),
            "reason": foreign_flow.get("reason"),
        },
        "flow_price_divergence_shadow": {"status": flow_price.get("status"), "identity": flow_price.get("artifact_identity")},
        "post_handoff_prospective_decision_feedback": {"status": feedback.get("status"), "identity": feedback.get("artifact_identity"),
                                                     **({"reason_code": feedback["reason_code"]} if feedback.get("reason_code") else {})},
        **({"thesis_evidence":attestation["thesis_evidence"]} if "thesis_evidence" in attestation else {}),
    }
def build_package(source: Path, session: str, previous: Path|None=None, *, producer_checkpoint: str="UNKNOWN", decision_brief: Path|None=None, daily_integrated_decision_brief: Path|None=None, post_handoff_presentation: Mapping[str, Any]|None=None) -> tuple[dict[str,Any],dict[str,Any]]:
    queue = opportunity_queue_requirement(source)
    if not queue["required"] and (source / OPPORTUNITY_QUEUE).exists():
        raise HandoffPublicationError("HANDOFF_OPPORTUNITY_QUEUE_PRESENT_BUT_UNDECLARED")
    files: dict[str, Any] = {name: source / name for name in (REQUIRED if queue["required"] else CORE_REQUIRED)}
    if previous: files[f"previous_session_bundle_{previous.parent.parent.name}.json"]=previous
    # next_session_decision_brief.json is a pure package-local derived projection (see
    # next_session_decision_brief.py) -- optional and additive, exactly like `previous`, so a
    # caller/test that never supplies one sees no behavior change at all.
    if decision_brief: files["next_session_decision_brief.json"]=decision_brief
    # daily_integrated_decision_brief.json (see daily_integrated_decision_brief.py) is the compact
    # AI-facing daily product -- optional and additive on the exact same pattern as decision_brief,
    # so ChatGPT can answer the owner's 11-watchlist review from the published handoff directly.
    if daily_integrated_decision_brief: files["daily_integrated_decision_brief.json"]=daily_integrated_decision_brief
    # post_handoff_presentation_state.json is generated in-memory (never read from or written
    # into the sealed Producer `source` directory) -- `files` may hold `bytes` here instead of a
    # `Path`, handled below and in `publish()`.
    if post_handoff_presentation is not None:
        files["post_handoff_presentation_state.json"] = (
            json.dumps(_presentation_observer_payload(session, post_handoff_presentation),
                       ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    # Optional provider research. Absence leaves the package identical. An ineligible
    # session also leaves it identical. An eligible unqualified file is UNAVAILABLE.
    financial_context = _load_structured_financial_context(source, session)
    if financial_context is not None:
        files[STRUCTURED_FINANCIAL_CONTEXT] = financial_context
    parsed: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for name, entry in files.items():
        if isinstance(entry, (bytes, bytearray)):
            raw = entry
        else:
            if not entry.is_file():
                raise HandoffPublicationError("HANDOFF_SOURCE_MISSING:" + name)
            raw = entry.read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8")
        del raw
        parsed[name] = json.loads(text)
        del text
        rejected = _unsafe_pointer(parsed[name])
        if rejected is not None:
            raise HandoffPublicationError("HANDOFF_ABSOLUTE_PATH_FORBIDDEN:" + name + ":" + rejected)
        # Previous bundles contribute only their original bytes/hash, never lineage.
        # Drop the parsed graph before loading the optional briefs that follow it.
        if previous is not None and entry == previous and name.startswith("previous_session_bundle_"):
            del parsed[name]
    if queue["identity"] is not None and (parsed.get(OPPORTUNITY_QUEUE) or {}).get("artifact_identity") != queue["identity"]:
        raise HandoffPublicationError("HANDOFF_OPPORTUNITY_QUEUE_IDENTITY_MISMATCH")
    package_identity = _identity({"session": session, "files": hashes})
    lineage = _manifest_lineage(parsed["ai_research_bundle_manifest.json"], producer_checkpoint)
    financial_source_identity = _financial_lineage(parsed)
    if financial_source_identity is not None: lineage["financial_analysis_source_context_identity"] = financial_source_identity
    # Additive and only when absent, so queue-bearing builds keep their existing identity.
    if not queue["required"]: lineage["opportunity_decision_queue"] = {"status": QUEUE_NOT_DECLARED}
    if decision_brief:
        lineage["next_session_decision_brief_identity"]=parsed["next_session_decision_brief.json"].get("artifact_identity")
        lineage["comparison_metadata"]=parsed["next_session_decision_brief.json"].get("comparison_metadata")
    if daily_integrated_decision_brief:
        brief_parsed=parsed["daily_integrated_decision_brief.json"]
        lineage["daily_integrated_decision_brief_identity"]=brief_parsed.get("artifact_identity")
        lineage["daily_integrated_decision_brief_previous_qualified_session"]=brief_parsed.get("previous_qualified_session")
    if post_handoff_presentation is not None:
        presentation_parsed = parsed["post_handoff_presentation_state.json"]
        lineage["post_handoff_presentation_state"] = {
            "status": presentation_parsed.get("post_handoff_presentation_status"),
            "workspace_artifact_identity": presentation_parsed.get("post_handoff_presentation_workspace_artifact_identity"),
            "sealed_producer_workspace_artifact_identity": presentation_parsed.get("sealed_producer_workspace_artifact_identity"),
            "signal_velocity_status": (presentation_parsed.get("signal_velocity") or {}).get("status"),
            "current_foreign_flow_enrichment_status": (presentation_parsed.get("current_foreign_flow_enrichment") or {}).get("status"),
            "flow_price_divergence_shadow_status": (presentation_parsed.get("flow_price_divergence_shadow") or {}).get("status"),
            "post_handoff_prospective_decision_feedback_status": (presentation_parsed.get("post_handoff_prospective_decision_feedback") or {}).get("status"),
        }
    if STRUCTURED_FINANCIAL_CONTEXT in parsed:
        item = parsed[STRUCTURED_FINANCIAL_CONTEXT]
        lineage["structured_financial_research"] = {
            "availability": item.get("availability"),
            "attachment_role": item.get("attachment_role"),
            "context_sha256": item.get("context_sha256"),
            "historical_pit": item.get("historical_pit"),
            "input_sha256": item.get("input_sha256"),
            "official_fact_admitted": item.get("official_fact_admitted"),
            "research_identity": item.get("research_identity"),
        }
    handoff_build_id="handoff_build_"+_identity({"session":session,"package_sha256":package_identity,"lineage":lineage})
    payload={"schema_version":CONTRACT_VERSION,"session":session,"status":"READY_FOR_AI","files":hashes,"package_sha256":package_identity,"lineage":lineage,"handoff_build_id":handoff_build_id}
    return files,payload
def _latest_payload(session: str, payload: Mapping[str, Any], *, immutable_session_path: str, handoff_commit: str, previous: Path|None) -> dict[str, Any]:
    latest={"schema_version":"stocklookup_ai_handoff_latest/v2","latest_session":session,"status":"READY_FOR_AI","handoff_build_id":payload["handoff_build_id"],"immutable_session_path":immutable_session_path,"handoff_commit":handoff_commit,"producer_checkpoint":payload["lineage"]["producer_checkpoint"],"producer_lineage":payload["lineage"],"session_bundle_sha256":payload["files"]["ai_research_session_bundle.json"],"opportunity_artifact_sha256":payload["files"].get(OPPORTUNITY_QUEUE),"manifest_sha256":payload["files"]["ai_research_bundle_manifest.json"],"previous_session":previous.parent.parent.name if previous else None}
    if OPPORTUNITY_QUEUE not in payload["files"]: latest["opportunity_decision_queue_status"]=QUEUE_NOT_DECLARED
    if "next_session_decision_brief.json" in payload["files"]:
        latest["decision_brief_sha256"]=payload["files"]["next_session_decision_brief.json"]
        latest["comparison_metadata"]=payload["lineage"].get("comparison_metadata")
    if "daily_integrated_decision_brief.json" in payload["files"]: latest["daily_integrated_decision_brief_sha256"]=payload["files"]["daily_integrated_decision_brief.json"]
    if STRUCTURED_FINANCIAL_CONTEXT in payload["files"]:
        latest["structured_financial_research_context_sha256"]=payload["files"][STRUCTURED_FINANCIAL_CONTEXT]
    return latest
def publish(repo: Path, source: Path, session: str, *, previous: Path|None=None, producer_checkpoint: str="UNKNOWN", push: bool=True, local_only: bool=False, decision_brief: Path|None=None, daily_integrated_decision_brief: Path|None=None, post_handoff_presentation: Mapping[str, Any]|None=None) -> dict[str,Any]:
    """``local_only=True`` builds and validates the package (proving it is genuinely
    publishable -- every required file present, every hash computed, the manifest lineage
    chain checked) but returns before touching ``repo`` at all: no ``mkdir``, no file copy, no
    ``git`` call of any kind, not even a commit. This is distinct from ``push=False``, which
    still performs two real local commits (see the module docstring incident this parameter
    exists to close) -- ``local_only`` is the genuine zero-Git-mutation contract. ``local_only``
    always takes precedence over ``push`` -- including ``push``'s own default of ``True`` -- so
    a caller never needs to remember to also pass ``push=False``; there is exactly one way to
    ask for zero Git mutation, not two flags that must agree."""
    files,payload=build_package(source,session,previous,producer_checkpoint=producer_checkpoint,decision_brief=decision_brief,daily_integrated_decision_brief=daily_integrated_decision_brief,post_handoff_presentation=post_handoff_presentation)
    target=repo/"sessions"/session/"builds"/payload["handoff_build_id"]
    if local_only:
        return {"status":"LOCAL_VALIDATED_NO_GIT_MUTATION","session":session,"package":payload,"immutable_session_path":target.relative_to(repo).as_posix()}
    latest_path = repo / "LATEST.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.is_file() else {}
    if not isinstance(latest, dict):
        raise HandoffPublicationError("HANDOFF_LATEST_NOT_OBJECT")
    if str(latest.get("latest_session") or "") > session:
        raise HandoffPublicationError("HANDOFF_NEWER_LATEST_SESSION:"+str(latest["latest_session"]))
    immutable_session_path=target.relative_to(repo).as_posix()
    if target.exists():
        storage=_stored_storage(target)
        current={name:digest for name in files if (digest:=_stored_original_sha(target,name,storage)) is not None}
        if current!=payload["files"]:
            raise HandoffPublicationError("FAIL_CLOSED_HANDOFF_BUILD_CONFLICT:"+payload["handoff_build_id"])
        # A directory alone is not a publication receipt. Resume only committed,
        # unchanged immutable bytes; a crash before the immutable commit fails closed.
        if _git(repo, "status", "--porcelain", "--", immutable_session_path):
            raise HandoffPublicationError("FAIL_CLOSED_HANDOFF_BUILD_UNCOMMITTED")
        build_commit = _git(repo, "log", "-1", "--format=%H", "--", immutable_session_path)
        if not build_commit:
            raise HandoffPublicationError("FAIL_CLOSED_HANDOFF_BUILD_UNCOMMITTED")
        expected_latest = _latest_payload(session,payload,immutable_session_path=immutable_session_path,
                                          handoff_commit=build_commit,previous=previous)
        if (latest == expected_latest and
                not _git(repo, "status", "--porcelain", "--", "LATEST.json", "LATEST.md")):
            pointer_commit = _git(repo, "rev-parse", "HEAD")
            if push: _git(repo, "push")
            return {"status":"NO_OP_ALREADY_PUBLISHED","session":session,"package":payload,
                    "immutable_session_path":immutable_session_path,
                    "handoff_commit":pointer_commit,"immutable_handoff_commit":build_commit}
        # Only the just-committed build may finish an interrupted pointer update.
        # An older build with a different authoritative pointer is never repointed.
        if _git(repo, "rev-parse", "HEAD") != build_commit:
            raise HandoffPublicationError("FAIL_CLOSED_HANDOFF_LATEST_POINTER_CONFLICT")
    else:
        target.mkdir(parents=True,exist_ok=False)
        # Hash-bound transport bytes must survive repository/global text and clean
        # filters. The nearest attributes apply only to this new immutable build;
        # neither source bytes, old builds nor the operator's Git config are changed.
        (target/".gitattributes").write_bytes(b"* -text -filter -ident\n")
        storage={}
        for name,entry in files.items():
            if _entry_size(entry) > GIT_STORED_FILE_LIMIT_BYTES:
                storage[name]=_write_gzip_verified(entry, target / (name + ".gz"), payload["files"][name])
            elif isinstance(entry, (bytes, bytearray)): (target/name).write_bytes(entry)
            else:
                _copy_verified(entry, target / name, payload["files"][name])
        note=""
        if storage:
            (target/STORAGE_SIDECAR).write_text(json.dumps({"schema_version":STORAGE_CONTRACT,"limit_bytes":GIT_STORED_FILE_LIMIT_BYTES,"files":storage},indent=2,sort_keys=True)+"\n",encoding="utf-8")
            note="\nStored as gzip (original sha256 unchanged; see "+STORAGE_SIDECAR+"): "+", ".join(sorted(storage))+"\n"
        (target/"HANDOFF.md").write_text(f"# Stock Lookup AI handoff\n\nSession: {session}\n\nBuild: {payload['handoff_build_id']}\n\nStatus: READY_FOR_AI\n{note}",encoding="utf-8")
        _git(repo,"add",immutable_session_path)
        _git(repo,"commit","-m",f"handoff: {session} build {payload['handoff_build_id']}")
        build_commit=_git(repo,"rev-parse","HEAD")
    latest=_latest_payload(session,payload,immutable_session_path=immutable_session_path,handoff_commit=build_commit,previous=previous)
    (repo/"LATEST.json").write_text(json.dumps(latest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (repo/"LATEST.md").write_text(f"# Latest Stock Lookup handoff\n\nSession: {session}\n\nBuild: {payload['handoff_build_id']}\n\nStatus: READY_FOR_AI\n",encoding="utf-8")
    _git(repo,"add","LATEST.json","LATEST.md")
    _git(repo,"commit","-m",f"handoff: {session} latest {payload['handoff_build_id']}")
    pointer_commit=_git(repo,"rev-parse","HEAD")
    if push: _git(repo,"push")
    return {"status":"PUBLISHED_READY_FOR_AI","session":session,"handoff_commit":pointer_commit,"immutable_handoff_commit":build_commit,"immutable_session_path":immutable_session_path,"package":payload}


def verify_remote_publication(repo: Path, published: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the handoff from ``origin/main``, never just the working tree."""
    _git(repo, "fetch", "origin")
    remote_sha = _git(repo, "rev-parse", "origin/main")
    expected_commit = str(published.get("handoff_commit") or "")
    if expected_commit and remote_sha != expected_commit:
        raise HandoffPublicationError(f"REMOTE_HANDOFF_SHA_MISMATCH:{expected_commit}:{remote_sha}")
    try:
        latest = json.loads(_git(repo, "show", "origin/main:LATEST.json"))
    except (json.JSONDecodeError, HandoffPublicationError) as exc:
        raise HandoffPublicationError("REMOTE_LATEST_JSON_INVALID") from exc
    package = published.get("package") or {}
    session = str(published.get("session") or "")
    path = str(published.get("immutable_session_path") or "")
    if (latest.get("status") != "READY_FOR_AI" or latest.get("latest_session") != session
            or latest.get("immutable_session_path") != path
            or latest.get("handoff_build_id") != package.get("handoff_build_id")):
        raise HandoffPublicationError("REMOTE_LATEST_POINTER_MISMATCH")
    names = set(_git(repo, "ls-tree", "-r", "--name-only", "origin/main", path).splitlines())
    storage: dict[str, Any] = {}
    if f"{path}/{STORAGE_SIDECAR}" in names:
        try:
            sidecar = json.loads(_git(repo, "show", f"origin/main:{path}/{STORAGE_SIDECAR}"))
        except (json.JSONDecodeError, HandoffPublicationError) as exc:
            raise HandoffPublicationError("REMOTE_HANDOFF_STORAGE_INVALID") from exc
        if sidecar.get("schema_version") != STORAGE_CONTRACT or not isinstance(sidecar.get("files"), dict):
            raise HandoffPublicationError("REMOTE_HANDOFF_STORAGE_INVALID")
        storage = sidecar["files"]
    expected_files = set((package.get("files") or {}).keys())
    if set(storage) - expected_files:
        raise HandoffPublicationError("REMOTE_HANDOFF_STORAGE_UNDECLARED_FILE")
    stored = {name: (str(storage[name].get("stored_name")) if name in storage else name) for name in expected_files}
    missing = sorted(f"{path}/{stored[name]}" for name in expected_files if f"{path}/{stored[name]}" not in names)
    if missing:
        raise HandoffPublicationError("REMOTE_IMMUTABLE_FILES_MISSING:" + ",".join(missing))
    for name, expected_hash in (package.get("files") or {}).items():
        remote_name = f"{path}/{stored[name]}"
        # Resolve the blob first: Windows Git treats a long ``rev:path`` argument to
        # ``show`` as a filesystem path, while object IDs are platform-neutral.
        tree = _git(repo, "ls-tree", "origin/main", "--", remote_name)
        fields = tree.split("\t", 1)[0].split()
        if len(fields) < 3:
            raise HandoffPublicationError("REMOTE_IMMUTABLE_BLOB_MISSING:" + name)
        data = _git_bytes(repo, "cat-file", "blob", fields[2])
        if name in storage:
            record = storage[name]
            if (record.get("encoding") != "gzip" or stored[name] != name + ".gz"
                    or record.get("original_sha256") != expected_hash
                    or hashlib.sha256(data).hexdigest() != record.get("stored_sha256")):
                raise HandoffPublicationError("REMOTE_STORED_FILE_INVALID:" + name)
            actual = _gunzip_sha(data)
        else:
            actual = hashlib.sha256(data).hexdigest()
        del data
        if actual != expected_hash:
            raise HandoffPublicationError("REMOTE_FILE_HASH_MISMATCH:" + name)
    if latest.get("producer_lineage") != package.get("lineage"):
        raise HandoffPublicationError("REMOTE_LINEAGE_MISMATCH")
    for key, name in (("session_bundle_sha256", "ai_research_session_bundle.json"),
                      ("opportunity_artifact_sha256", OPPORTUNITY_QUEUE),
                      ("manifest_sha256", "ai_research_bundle_manifest.json"),
                      ("decision_brief_sha256", "next_session_decision_brief.json"),
                      ("daily_integrated_decision_brief_sha256", "daily_integrated_decision_brief.json")):
        if latest.get(key) != (package.get("files") or {}).get(name):
            raise HandoffPublicationError("REMOTE_LATEST_HASH_MISMATCH:"+name)
    if latest.get("handoff_commit") != published.get("immutable_handoff_commit"):
        raise HandoffPublicationError("REMOTE_IMMUTABLE_COMMIT_MISMATCH")
    return {"status": "READY_FOR_AI", "latest_session": session,
            "latest_pointer": path, "remote_sha": remote_sha,
            "handoff_build_id": latest["handoff_build_id"]}
