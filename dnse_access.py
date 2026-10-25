"""Historical DNSE credential and request-signing API retained for frozen Daily importers.

Implementation belongs to stocklookup_core.acquisition.dnse_access. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.acquisition.dnse_access import (
    Any,
    BASE_URL,
    CREDENTIAL_ENV_PAIRS,
    DEFAULT_API_VERSION,
    DEFAULT_API_VERSION_ENV,
    Mapping,
    Sequence,
    _REDACTED,
    _SENSITIVE_KEY_SUBSTRINGS,
    _find_credential_pair,
    _signature_string,
    api_version,
    auth_headers,
    base64,
    build_signature,
    credential_status,
    credentials_for_request,
    datetime,
    hashlib,
    hmac,
    os,
    parse_qsl,
    redact_headers,
    redact_value,
    safe_error_code,
    sanitize_url,
    scrub_text,
    timezone,
    urlencode,
    urlsplit,
    urlunsplit,
    uuid,
)
