"""Offline source conservation for Owner-approved source transitions.

The original manifest/pins stay unchanged. Historical bytes come only from the exact
archived source after both sides have been read and hashed. Active execution always
hashes active source; no digest spoofing or historical receipt adoption is provided.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools import qualify_e4_infrastructure as e4

READER = "prospective_decision_retention.py"
ARCHIVE = "tests/fixtures/retention_reader_v1.py.txt"
MANIFEST = "tests/fixtures/retention_reader_transition_v2.json"
STORAGE_MANIFEST = "tests/fixtures/storage_portability_source_transition_v1.json"
VALUATION_MANIFEST = "tests/fixtures/evidence_valuation_orchestration_source_transition_v1.json"
VALUATION_CONTRACT = "evidence_valuation_orchestration_source_transition/v1"
VALUATION_BASE = "de90c6b94c7bb2377bedd7e2a1c809498d22926a"
VALUATION_SOURCES = (
    "canonical_daily_operation.py",
    "canonical_post_close_pipeline.py",
)
THESIS_MANIFEST = "tests/fixtures/thesis_evidence_production_source_transition_v1.json"
THESIS_CONTRACT = "thesis_evidence_production_source_transition/v1"
THESIS_BASE = "de90c6b94c7bb2377bedd7e2a1c809498d22926a"
THESIS_SOURCE = "stocklookup_core/research/thesis_evidence_production.py"
THESIS_ARCHIVE = "tests/fixtures/thesis_evidence_v1_sources/thesis_evidence_production.py.txt"
THESIS_SCOPE = "EXACT_ONE_FILE_OWNER_APPROVED_NOT_A_GENERAL_TRANSITION"
_THESIS_FIELDS = frozenset({
    "contract_version", "workstream", "base_commit", "source_path", "archive",
    "prior_sha256_lf", "active_sha256_lf", "historical_e4_v2_digest", "active_e4_v2_digest",
    "rejected_mixed_digest", "exception_scope", "release_authority", "compatibility",
})
FINANCIAL_RESEARCH_MANIFEST = "tests/fixtures/financial_research_source_transition_v1.json"


LAYOUT_MANIFEST = "tests/fixtures/repository_layout_source_transition_v1.json"
LAYOUT_CONTRACT = "repository_layout_source_transition/v1"
LAYOUT_BASE = "92fe761287f08d97ab88602dbe9349ab656a1fe6"
LAYOUT_SCOPE = "EXACT_IMPORT_RETARGET_ONLY_NO_BEHAVIOR_CHANGE"
# Each admitted source and the transition manifest that already governs its live digest.
LAYOUT_SOURCES = {
    "stocklookup.py": FINANCIAL_RESEARCH_MANIFEST,
    "tools/run_owner_daily.py": STORAGE_MANIFEST,
    "canonical_daily_operation.py": VALUATION_MANIFEST,
    "canonical_post_close_pipeline.py": VALUATION_MANIFEST,
}

CAPACITY_SOURCE = "tools/run_owner_daily.py"
CAPACITY_MANIFEST = "tests/fixtures/owner_daily_capacity_source_transition_v1.json"
CAPACITY_ARCHIVE = "tests/fixtures/owner_daily_capacity_v1_sources/tools/run_owner_daily.py.txt"
LAUNCHER_MANIFEST = "tests/fixtures/owner_daily_launcher_source_transition_v1.json"
LAUNCHER_SOURCES = ("tools/run_owner_daily.py", "stocklookup.py")
IID_RUNTIME_MANIFEST = "tests/fixtures/owner_daily_iid_runtime_memory_source_transition_v1.json"
IID_RUNTIME_BASE = "eaaf7c946d54b2f6b0ef41137b8dfa294e3dc77d"
IID_RUNTIME_SCOPE = "EXACT_IID_RUNTIME_MEMORY_CORRECTIVE_ONLY"
IID_RUNTIME_SOURCES = (
    "tools/run_owner_daily.py",
    "canonical_post_close_pipeline.py",
    "stocklookup_core/decision/integrated_investment_decision_product.py",
)
TPLUS_RESUME_MANIFEST = "tests/fixtures/tplus_resumable_feedback_source_transition_v1.json"
TPLUS_RESUME_BASE = "de40f25a6f647b907bc58dff513eb4f7b1bbba0c"
TPLUS_RESUME_SCOPE = "EXACT_TPLUS_RESUMABLE_FEEDBACK_ONLY"
TPLUS_RESUME_SOURCE = "prospective_feedback_streaming.py"
TPLUS_DAILY_MANIFEST = "tests/fixtures/tplus_daily_incremental_source_transition_v1.json"
TPLUS_DAILY_ARCHIVE = "tests/fixtures/tplus_daily_incremental_v1_sources/prospective_feedback_streaming.py.txt"
TPLUS_DAILY_BASE = "53c7d8e8300283e8d6c8386e7281175d3f0f5aba"
RESIDENT_MANIFEST = "tests/fixtures/owner_daily_resident_iid_source_transition_v1.json"
RESIDENT_SOURCES = ("canonical_daily_operation.py", "stocklookup_core/decision/daily_integrated_decision_brief.py")
RESIDENT_PRIOR_PINS = ("16172dae8073ebef819022b3bad71ca216c22e6c0ddbaa3ea31535fe5557cc7c",
                       "e39c49ee1e20958617d92aaef51b530f27da18003cab59c592670090fc98c5a1")


def _resident_spec(root: Path) -> dict | None:
    path = root / RESIDENT_MANIFEST
    if not path.is_file():
        return None
    spec = json.loads(path.read_bytes())
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "owner_daily_resident_iid_source_transition/v1"
            or spec.get("base_commit") != "b9c4ff102f74bc41f4cb863f43a875a93e07cd9d"
            or spec.get("scope") != "EXACT_PRESEAL_RESIDENT_IID_ONLY"
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") != "fe053a2098300425851e4184f99552884d251b18acbc0b50511c6948cc64fa45"
            or not isinstance(spec.get("sources"), dict) or tuple(spec["sources"]) != RESIDENT_SOURCES):
        raise ValueError("RESIDENT_IID_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


def _resident_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    if relative not in RESIDENT_SOURCES:
        return active
    spec = _resident_spec(root)
    if spec is None:
        return active
    row = spec["sources"][relative]
    archive = "tests/fixtures/owner_daily_resident_iid_v1_sources/" + relative + ".txt"
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != archive):
        raise ValueError("RESIDENT_IID_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (row["prior_sha256_lf"] != RESIDENT_PRIOR_PINS[RESIDENT_SOURCES.index(relative)]
            or hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("RESIDENT_IID_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _tplus_daily_spec(root: Path) -> dict | None:
    manifest = root / TPLUS_DAILY_MANIFEST
    if not manifest.is_file():
        return None
    spec = json.loads(manifest.read_bytes())
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_daily_incremental_source_transition/v1"
            or spec.get("base_commit") != TPLUS_DAILY_BASE
            or spec.get("scope") != "EXACT_TPLUS_DAILY_INCREMENTAL_ONLY"
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(spec.get("sources"), dict) or tuple(spec["sources"]) != (TPLUS_RESUME_SOURCE,)):
        raise ValueError("TPLUS_DAILY_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


def _tplus_daily_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    spec = _tplus_daily_spec(root)
    if spec is None or relative != TPLUS_RESUME_SOURCE:
        return active
    row = spec["sources"][relative]
    if (set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != TPLUS_DAILY_ARCHIVE):
        raise ValueError("TPLUS_DAILY_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / TPLUS_DAILY_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_DAILY_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _tplus_resume_spec(root: Path) -> dict | None:
    manifest = root / TPLUS_RESUME_MANIFEST
    if not manifest.is_file():
        return None
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_resumable_feedback_source_transition/v1"
            or spec.get("base_commit") != TPLUS_RESUME_BASE
            or spec.get("scope") != TPLUS_RESUME_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != (TPLUS_RESUME_SOURCE,)):
        raise ValueError("TPLUS_RESUME_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


def _tplus_resume_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the resumable T+ feedback successor before every older source pin.

    The archived bytes are the exact pre-corrective streaming builder. Older manifests
    stay unchanged and still bind those bytes. A missing manifest keeps older checkouts valid.
    """
    spec = _tplus_resume_spec(root)
    if spec is None or relative != TPLUS_RESUME_SOURCE:
        return active
    row = spec["sources"][relative]
    archive = "tests/fixtures/tplus_resumable_feedback_v1_sources/" + relative + ".txt"
    if set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"} or row.get("archive") != archive:
        raise ValueError("TPLUS_RESUME_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_RESUME_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _iid_runtime_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the IID runtime-memory successor before every older source pin.

    The archived bytes are the exact pre-corrective sources. Older manifests stay
    unchanged and still bind those bytes. A missing manifest keeps older checkouts valid.
    """
    manifest = root / IID_RUNTIME_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "owner_daily_iid_runtime_memory_source_transition/v1"
            or spec.get("base_commit") != IID_RUNTIME_BASE
            or spec.get("scope") != IID_RUNTIME_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") != "ebb592d0ceddc67f9186184c6e13f093c18ff0ddb749ccfc4e6b6cb49599a693"
            or not isinstance(sources, dict) or tuple(sources) != IID_RUNTIME_SOURCES):
        raise ValueError("IID_RUNTIME_MEMORY_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources.get(relative)
    if row is None:
        return active
    archive = "tests/fixtures/owner_daily_iid_runtime_memory_v1_sources/" + relative + ".txt"
    if set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"} or row.get("archive") != archive:
        raise ValueError("IID_RUNTIME_MEMORY_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("IID_RUNTIME_MEMORY_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _capture_only_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    manifest = root / "tests/fixtures/owner_daily_capture_only_source_transition_v1.json"
    if relative != "tools/run_owner_daily.py" or not manifest.exists():
        return active
    spec = json.loads(manifest.read_bytes())
    archive = "tests/fixtures/owner_daily_capture_only_v1_sources/tools/run_owner_daily.py.txt"
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "archive", "prior_sha256_lf", "active_sha256_lf"}
            or spec["contract_version"] != "owner_daily_capture_only_source_transition/v1"
            or spec["base_commit"] != "a46bc5606cdbeb083f251c7418168e500205142a"
            or spec["scope"] != "SHARED_CAPTURE_WRITER_LEASE_ONLY" or spec["release_authority"] != "NOT_GRANTED"
            or spec["archive"] != archive):
        raise ValueError("CAPTURE_WRITER_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    addition = b"from tools.capture_writer_lease import exclusive_writer\n\n\n@exclusive_writer\n"
    if (hashlib.sha256(prior).hexdigest() != spec["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != spec["active_sha256_lf"]
            or active.count(addition) != 1 or active.replace(addition, b"") != prior):
        raise ValueError("CAPTURE_WRITER_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _launcher_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Exact lifecycle/import successor; no earlier manifest or source pin changes."""
    active = _iid_runtime_prior_bytes(root, relative, _capture_only_prior_bytes(root, relative, active))
    if relative not in LAUNCHER_SOURCES or not (root / LAUNCHER_MANIFEST).exists():
        return active
    spec = json.loads((root / LAUNCHER_MANIFEST).read_bytes())
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources"}
            or spec["contract_version"] != "owner_daily_launcher_source_transition/v1"
            or spec["base_commit"] != "bff837a9f11fd127eb9326f5411fb6dee8c116f5"
            or spec["scope"] != "SEQUENTIAL_RELAUNCH_AND_DEFERRED_PUBLICATION_IMPORTS_ONLY"
            or spec["release_authority"] != "NOT_GRANTED"
            or tuple(spec["sources"]) != LAUNCHER_SOURCES):
        raise ValueError("LAUNCHER_SOURCE_TRANSITION_SCOPE_INVALID")
    row = spec["sources"][relative]
    archive = "tests/fixtures/owner_daily_launcher_v1_sources/" + relative + ".txt"
    if set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"} or row["archive"] != archive:
        raise ValueError("LAUNCHER_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("LAUNCHER_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _capacity_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Verify the one-file capacity successor while conserving all earlier pins.

    Only historical verification consumes the archive. Execution receipts still
    require the actual live bytes, never the pre-capacity launcher digest.
    """
    active = _launcher_prior_bytes(root, relative, active)
    if relative != CAPACITY_SOURCE or not (root / CAPACITY_MANIFEST).exists():
        return active
    spec = json.loads((root / CAPACITY_MANIFEST).read_bytes())
    if (set(spec) != {"contract_version", "base_commit", "source_path", "archive",
                      "prior_sha256_lf", "active_sha256_lf", "scope", "release_authority"}
            or spec.get("contract_version") != "owner_daily_capacity_source_transition/v1"
            or spec.get("base_commit") != "c19f72d794dccdeb34ecfe23a40e9ad7dbeef676"
            or spec.get("source_path") != CAPACITY_SOURCE or spec.get("archive") != CAPACITY_ARCHIVE
            or spec.get("scope") != "EXACT_ONE_FILE_CAPACITY_LAUNCH_CONTROL_ONLY"
            or spec.get("release_authority") != "NOT_GRANTED"):
        raise ValueError("CAPACITY_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / CAPACITY_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    layout = json.loads((root / LAYOUT_MANIFEST).read_bytes())["sources"][relative]
    if (hashlib.sha256(prior).hexdigest() != spec["prior_sha256_lf"]
            or spec["prior_sha256_lf"] != layout["active_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != spec["active_sha256_lf"]
            or spec["active_sha256_lf"] == spec["prior_sha256_lf"]):
        raise ValueError("CAPACITY_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _financial_research_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Same conservation rule as the storage transition, for the divergence pipeline leg."""
    manifest = root / FINANCIAL_RESEARCH_MANIFEST
    if not manifest.exists():
        return active
    spec = json.loads(manifest.read_bytes())
    if spec.get("contract_version") != "financial_research_source_transition/v1":
        raise ValueError("FINANCIAL_RESEARCH_SOURCE_TRANSITION_INVALID")
    row = spec["sources"].get(relative)
    if row is None:
        return active
    expected_archive = "tests/fixtures/financial_research_v1_sources/" + relative + ".txt"
    if row["archive"] != expected_archive:
        raise ValueError("FINANCIAL_RESEARCH_SOURCE_ARCHIVE_PATH_INVALID")
    prior = (root / expected_archive).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    # E2/E3-pinned files must reproduce their pin; E4 V2-only files bind to the archived
    # prior-release bytes (their own digest test then reproduces the historical code digest).
    expected = pins.get(relative, row["prior_sha256_lf"])
    if (row["prior_sha256_lf"] != expected or hashlib.sha256(prior).hexdigest() != expected
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]):
        raise ValueError("FINANCIAL_RESEARCH_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _storage_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Conserve exact pre-storage sources without repinning either historical domain."""
    active = _tplus_daily_prior_bytes(root, relative, active)
    active = _tplus_resume_prior_bytes(root, relative, active)
    manifest = root / STORAGE_MANIFEST
    if not manifest.exists():
        return active  # Released pre-storage checkout compatibility.
    spec = json.loads(manifest.read_bytes())
    if spec.get("contract_version") != "storage_portability_source_transition/v1":
        raise ValueError("STORAGE_SOURCE_TRANSITION_INVALID")
    row = spec["sources"].get(relative)
    if row is None:
        return active
    expected_archive = "tests/fixtures/storage_portability_v1_sources/" + relative + ".txt"
    if row["archive"] != expected_archive:
        raise ValueError("STORAGE_SOURCE_ARCHIVE_PATH_INVALID")
    prior = (root / expected_archive).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    expected = (json.loads((root / MANIFEST).read_bytes())["active_sha256_lf"]
                if relative == READER else pins[relative])
    if (row["prior_sha256_lf"] != expected or hashlib.sha256(prior).hexdigest() != expected
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]):
        raise ValueError("STORAGE_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _valuation_orchestration_prior_bytes(root: Path, relative: str) -> bytes:
    """Return archived origin/main bytes for the two approved orchestration sources.

    The closed set is the code constant above. A manifest that names any other
    file, or omits either approved file, is refused. Both the archive and the
    live file are hashed on every call.
    """
    if relative not in VALUATION_SOURCES:
        raise ValueError("VALUATION_SOURCE_TRANSITION_SCOPE_INVALID")
    manifest = root / VALUATION_MANIFEST
    if not manifest.is_file():
        raise ValueError("VALUATION_SOURCE_TRANSITION_INVALID")
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    admitted = spec.get("admitted_sources")
    if (spec.get("contract_version") != VALUATION_CONTRACT or spec.get("base_commit") != VALUATION_BASE
            or spec.get("exception_scope") != "EXACT_TWO_FILE_OWNER_APPROVED_NOT_A_GENERAL_TRANSITION"
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or not isinstance(admitted, list)
            or admitted != list(VALUATION_SOURCES) or list(sources) != list(VALUATION_SOURCES)):
        raise ValueError("VALUATION_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    expected_archive = "tests/fixtures/evidence_valuation_v1_sources/" + relative + ".txt"
    if not isinstance(row, dict) or row.get("archive") != expected_archive:
        raise ValueError("VALUATION_SOURCE_ARCHIVE_PATH_INVALID")
    if row.get("base_commit") != VALUATION_BASE:
        raise ValueError("VALUATION_SOURCE_TRANSITION_BASE_INVALID")
    active = _iid_runtime_prior_bytes(
        root, relative, _resident_prior_bytes(root, relative, (root / relative).read_bytes().replace(b"\r\n", b"\n")))
    prior = (root / expected_archive).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    prior_sha = hashlib.sha256(prior).hexdigest()
    active_sha = hashlib.sha256(active).hexdigest()
    if (row.get("prior_sha256_lf") != pins[relative] or prior_sha != pins[relative]
            or row.get("active_sha256_lf") != active_sha or active_sha == prior_sha):
        raise ValueError("VALUATION_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _thesis_production_prior_bytes(root: Path, relative: str) -> bytes:
    """Return archived origin/main bytes for the one approved Thesis source.

    The admitted path is the code constant above. A manifest that names another
    file, adds a field, or omits this file is refused. The archive and the live
    file are hashed on every call.
    """
    if relative != THESIS_SOURCE:
        raise ValueError("THESIS_SOURCE_TRANSITION_SCOPE_INVALID")
    manifest = root / THESIS_MANIFEST
    if not manifest.is_file():
        raise ValueError("THESIS_SOURCE_TRANSITION_INVALID")
    spec = json.loads(manifest.read_bytes())
    if set(spec) != _THESIS_FIELDS:
        raise ValueError("THESIS_SOURCE_TRANSITION_SCOPE_INVALID")
    if (spec.get("contract_version") != THESIS_CONTRACT or spec.get("base_commit") != THESIS_BASE
            or spec.get("exception_scope") != THESIS_SCOPE or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("source_path") != THESIS_SOURCE or spec.get("archive") != THESIS_ARCHIVE):
        raise ValueError("THESIS_SOURCE_TRANSITION_SCOPE_INVALID")
    active = (root / THESIS_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    prior = (root / THESIS_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    prior_sha = hashlib.sha256(prior).hexdigest()
    active_sha = hashlib.sha256(active).hexdigest()
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    pinned = pins.get(THESIS_SOURCE)
    if (spec.get("prior_sha256_lf") != prior_sha or spec.get("active_sha256_lf") != active_sha
            or active_sha == prior_sha or (pinned is not None and pinned != prior_sha)):
        raise ValueError("THESIS_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def historical_bytes(root: Path, relative: str) -> bytes:
    """Verify both sides of an approved boundary before supplying legacy bytes."""
    content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
    content = _capacity_prior_bytes(root, relative, content)
    content = _storage_prior_bytes(root, relative, content)
    if relative in VALUATION_SOURCES:
        return _valuation_orchestration_prior_bytes(root, relative)
    if relative == THESIS_SOURCE:
        return _thesis_production_prior_bytes(root, relative)
    content = _resident_prior_bytes(root, relative, content)
    content = _financial_research_prior_bytes(root, relative, content)
    if relative != READER:
        return content
    spec = json.loads((root / MANIFEST).read_bytes())
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    archive = (root / ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (spec["contract_version"] != "retention_reader_source_transition/v2" or
        spec["reader_path"] != READER or spec["legacy_archive"] != ARCHIVE or
        hashlib.sha256(archive).hexdigest() != pins[READER] or
        spec["legacy_sha256_lf"] != pins[READER] or
        hashlib.sha256(content).hexdigest() != spec["active_sha256_lf"] or
        spec["reader_version"] != "prospective_t0_origination_lineage/v2"):
        raise ValueError("RETENTION_READER_VERSION_BOUNDARY_INVALID")
    return archive


def legacy_source_identity(root: Path, *, version: str) -> dict:
    """Recompute the original closed hash domain; never return a historical constant."""
    if version not in {"v1", "v2"}:
        raise ValueError("E4_SOURCE_VERSION_UNSUPPORTED")
    digest = hashlib.sha256(b"e4_infrastructure_source/v2\0" if version == "v2" else b"")
    sources = list(e4.V1_SOURCES)
    if version == "v2":
        sources.extend((p, p) for p in e4.V2_SOURCES)
    for label, relative in sources:
        digest.update(label.encode() + b"\0" + hashlib.sha256(historical_bytes(root, relative)).digest())
    return {"source_version": version, "code_digest": digest.hexdigest(), "verification_scope": "HISTORICAL_SOURCE_ONLY"}


def active_valuation_orchestration_identity(root: Path) -> dict:
    """Attest the live orchestration sources without adopting their historical digest."""
    spec = json.loads((root / VALUATION_MANIFEST).read_bytes())
    execution = e4.source_identity(root, version="v1")
    execution_paths = {row["path"] for row in execution["sources"].values()}
    if set(VALUATION_SOURCES) & execution_paths:
        raise ValueError("VALUATION_SOURCE_EXECUTION_DOMAIN_INVALID")
    rows = {}
    for relative in VALUATION_SOURCES:
        historical = historical_bytes(root, relative)
        active = _iid_runtime_prior_bytes(
            root, relative, _resident_prior_bytes(root, relative, (root / relative).read_bytes().replace(b"\r\n", b"\n")))
        historical_sha = hashlib.sha256(historical).hexdigest()
        active_sha = hashlib.sha256(active).hexdigest()
        declared = spec["sources"][relative]
        if (historical_sha != declared["prior_sha256_lf"] or active_sha != declared["active_sha256_lf"]
                or active_sha == historical_sha):
            raise ValueError("VALUATION_SOURCE_TRANSITION_BINDING_INVALID")
        rows[relative] = {"historical_sha256_lf": historical_sha, "active_sha256_lf": active_sha}
    return {
        "contract_version": VALUATION_CONTRACT,
        "base_commit": VALUATION_BASE,
        "sources": rows,
        "execution_code_digest": execution["code_digest"],
        "execution_source_version": execution["source_version"],
        "historical_receipt_adoption": False,
        "cache_policy": "EXACT_ACTIVE_BYTES_REQUIRED_NO_HISTORICAL_RECEIPT_ADOPTION",
        "release_authority": "NOT_GRANTED",
    }


def active_thesis_evidence_identity(root: Path) -> dict:
    """Attest the live Thesis source without adopting its historical or mixed digest."""
    spec = json.loads((root / THESIS_MANIFEST).read_bytes())
    historical_file = historical_bytes(root, THESIS_SOURCE)
    active_file = (root / THESIS_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    historical_sha = hashlib.sha256(historical_file).hexdigest()
    active_sha = hashlib.sha256(active_file).hexdigest()
    if (historical_sha != spec["prior_sha256_lf"] or active_sha != spec["active_sha256_lf"]
            or active_sha == historical_sha):
        raise ValueError("THESIS_SOURCE_TRANSITION_BINDING_INVALID")
    execution = e4.source_identity(root, version="v2")
    historical = legacy_source_identity(root, version="v2")
    if THESIS_SOURCE not in {row["path"] for row in execution["sources"].values()}:
        raise ValueError("THESIS_SOURCE_EXECUTION_DOMAIN_INVALID")
    if historical["code_digest"] != spec["historical_e4_v2_digest"]:
        raise ValueError("THESIS_SOURCE_HISTORICAL_DIGEST_MISMATCH")
    expected_execution = spec["active_e4_v2_digest"]
    successor = _tplus_resume_spec(root)
    if successor is not None:
        if successor["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = successor["active_e4_v2_digest"]
    daily = _tplus_daily_spec(root)
    if daily is not None:
        if daily["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = daily["active_e4_v2_digest"]
    resident = _resident_spec(root)
    if resident is not None:
        if resident["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = resident["active_e4_v2_digest"]
    if execution["code_digest"] != expected_execution or execution["code_digest"] == historical["code_digest"]:
        raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
    if spec["rejected_mixed_digest"] in {execution["code_digest"], historical["code_digest"]}:
        raise ValueError("THESIS_SOURCE_MIXED_DIGEST_REJECTED")
    historical_receipt = {
        "source_version": "v2", "contract_version": "e4_infrastructure_source/v2",
        "code_digest": historical["code_digest"], "input_digest": "historical-receipt",
    }
    mixed_receipt = {**historical_receipt, "code_digest": spec["rejected_mixed_digest"]}
    if (e4.candidate_reuse_eligible(historical_receipt, execution, input_digest="historical-receipt")
            or e4.candidate_reuse_eligible(mixed_receipt, execution, input_digest="historical-receipt")):
        raise ValueError("THESIS_SOURCE_HISTORICAL_RECEIPT_ADOPTED")
    return {
        "contract_version": THESIS_CONTRACT,
        "base_commit": THESIS_BASE,
        "source_path": THESIS_SOURCE,
        "historical_sha256_lf": historical_sha,
        "active_sha256_lf": active_sha,
        "historical_e4_v2_digest": historical["code_digest"],
        "active_e4_v2_digest": execution["code_digest"],
        "historical_receipt_adoption": False,
        "cache_policy": "EXACT_ACTIVE_BYTES_REQUIRED_NO_HISTORICAL_RECEIPT_ADOPTION",
        "release_authority": "NOT_GRANTED",
    }


def active_reader_identity(root: Path) -> dict:
    historical_bytes(root, READER)
    spec = json.loads((root / MANIFEST).read_bytes())
    active = e4.source_identity(root, version="v1")
    return {"reader_version": spec["reader_version"], "execution_code_digest": active["code_digest"],
            "source_version": "retention_reader_source/v2", "legacy_receipt_adoption": False,
            "cache_policy": "EXACT_EXECUTION_AND_VERIFIER_DIGEST_REQUIRED_NO_CROSS_VERSION_ADOPTION"}


def layout_transition_identity(root: Path) -> dict:
    """Bind the layout import-retarget transition to archived base bytes and the live files.

    The archived base bytes reproduce the digest each governing manifest declared before
    this transition; the governing manifest now declares the live digest; the original
    E2/E3 pin is still reproduced only through ``historical_bytes``. Nothing is adopted
    across versions, and every file is hashed on every call.
    """
    spec = json.loads((root / LAYOUT_MANIFEST).read_bytes())
    if (spec.get("contract_version") != LAYOUT_CONTRACT or spec.get("base_commit") != LAYOUT_BASE
            or spec.get("exception_scope") != LAYOUT_SCOPE or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(spec.get("sources"), dict) or list(spec["sources"]) != list(LAYOUT_SOURCES)):
        raise ValueError("LAYOUT_SOURCE_TRANSITION_SCOPE_INVALID")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    rows = {}
    for relative, governing in LAYOUT_SOURCES.items():
        row = spec["sources"][relative]
        expected_archive = "tests/fixtures/repository_layout_v1_sources/" + relative + ".txt"
        if not isinstance(row, dict) or row.get("archive") != expected_archive or row.get("governing_manifest") != governing:
            raise ValueError("LAYOUT_SOURCE_ARCHIVE_PATH_INVALID")
        prior_sha = hashlib.sha256((root / expected_archive).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        live = (root / relative).read_bytes().replace(b"\r\n", b"\n")
        active_sha = hashlib.sha256(_capacity_prior_bytes(root, relative, _resident_prior_bytes(root, relative, live))).hexdigest()
        declared = json.loads((root / governing).read_bytes())["sources"][relative]["active_sha256_lf"]
        if (row.get("prior_sha256_lf") != prior_sha or row.get("active_sha256_lf") != active_sha
                or prior_sha == active_sha or declared != active_sha
                or row.get("historical_pin_sha256_lf") != pins[relative]
                or hashlib.sha256(historical_bytes(root, relative)).hexdigest() != pins[relative]):
            raise ValueError("LAYOUT_SOURCE_TRANSITION_BINDING_INVALID")
        rows[relative] = {"historical_pin_sha256_lf": pins[relative], "prior_sha256_lf": prior_sha,
                          "active_sha256_lf": hashlib.sha256(live).hexdigest()}
    return {
        "contract_version": LAYOUT_CONTRACT,
        "base_commit": LAYOUT_BASE,
        "sources": rows,
        "historical_receipt_adoption": False,
        "cache_policy": "EXACT_ACTIVE_BYTES_REQUIRED_NO_HISTORICAL_RECEIPT_ADOPTION",
        "release_authority": "NOT_GRANTED",
    }


def layout_source_receipt_admissible(root: Path, relative: str, receipt_sha256_lf: str) -> bool:
    """A source receipt proves only the exact live bytes; base and original digests never qualify."""
    return receipt_sha256_lf == layout_transition_identity(root)["sources"][relative]["active_sha256_lf"]
