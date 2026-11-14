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
TPLUS_REAL_CORPUS_MANIFEST = "tests/fixtures/tplus_real_t0_corpus_source_transition_v1.json"
TPLUS_REAL_CORPUS_BASE = "f56cab5e7c2bd821898cd8bee5a5a90f2ffa3551"
TPLUS_REAL_CORPUS_SCOPE = "EXACT_TPLUS_EVIDENCE_ROOT_AND_EMPTY_CORPUS_REFUSAL_ONLY"
TPLUS_REAL_CORPUS_SOURCES = (TPLUS_RESUME_SOURCE, "canonical_post_close_pipeline.py")
TPLUS_INCREMENTAL_MANIFEST = "tests/fixtures/tplus_incremental_cost_v2_source_transition_v1.json"
TPLUS_INCREMENTAL_BASE = "f43471435403c0de8efc2e6fd800e2b83356b9b6"
TPLUS_INCREMENTAL_SCOPE = "EXACT_TPLUS_INCREMENTAL_COST_ONLY"
TPLUS_INCREMENTAL_ARCHIVE = "tests/fixtures/tplus_incremental_cost_v2_sources/prospective_feedback_streaming.py.txt"
TPLUS_FEEDBACK_IO_MANIFEST = "tests/fixtures/tplus_feedback_io_source_transition_v1.json"
TPLUS_FEEDBACK_IO_ARCHIVE = "tests/fixtures/tplus_feedback_io_v1_sources/prospective_feedback_streaming.py.txt"
TPLUS_FEEDBACK_IO_BASE = "6ddfcd57285a06fb7ed72e4623718095850559c0"
TPLUS_FEEDBACK_IO_SCOPE = "SETTLED_READ_AND_ASSEMBLY_READBACK_ONLY"
TPLUS_M1B_MANIFEST = "tests/fixtures/tplus_incremental_cost_v2_m1b_source_transition_v1.json"
STORAGE_REUSE_D4A_MANIFEST = "tests/fixtures/storage_reuse_d4a_source_transition_v1.json"
STORAGE_REUSE_D4A_BASE = "0258f391bd3e81256a7480dd171062a76af6d9ca"
STORAGE_REUSE_D4A_SCOPE = "EXACT_STORAGE_REUSE_D4A_SWITCHES_AND_IID_VIEW_LINK_ONLY"
STORAGE_REUSE_D4A_SOURCE = "canonical_post_close_pipeline.py"
STORAGE_REUSE_D4A_ARCHIVE = "tests/fixtures/storage_reuse_d4a_sources/canonical_post_close_pipeline.py.txt"
TPLUS_M1B_BASE = "dc220164b6a4eb2b6fbec8175e588d6de9ab5553"
TPLUS_M1B_SCOPE = "EXACT_TPLUS_INCREMENTAL_COST_M1B_ONLY"
TPLUS_M1B_ARCHIVE = "tests/fixtures/tplus_incremental_cost_v2_m1b_sources/prospective_feedback_streaming.py.txt"
THESIS_ROOT_MANIFEST = "tests/fixtures/thesis_current_technical_root_source_transition_v1.json"
THESIS_ROOT_BASE = "83897636e1813ad0b6a016c0a8d50b3f5430ea27"
THESIS_ROOT_SCOPE = "EXACT_THESIS_CURRENT_STAGE_ENRICHMENT_ROOT_ONLY"
THESIS_ROOT_ARCHIVE = "tests/fixtures/thesis_current_technical_root_sources/thesis_evidence_production.py.txt"
LEGACY_SUMMARY_MANIFEST = "tests/fixtures/tplus_legacy_summary_fingerprint_source_transition_v1.json"
LEGACY_SUMMARY_BASE = "58b42b664d8e5008bd1e8e16f7cb167b52b60d21"
LEGACY_SUMMARY_SCOPE = "EXACT_TPLUS_LEGACY_SUMMARY_FINGERPRINT_REUSE_ONLY"
LEGACY_SUMMARY_SOURCE = "prospective_decision_outcome_feedback.py"
LEGACY_SUMMARY_ARCHIVE = "tests/fixtures/tplus_legacy_summary_fingerprint_sources/prospective_decision_outcome_feedback.py.txt"
DECISION_CONTEXT_MANIFEST = "tests/fixtures/decision_context_premarket_source_transition_v1.json"
DECISION_CONTEXT_BASE = "73ab3b7f959eeb13f98bdebc8dc7e2496d6f2f4f"
DECISION_CONTEXT_SCOPE = "EXACT_BRIEF_MATCHED_COHORT_AND_MARKET_GATED_ADDITIVE_FIELDS_ONLY"
DECISION_CONTEXT_SOURCE = "stocklookup_core/decision/daily_integrated_decision_brief.py"
DECISION_CONTEXT_ARCHIVE = "tests/fixtures/decision_context_premarket_sources/daily_integrated_decision_brief.py.txt"
DECISION_CONTEXT_PRIOR_SHA256_LF = "928a8098c3884bc52e1e7db9403f19475fab9823964c71bee2dc7f26dfa86492"
OCR_RECOGNITION_MANIFEST = "tests/fixtures/ocr_unit_period_recognition_source_transition_v1.json"
OCR_RECOGNITION_BASE = "b6c34442db28dfd249680e249ae59fc9494bfd84"
OCR_RECOGNITION_SCOPE = "EXACT_OCR_UNIT_LABEL_AND_H1_OPERATING_PERIOD_RECOGNITION_ONLY"
OCR_RECOGNITION_SOURCES = ("financial_statement_unit_resolution.py", "official_financial_period_identity.py")
ARCHITECTURE_BASELINE_SOURCE = "config/architecture_dependency_baseline.json"
ARCHITECTURE_BASELINE_MANIFEST = "tests/fixtures/architecture_dependency_baseline_source_transition_v1.json"
ARCHITECTURE_BASELINE_ARCHIVE = "tests/fixtures/architecture_dependency_baseline_v1.json.txt"
ARCHITECTURE_BASELINE_BASE = "b83fd916b02e245e0c6b10078060809bb31b971d"
ARCHITECTURE_BASELINE_SCOPE = "EXACT_ONE_FILE_M1B_GRANDFATHERED_EDGES_ONLY"
_ARCHITECTURE_BASELINE_FIELDS = frozenset({
    "contract_version", "base_commit", "source_path", "archive",
    "prior_sha256_lf", "active_sha256_lf", "scope", "release_authority",
})
RESIDENT_MANIFEST = "tests/fixtures/owner_daily_resident_iid_source_transition_v1.json"
RESIDENT_SOURCES = ("canonical_daily_operation.py", "stocklookup_core/decision/daily_integrated_decision_brief.py")
RESIDENT_PRIOR_PINS = ("16172dae8073ebef819022b3bad71ca216c22e6c0ddbaa3ea31535fe5557cc7c",
                       "e39c49ee1e20958617d92aaef51b530f27da18003cab59c592670090fc98c5a1")
