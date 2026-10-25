"""Historical price-structure breakout context API retained for the frozen technical owner and historically executed sources.

Implementation belongs to stocklookup_core.tactical.price_structure_breakout_context. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.tactical.price_structure_breakout_context import (
    Any,
    Counter,
    LOOKBACK,
    Mapping,
    NEAR,
    _canon,
    _hash,
    build,
    daily_overlay,
    hashlib,
    json,
    review_overlay,
    scenario_overlay,
)
