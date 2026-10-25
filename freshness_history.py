"""Historical freshness-envelope API retained for frozen Daily and historical importers.

Implementation belongs to stocklookup_core.evidence.freshness_history. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.evidence.freshness_history import (
    Any,
    DomainRule,
    READINESS_STATES,
    RULES,
    STATUSES,
    _readiness,
    dataclass,
    date,
    datetime,
    evaluate_analysis_readiness,
    freshness_envelope,
    latest_completed_market_day,
    parse_timestamp,
    timedelta,
    timezone,
)