BRIEF_INPUT_MANIFEST = "tests/fixtures/owner_daily_brief_inputs_source_transition_v1.json"
BRIEF_INPUT_SOURCE = "stocklookup_core/decision/daily_integrated_decision_brief.py"
BRIEF_INPUT_ARCHIVE = "tests/fixtures/owner_daily_brief_inputs_v1_sources/daily_integrated_decision_brief.py.txt"
EVALUATED_INPUT_MANIFEST = "tests/fixtures/owner_daily_evaluated_input_source_transition_v1.json"
EVALUATED_INPUT_SOURCE = "canonical_daily_operation.py"
EVALUATED_INPUT_ARCHIVE = "tests/fixtures/owner_daily_evaluated_input_v1_sources/canonical_daily_operation.py.txt"
POST_PRODUCER_MANIFEST = "tests/fixtures/owner_daily_post_producer_source_transition_v1.json"
POST_PRODUCER_ARCHIVE = "tests/fixtures/owner_daily_post_producer_v1_sources/canonical_daily_operation.py.txt"


def _post_producer_spec(root: Path) -> dict | None:
    path = root / POST_PRODUCER_MANIFEST
    if not path.is_file():
        return None
    spec = json.loads(path.read_bytes())
    digest = "5f5229a90fc24f8728ce48a6f50f804f2fc8fddc33e473bc7003268092173576"
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "owner_daily_post_producer_source_transition/v1"
            or spec.get("base_commit") != "bcca504efacd70c1cd2a4b4cf107ad867cb05474"
            or spec.get("scope") != "EXACT_POST_PRODUCER_ARGUMENT_LIFETIME_ONLY"
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") != digest or spec.get("active_e4_v2_digest") != digest
            or not isinstance(spec.get("sources"), dict) or tuple(spec["sources"]) != (EVALUATED_INPUT_SOURCE,)):
        raise ValueError("POST_PRODUCER_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


TACTICAL_SHADOW_MANIFEST = "tests/fixtures/owner_daily_tactical_shadow_source_transition_v1.json"
TACTICAL_SHADOW_SOURCES = ("canonical_daily_operation.py", "tools/run_owner_daily.py", "daily_analysis_pipeline.py")
TACTICAL_SHADOW_PIPELINE = "daily_analysis_pipeline.py"  # E2/E3-pinned; peeled first in historical_bytes.


def _tactical_shadow_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Conserve both historical source chains across the optional observer dispatch."""
    manifest = root / TACTICAL_SHADOW_MANIFEST
    if relative not in TACTICAL_SHADOW_SOURCES or not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    if (spec.get("base_commit") != "7d2c6915a84a9576c5783336ddca13995aaeb13f"
            or spec.get("scope") != "DEFER_TACTICAL_SHADOW_IN_CORE_AI_ONLY"
            or tuple(spec.get("sources", {})) != TACTICAL_SHADOW_SOURCES):
        raise ValueError("TACTICAL_SHADOW_SOURCE_TRANSITION_SCOPE_INVALID")
    row = spec["sources"][relative]
    archive = manifest.with_name(manifest.stem + "_sources") / (relative + ".txt")
    prior = archive.read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TACTICAL_SHADOW_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _post_producer_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    if relative != EVALUATED_INPUT_SOURCE:
        return active
    active = _tactical_shadow_prior_bytes(root, relative, active)
    spec = _post_producer_spec(root)
    if spec is None:
        return active
    row = spec["sources"][relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != POST_PRODUCER_ARCHIVE):
        raise ValueError("POST_PRODUCER_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / POST_PRODUCER_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (row["prior_sha256_lf"] != "65da460e211b8222b76a73066a92efade27cf6d2d689d7f0239f913292d7533a"
            or hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("POST_PRODUCER_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _evaluated_input_spec(root: Path) -> dict | None:
    path = root / EVALUATED_INPUT_MANIFEST
    if not path.is_file():
        return None
    spec = json.loads(path.read_bytes())
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "owner_daily_evaluated_input_source_transition/v1"
            or spec.get("base_commit") != "ce188125582fb6fb2cd6c9bb064f83bf0e7ec1a7"
            or spec.get("scope") != "EXACT_DAILY_EVALUATED_VALUATION_ALLOCATION_ONLY"
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") != "5f5229a90fc24f8728ce48a6f50f804f2fc8fddc33e473bc7003268092173576"
            or not isinstance(spec.get("sources"), dict) or tuple(spec["sources"]) != (EVALUATED_INPUT_SOURCE,)):
        raise ValueError("EVALUATED_INPUT_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


def _evaluated_input_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    active = _post_producer_prior_bytes(root, relative, active)
    if relative != EVALUATED_INPUT_SOURCE:
        return active
    spec = _evaluated_input_spec(root)
    if spec is None:
        return active
    row = spec["sources"][relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != EVALUATED_INPUT_ARCHIVE):
        raise ValueError("EVALUATED_INPUT_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / EVALUATED_INPUT_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (row["prior_sha256_lf"] != "d828e9710d559192dbd4bfd19743fba414851942e0c4ae8bc99a38b1fb0622b8"
            or hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("EVALUATED_INPUT_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _brief_input_spec(root: Path) -> dict | None:
    path = root / BRIEF_INPUT_MANIFEST
    if not path.is_file():
        return None
    spec = json.loads(path.read_bytes())
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "owner_daily_brief_inputs_source_transition/v1"
            or spec.get("base_commit") != "dc9977141863729a849a2f1fb85be9a27e2b2332"
            or spec.get("scope") != "EXACT_BRIEF_SUPPLEMENTARY_INPUT_ALLOCATION_ONLY"
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") != "1e169a11fec8d571c84595b506f3fa6a5712d0b0a1cc4b6279a44b3d9fd8eb8a"
            or not isinstance(spec.get("sources"), dict) or tuple(spec["sources"]) != (BRIEF_INPUT_SOURCE,)):
        raise ValueError("BRIEF_INPUT_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


def _brief_input_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    if relative != BRIEF_INPUT_SOURCE:
        return active
    spec = _brief_input_spec(root)
    if spec is None:
        return active
    row = spec["sources"][relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != BRIEF_INPUT_ARCHIVE):
        raise ValueError("BRIEF_INPUT_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / BRIEF_INPUT_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (row["prior_sha256_lf"] != "3badc2ae45005d08dfb983996eb0097b778339278a669fee9c4d6ba0cad6b5f0"
            or hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("BRIEF_INPUT_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


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
    active = _evaluated_input_prior_bytes(root, relative, active)
    active = _brief_input_prior_bytes(root, relative, active)
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


def _storage_reuse_d4a_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the D4a storage-reuse successor before the 2026-11-03 evidence-root pin.

    Only ``canonical_post_close_pipeline.py`` changed (Owner switches, IID view link, one
    producer keyword). E4 v2 digest is unchanged. Bytes that are not the D4a active source
    pass through so older layers keep their own fail-closed checks.
    """
    if relative != STORAGE_REUSE_D4A_SOURCE:
        return active
    manifest = root / STORAGE_REUSE_D4A_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "storage_reuse_d4a_source_transition/v1"
            or spec.get("base_commit") != STORAGE_REUSE_D4A_BASE
            or spec.get("scope") != STORAGE_REUSE_D4A_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") != spec.get("active_e4_v2_digest")
            or not isinstance(sources, dict) or tuple(sources) != (STORAGE_REUSE_D4A_SOURCE,)):
        raise ValueError("STORAGE_REUSE_D4A_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != STORAGE_REUSE_D4A_ARCHIVE):
        raise ValueError("STORAGE_REUSE_D4A_SOURCE_TRANSITION_SCOPE_INVALID")
    if hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]:
        return active
    prior = (root / STORAGE_REUSE_D4A_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"] or row["prior_sha256_lf"] == row["active_sha256_lf"]:
        raise ValueError("STORAGE_REUSE_D4A_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _tplus_real_corpus_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the 2026-11-03 T+ evidence-root successor before every older pin of the same source.

    Only the feedback child's ``--root`` (operation evidence root) and the explicit empty-corpus
    refusal changed. Older manifests stay unchanged; a missing manifest keeps older checkouts valid.
    """
    active = _storage_reuse_d4a_prior_bytes(root, relative, active)
    manifest = root / TPLUS_REAL_CORPUS_MANIFEST
    if relative not in TPLUS_REAL_CORPUS_SOURCES or not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_real_t0_corpus_source_transition/v1"
            or spec.get("base_commit") != TPLUS_REAL_CORPUS_BASE
            or spec.get("scope") != TPLUS_REAL_CORPUS_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != TPLUS_REAL_CORPUS_SOURCES):
        raise ValueError("TPLUS_REAL_CORPUS_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    archive = "tests/fixtures/tplus_real_t0_corpus_v1_sources/" + relative + ".txt"
    if not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"} or row.get("archive") != archive:
        raise ValueError("TPLUS_REAL_CORPUS_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_REAL_CORPUS_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _tplus_feedback_io_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Conserve the released M1b bytes across the offline-verified I/O corrective."""
    if relative != TPLUS_RESUME_SOURCE:
        return active
    manifest = root / TPLUS_FEEDBACK_IO_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_feedback_io_source_transition/v1"
            or spec.get("base_commit") != TPLUS_FEEDBACK_IO_BASE
            or spec.get("scope") != TPLUS_FEEDBACK_IO_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != (TPLUS_RESUME_SOURCE,)):
        raise ValueError("TPLUS_FEEDBACK_IO_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != TPLUS_FEEDBACK_IO_ARCHIVE):
        raise ValueError("TPLUS_FEEDBACK_IO_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / TPLUS_FEEDBACK_IO_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_FEEDBACK_IO_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _tplus_m1b_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the M1b successor before the M1 incremental-cost pin.

    Only ``prospective_feedback_streaming.py`` changed. A missing manifest keeps older checkouts valid.
    """
    if relative != TPLUS_RESUME_SOURCE:
        return active
    active = _tplus_feedback_io_prior_bytes(root, relative, active)
    manifest = root / TPLUS_M1B_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_incremental_cost_v2_m1b_source_transition/v1"
            or spec.get("base_commit") != TPLUS_M1B_BASE
            or spec.get("scope") != TPLUS_M1B_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != (TPLUS_RESUME_SOURCE,)):
        raise ValueError("TPLUS_M1B_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != TPLUS_M1B_ARCHIVE):
        raise ValueError("TPLUS_M1B_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / TPLUS_M1B_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_M1B_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _tplus_incremental_cost_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the fingerprint and sidecar cost successor before the 2026-11-03 evidence-root pin.

    Only ``prospective_feedback_streaming.py`` changed. The pipeline file is not in this layer,
    so it stays on the real-corpus pin. A missing manifest keeps older checkouts valid.
    """
    if relative != TPLUS_RESUME_SOURCE:
        return active
    manifest = root / TPLUS_INCREMENTAL_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_incremental_cost_v2_source_transition/v1"
            or spec.get("base_commit") != TPLUS_INCREMENTAL_BASE
            or spec.get("scope") != TPLUS_INCREMENTAL_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != (TPLUS_RESUME_SOURCE,)):
        raise ValueError("TPLUS_INCREMENTAL_COST_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != TPLUS_INCREMENTAL_ARCHIVE):
        raise ValueError("TPLUS_INCREMENTAL_COST_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / TPLUS_INCREMENTAL_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_INCREMENTAL_COST_SOURCE_TRANSITION_BINDING_INVALID")
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
    if relative == "canonical_post_close_pipeline.py":
        active = _tplus_real_corpus_prior_bytes(root, relative, active)
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


def _multi_freeze_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the 2026-11-02 sealed-row registry commit successor before the capture-only pin."""
    manifest = root / "tests/fixtures/owner_daily_multi_freeze_source_transition_v1.json"
    if relative != "tools/run_owner_daily.py" or not manifest.exists():
        return active
    spec = json.loads(manifest.read_bytes())
    archive = "tests/fixtures/owner_daily_multi_freeze_v1_sources/tools/run_owner_daily.py.txt"
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "archive", "prior_sha256_lf", "active_sha256_lf"}
            or spec["contract_version"] != "owner_daily_multi_freeze_source_transition/v1"
            or spec["base_commit"] != "db496b390606b09eab3a9f9d5f6b977150d3ad00"
            or spec["scope"] != "SEALED_SESSION_REGISTRY_COMMIT_ONLY" or spec["release_authority"] != "NOT_GRANTED"
            or spec["archive"] != archive):
        raise ValueError("MULTI_FREEZE_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != spec["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != spec["active_sha256_lf"]
            or spec["prior_sha256_lf"] == spec["active_sha256_lf"]):
        raise ValueError("MULTI_FREEZE_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _core_ai_fast_path_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the Owner workflow-mode successor before the publication-conclusion pin."""
    manifest = root / "tests/fixtures/owner_daily_core_ai_fast_path_source_transition_v1.json"
    if relative != "tools/run_owner_daily.py" or not manifest.exists():
        return active
    active = _tactical_shadow_prior_bytes(root, relative, active)
    spec = json.loads(manifest.read_bytes())
    archive = "tests/fixtures/owner_daily_core_ai_fast_path_v1_sources/tools/run_owner_daily.py.txt"
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "archive", "prior_sha256_lf", "active_sha256_lf"}
            or spec["contract_version"] != "owner_daily_core_ai_fast_path_source_transition/v1"
            or spec["base_commit"] != "cfa53162efa236a2b27ed421b159743f5451375d"
            or spec["scope"] != "OWNER_WORKFLOW_MODE_CORE_AI_DEFAULT_AND_EXPLICIT_FULL_PUBLISH_ONLY"
            or spec["release_authority"] != "NOT_GRANTED"
            or spec["archive"] != archive):
        raise ValueError("CORE_AI_FAST_PATH_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != spec["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != spec["active_sha256_lf"]
            or spec["prior_sha256_lf"] == spec["active_sha256_lf"]):
        raise ValueError("CORE_AI_FAST_PATH_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _publication_conclusion_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the Dashboard CI conclusion classifier before the pending-commit pin."""
    manifest = root / "tests/fixtures/owner_daily_publication_conclusion_source_transition_v1.json"
    if relative != "tools/run_owner_daily.py" or not manifest.exists():
        return active
    spec = json.loads(manifest.read_bytes())
    archive = "tests/fixtures/owner_daily_publication_conclusion_v1_sources/tools/run_owner_daily.py.txt"
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "archive", "prior_sha256_lf", "active_sha256_lf"}
            or spec["contract_version"] != "owner_daily_publication_conclusion_source_transition/v1"
            or spec["base_commit"] != "f5fdbec888c971165065786e8221d67cc420a611"
            or spec["scope"] != "DASHBOARD_PUBLICATION_CONCLUSION_CLASSIFICATION_ONLY"
            or spec["release_authority"] != "NOT_GRANTED"
            or spec["archive"] != archive):
        raise ValueError("PUBLICATION_CONCLUSION_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != spec["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != spec["active_sha256_lf"]
            or spec["prior_sha256_lf"] == spec["active_sha256_lf"]):
        raise ValueError("PUBLICATION_CONCLUSION_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _pending_commit_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the 2026-11-04 exact pending commit recovery successor before the capture-only pin."""
    manifest = root / "tests/fixtures/owner_daily_pending_commit_source_transition_v1.json"
    if relative != "tools/run_owner_daily.py" or not manifest.exists():
        return active
    spec = json.loads(manifest.read_bytes())
    archive = "tests/fixtures/owner_daily_pending_commit_v1_sources/tools/run_owner_daily.py.txt"
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "archive", "prior_sha256_lf", "active_sha256_lf"}
            or spec["contract_version"] != "owner_daily_pending_commit_source_transition/v1"
            or spec["base_commit"] != "d999d847ee3730931ea14909053950e4ac1cf5b6"
            or spec["scope"] != "EXACT_COMPLETED_SESSION_PENDING_COMMIT_RECOVERY_ONLY" or spec["release_authority"] != "NOT_GRANTED"
            or spec["archive"] != archive):
        raise ValueError("PENDING_COMMIT_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != spec["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != spec["active_sha256_lf"]
            or spec["prior_sha256_lf"] == spec["active_sha256_lf"]):
        raise ValueError("PENDING_COMMIT_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _launcher_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Exact lifecycle/import successor; no earlier manifest or source pin changes."""
    active = _core_ai_fast_path_prior_bytes(root, relative, active)
    active = _publication_conclusion_prior_bytes(root, relative, active)
    active = _pending_commit_prior_bytes(root, relative, active)
    active = _multi_freeze_prior_bytes(root, relative, active)
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
    if relative == TPLUS_RESUME_SOURCE:
        active = _tplus_m1b_prior_bytes(root, relative, active)
        active = _tplus_incremental_cost_prior_bytes(root, relative, active)
        active = _tplus_real_corpus_prior_bytes(root, relative, active)
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


def _thesis_root_spec(root: Path) -> dict | None:
    """Successor of the M1b pin: current-stage enrichment batch under governed roots.

    Only ``thesis_evidence_production.py`` changed (exact relative path searched under the
    checkout, the build output root and the governed evidence roots; differing copies refuse).
    T0 semantics are unchanged. A missing manifest keeps older checkouts valid.
    """
    manifest = root / THESIS_ROOT_MANIFEST
    if not manifest.is_file():
        return None
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "thesis_current_technical_root_source_transition/v1"
            or spec.get("base_commit") != THESIS_ROOT_BASE
            or spec.get("scope") != THESIS_ROOT_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or spec.get("previous_e4_v2_digest") == spec.get("active_e4_v2_digest")
            or not isinstance(sources, dict) or tuple(sources) != (THESIS_SOURCE,)):
        raise ValueError("THESIS_ROOT_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[THESIS_SOURCE]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != THESIS_ROOT_ARCHIVE):
        raise ValueError("THESIS_ROOT_SOURCE_TRANSITION_SCOPE_INVALID")
    return spec


def _thesis_root_prior_bytes(root: Path, active: bytes) -> bytes:
    spec = _thesis_root_spec(root)
    if spec is None:
        return active
    row = spec["sources"][THESIS_SOURCE]
    prior = (root / THESIS_ROOT_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("THESIS_ROOT_SOURCE_TRANSITION_BINDING_INVALID")
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
    active = _thesis_root_prior_bytes(root, (root / THESIS_SOURCE).read_bytes().replace(b"\r\n", b"\n"))
    prior = (root / THESIS_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    prior_sha = hashlib.sha256(prior).hexdigest()
    active_sha = hashlib.sha256(active).hexdigest()
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    pinned = pins.get(THESIS_SOURCE)
    if (spec.get("prior_sha256_lf") != prior_sha or spec.get("active_sha256_lf") != active_sha
            or active_sha == prior_sha or (pinned is not None and pinned != prior_sha)):
        raise ValueError("THESIS_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _architecture_baseline_prior_bytes(root: Path, active: bytes) -> bytes:
    """Peel the M1b grandfathered edges back to the frozen baseline pin.

    A missing manifest keeps older checkouts valid. The archive is the baseline
    at ARCHITECTURE_BASELINE_BASE. Historical readers keep that pin; the live
    file is the requalified ratchet surface.
    """
    manifest = root / ARCHITECTURE_BASELINE_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    if set(spec) != _ARCHITECTURE_BASELINE_FIELDS:
        raise ValueError("ARCHITECTURE_BASELINE_SOURCE_TRANSITION_SCOPE_INVALID")
    if (spec.get("contract_version") != "architecture_dependency_baseline_source_transition/v1"
            or spec.get("base_commit") != ARCHITECTURE_BASELINE_BASE
            or spec.get("source_path") != ARCHITECTURE_BASELINE_SOURCE
            or spec.get("archive") != ARCHITECTURE_BASELINE_ARCHIVE
            or spec.get("scope") != ARCHITECTURE_BASELINE_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"):
        raise ValueError("ARCHITECTURE_BASELINE_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / ARCHITECTURE_BASELINE_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    pins = json.loads((root / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    prior_sha = hashlib.sha256(prior).hexdigest()
    active_sha = hashlib.sha256(active).hexdigest()
    if (spec.get("prior_sha256_lf") != prior_sha or prior_sha != pins.get(ARCHITECTURE_BASELINE_SOURCE)
            or spec.get("active_sha256_lf") != active_sha or active_sha == prior_sha):
        raise ValueError("ARCHITECTURE_BASELINE_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _ocr_recognition_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the 2026-11-07 OCR recognition successor (Owner approved "fix the parser").

    Only two recognizers changed: an OCR glyph variant of a bare unit-label line ("Bon vi:" /
    "Don vj:" + one explicit currency) and the VAS phrase "kỳ hoạt động 6 tháng kết thúc ngày
    30 tháng 6 năm YYYY". A missing manifest keeps older checkouts valid; other bytes pass through.
    """
    if relative not in OCR_RECOGNITION_SOURCES:
        return active
    manifest = root / OCR_RECOGNITION_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources"}
            or spec.get("contract_version") != "ocr_unit_period_recognition_source_transition/v1"
            or spec.get("base_commit") != OCR_RECOGNITION_BASE
            or spec.get("scope") != OCR_RECOGNITION_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != OCR_RECOGNITION_SOURCES):
        raise ValueError("OCR_RECOGNITION_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    archive = "tests/fixtures/ocr_unit_period_recognition_sources/" + relative + ".txt"
    if not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"} or row.get("archive") != archive:
        raise ValueError("OCR_RECOGNITION_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / archive).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("OCR_RECOGNITION_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _legacy_summary_fingerprint_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the legacy summary-fingerprint reuse before the frozen storage pin.

    Only ``prospective_decision_outcome_feedback.py`` changed. A missing manifest keeps older checkouts valid.
    """
    if relative != LEGACY_SUMMARY_SOURCE:
        return active
    manifest = root / LEGACY_SUMMARY_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "tplus_legacy_summary_fingerprint_source_transition/v1"
            or spec.get("base_commit") != LEGACY_SUMMARY_BASE
            or spec.get("scope") != LEGACY_SUMMARY_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != (LEGACY_SUMMARY_SOURCE,)):
        raise ValueError("TPLUS_LEGACY_SUMMARY_FINGERPRINT_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != LEGACY_SUMMARY_ARCHIVE):
        raise ValueError("TPLUS_LEGACY_SUMMARY_FINGERPRINT_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / LEGACY_SUMMARY_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("TPLUS_LEGACY_SUMMARY_FINGERPRINT_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def _decision_context_prior_bytes(root: Path, relative: str, active: bytes) -> bytes:
    """Peel the 2026-11-08 additive brief fields (matched-cohort change, market-gated set).

    Only ``daily_integrated_decision_brief.py`` changed; the new fields are emitted only when they carry
    evidence, so a session without them keeps its exact prior brief bytes. A missing manifest keeps older
    checkouts valid.
    """
    if relative != DECISION_CONTEXT_SOURCE:
        return active
    manifest = root / DECISION_CONTEXT_MANIFEST
    if not manifest.is_file():
        return active
    spec = json.loads(manifest.read_bytes())
    sources = spec.get("sources")
    if (set(spec) != {"contract_version", "base_commit", "scope", "release_authority", "sources",
                      "previous_e4_v2_digest", "active_e4_v2_digest"}
            or spec.get("contract_version") != "decision_context_premarket_source_transition/v1"
            or spec.get("base_commit") != DECISION_CONTEXT_BASE
            or spec.get("scope") != DECISION_CONTEXT_SCOPE
            or spec.get("release_authority") != "NOT_GRANTED"
            or not isinstance(sources, dict) or tuple(sources) != (DECISION_CONTEXT_SOURCE,)):
        raise ValueError("DECISION_CONTEXT_SOURCE_TRANSITION_SCOPE_INVALID")
    row = sources[relative]
    if (not isinstance(row, dict) or set(row) != {"archive", "prior_sha256_lf", "active_sha256_lf"}
            or row.get("archive") != DECISION_CONTEXT_ARCHIVE):
        raise ValueError("DECISION_CONTEXT_SOURCE_TRANSITION_SCOPE_INVALID")
    prior = (root / DECISION_CONTEXT_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    if (row["prior_sha256_lf"] != DECISION_CONTEXT_PRIOR_SHA256_LF
            or hashlib.sha256(prior).hexdigest() != row["prior_sha256_lf"]
            or hashlib.sha256(active).hexdigest() != row["active_sha256_lf"]
            or row["prior_sha256_lf"] == row["active_sha256_lf"]):
        raise ValueError("DECISION_CONTEXT_SOURCE_TRANSITION_BINDING_INVALID")
    return prior


def historical_bytes(root: Path, relative: str) -> bytes:
    """Verify both sides of an approved boundary before supplying legacy bytes."""
    content = (root / relative).read_bytes().replace(b"\r\n", b"\n")
    if relative == TACTICAL_SHADOW_PIPELINE:
        content = _tactical_shadow_prior_bytes(root, relative, content)
    content = _decision_context_prior_bytes(root, relative, content)
    content = _legacy_summary_fingerprint_prior_bytes(root, relative, content)
    content = _ocr_recognition_prior_bytes(root, relative, content)
    if relative == ARCHITECTURE_BASELINE_SOURCE:
        content = _architecture_baseline_prior_bytes(root, content)
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
    live_file = (root / THESIS_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    active_file = _thesis_root_prior_bytes(root, live_file)
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
    brief_inputs = _brief_input_spec(root)
    if brief_inputs is not None:
        if brief_inputs["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = brief_inputs["active_e4_v2_digest"]
    evaluated_input = _evaluated_input_spec(root)
    if evaluated_input is not None:
        if evaluated_input["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = evaluated_input["active_e4_v2_digest"]
    post_producer = _post_producer_spec(root)
    if post_producer is not None:
        if post_producer["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = post_producer["active_e4_v2_digest"]
    streaming_bytes = (root / TPLUS_RESUME_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    if (root / TPLUS_M1B_MANIFEST).is_file():
        streaming_bytes = _tplus_m1b_prior_bytes(root, TPLUS_RESUME_SOURCE, streaming_bytes)
    if (root / TPLUS_INCREMENTAL_MANIFEST).is_file():
        streaming_bytes = _tplus_incremental_cost_prior_bytes(root, TPLUS_RESUME_SOURCE, streaming_bytes)
    if (root / TPLUS_REAL_CORPUS_MANIFEST).is_file():
        real_corpus = json.loads((root / TPLUS_REAL_CORPUS_MANIFEST).read_bytes())
        _tplus_real_corpus_prior_bytes(root, TPLUS_RESUME_SOURCE, streaming_bytes)
        if real_corpus["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = real_corpus["active_e4_v2_digest"]
    if (root / TPLUS_INCREMENTAL_MANIFEST).is_file():
        incremental = json.loads((root / TPLUS_INCREMENTAL_MANIFEST).read_bytes())
        if incremental["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = incremental["active_e4_v2_digest"]
    if (root / TPLUS_M1B_MANIFEST).is_file():
        m1b = json.loads((root / TPLUS_M1B_MANIFEST).read_bytes())
        if m1b["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = m1b["active_e4_v2_digest"]
    thesis_root = _thesis_root_spec(root)
    if thesis_root is not None:
        if thesis_root["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = thesis_root["active_e4_v2_digest"]
    summary_manifest = root / LEGACY_SUMMARY_MANIFEST
    if summary_manifest.is_file():
        live_feedback = (root / LEGACY_SUMMARY_SOURCE).read_bytes().replace(b"\r\n", b"\n")
        _legacy_summary_fingerprint_prior_bytes(root, LEGACY_SUMMARY_SOURCE, live_feedback)
        summary_fp = json.loads(summary_manifest.read_bytes())
        if summary_fp["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = summary_fp["active_e4_v2_digest"]
    context_manifest = root / DECISION_CONTEXT_MANIFEST
    if context_manifest.is_file():
        live_brief = (root / DECISION_CONTEXT_SOURCE).read_bytes().replace(b"\r\n", b"\n")
        _decision_context_prior_bytes(root, DECISION_CONTEXT_SOURCE, live_brief)
        context = json.loads(context_manifest.read_bytes())
        if context["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = context["active_e4_v2_digest"]
    feedback_io_manifest = root / TPLUS_FEEDBACK_IO_MANIFEST
    if feedback_io_manifest.is_file():
        feedback_io = json.loads(feedback_io_manifest.read_bytes())
        if feedback_io["previous_e4_v2_digest"] != expected_execution:
            raise ValueError("THESIS_SOURCE_ACTIVE_DIGEST_MISMATCH")
        expected_execution = feedback_io["active_e4_v2_digest"]
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
