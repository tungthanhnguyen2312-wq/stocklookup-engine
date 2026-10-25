"""Historical sector-relative research context API retained for historically executed sources.

Implementation belongs to stocklookup_core.financial.sector_relative_research_context. This root name is kept only for
the importers listed in the layout migration fixture; the exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.financial.sector_relative_research_context import (
    Any,
    Counter,
    MIN_COHORT_MEMBERS,
    Mapping,
    NUMERIC_METRICS,
    Path,
    _bucket,
    _canon,
    _hash,
    _numeric_context,
    _trend_context,
    _unavailable,
    build,
    defaultdict,
    hashlib,
    json,
    load_provider_descriptive_industry_classes,
    load_qualified_entity_classes,
    markdown_overlay,
    median,
    review_pack_overlay,
)
