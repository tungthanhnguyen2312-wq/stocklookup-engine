"""Historical qualified research snapshot v2 API retained for the frozen release orchestrator.

Implementation belongs to stocklookup_core.research.qualified_research_snapshot_v2. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.research.qualified_research_snapshot_v2 import (
    Any,
    COMPATIBLE_SCHEMA_VERSIONS,
    Mapping,
    PRODUCTION_UNIVERSE,
    SCHEMA_VERSION,
    _CAPABILITY_PATHS,
    _analysis_states,
    _capability_state,
    _hash,
    _m,
    _reason_codes,
    _stable,
    build,
    from_served_bundle,
    json,
    sha256,
)
