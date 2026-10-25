"""Historical official acquisition budget API retained for historically executed sources.

Implementation belongs to stocklookup_core.acquisition.official_acquisition_budget. This root name is kept only for
the importers listed in the layout migration fixture; the exported objects are the
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
