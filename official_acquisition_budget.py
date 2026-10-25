"""Historical official acquisition budget API retained for historically executed sources.

Implementation belongs to stocklookup_core.acquisition.official_acquisition_budget. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.acquisition.official_acquisition_budget import (
    AcquisitionBudget,
    AcquisitionBudgetExceeded,
    AcquisitionLimits,
    Callable,
    HTTPRedirectHandler,
    _NoAutomaticRedirect,
    asdict,
    build_opener,
    dataclass,
    hashlib,
    time,
)
