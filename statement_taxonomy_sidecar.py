"""Historical statement-taxonomy sidecar API retained for the frozen operator entrypoint.

Implementation belongs to stocklookup_core.financial.statement_taxonomy_sidecar. The root name remains because the frozen or
historically executed importers recorded in tests/fixtures/repository_layout_migration_20261025_relocations.json
import it; other existing root and tools callers may keep using it. The exported objects are the
package objects, including pickle and exception identity.
"""
from stocklookup_core.financial.statement_taxonomy_sidecar import (
    Any,
    CLASSIFIER_VERSION,
    CORPORATE_TAXONOMY,
    FINANCIAL_TAXONOMIES,
    Iterable,
    Mapping,
    NON_EVIDENTIAL_TAXONOMIES,
    Path,
    SIDECAR_FILENAME,
    SIDECAR_SCHEMA_VERSION,
    _AUTHORITY_GENERATED,
    _AUTHORITY_MANUAL,
    _AUTHORITY_UNKNOWN,
    _INPUT_GLOB,
    _canonical_json,
    _classify_payload,
    _fingerprint,
    _record_for_ticker,
    _record_identity,
    _sha256_file,
    build_sidecar,
    classify_statement_taxonomy,
    hashlib,
    iter_records,
    json,
    load_sidecar,
    os,
    resolve_entity_authority,
    resolve_taxonomy,
    sidecar_path,
    sidecar_provenance,
    taxonomy_index,
)
