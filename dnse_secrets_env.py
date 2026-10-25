"""Historical DNSE secrets-file loader API retained for frozen Daily importers.

Implementation belongs to stocklookup_core.acquisition.dnse_secrets_env. This root name is kept only for
the importers listed in the layout migration fixture; the exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.acquisition.dnse_secrets_env import (
    Any,
    CREDENTIAL_ENV_PAIRS,
    DEFAULT_SECRETS_PATH,
    Path,
    SECRETS_PATH_ENV,
    _KNOWN_KEYS,
    _parse_env_lines,
    credential_status,
    ensure_credentials_loaded,
    load_secrets_env,
    os,
    secrets_path,
)
