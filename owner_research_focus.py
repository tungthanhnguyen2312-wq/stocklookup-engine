"""Historical owner-focus presentation-scope API retained for the frozen decision brief and historical importers.

Implementation belongs to stocklookup_core.research.owner_research_focus. This root name is kept only for
the importers listed in the layout migration fixture; the exported objects are the
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
