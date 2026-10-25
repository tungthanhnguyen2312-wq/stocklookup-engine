"""Historical owner-focus presentation-scope API retained for the frozen decision brief and historical importers.

Implementation belongs to stocklookup_core.research.owner_research_focus. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.research.owner_research_focus import (
    Any,
    CONFIG_PATH,
    CONTRACT_VERSION,
    Mapping,
    OwnerResearchFocusError,
    Path,
    _tickers,
    broader_watchlist,
    json,
    load_owner_research_focus,
    owner_focus_tickers,
)
