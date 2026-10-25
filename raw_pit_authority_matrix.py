"""Historical raw PIT authority matrix API retained for the frozen Integrated Decision importer.

Implementation belongs to stocklookup_core.evidence.raw_pit_authority_matrix. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.evidence.raw_pit_authority_matrix import (
    Any,
    BEFORE,
    CONTRACT_VERSION,
    DIMENSIONS,
    EXECUTION_REQUIRED_FEATURES,
    FEATURES,
    HISTORICAL_USES,
    LIVE_USES,
    Mapping,
    PIT_REQUIRED_FEATURES,
    RESEARCH_USES,
    USE_CASES,
    _blocker,
    _instant,
    attach_current_readiness,
    authority_row,
    current_readiness_context,
    datetime,
    evaluate,
    math,
    promotion_dossier,
    stable_id,
    use_case_readiness,
)
