"""Scoped OCR layout proof for image-only official statements (Owner-approved corrective 2026-11-07).

Two admission checks assume a native text layer: document currency/unit declared on front pages 1-8,
and a cited ``label + value`` span that is contiguous in page text. An image-only VAS statement has no
text layer, declares ``Đơn vị: VND`` only on each statement page, and prints the line-code and note
columns between label and amount. For a document whose layout is registered here (no global
whitelist) the two checks are replaced by proofs that are at least as strict:

* a retained, content-addressed OCR proof (positioned tokens + rendered-image hashes + engine/config)
  bound to the document SHA, so every literal is replayable without re-running OCR;
* ``verify_statement_unit``: the table's own unit declaration (exact token ids, page, SHA, located above
  the table header), parsed to currency AND scale; any other parsed declaration on the statement pages
  or front pages that differs, or an undeclared page, blocks;
* ``verify_row``: label tokens, line-code token, value token and current-period header proven on one
  physical table row by coordinates: value inside the "current period" band under its header, line code
  in the line-code band on the value's row, no second amount in the current band on that row, a
  distinct comparative amount in the comparative band, exact raw text and sign.

Ambiguous OCR stays blocked. HOL-08 adds only same-render baseline U+00B2 geometry proof;
raw tokens remain unchanged and no other numeric character is interpreted differently.
"""
from __future__ import annotations

import hashlib
import json
import re
import math
import os
import sys
import uuid
from statistics import median
from typing import Any, Iterable, Mapping

CONTRACT_VERSION = "official_ocr_layout_proof/v1"
PROOF_DIR = "ocr-layout-proofs"

# Immutable snapshots are parsed from the same bounded bytes used for their digest.
from copy import deepcopy
from functools import lru_cache
from pathlib import Path, PurePosixPath
from datetime import datetime

REGISTRY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_LIMIT = 1024 * 1024
LAYOUT_SNAPSHOT = "config/official_financial_layouts/r0001.json"
ISSUER_SNAPSHOT = "config/official_financial_issuers/r0001.json"
CAPACITY_RECEIPT = "config/owner_daily_capacity_qualification.json"
REGISTRY_BINDINGS_ENV = "STOCK_LOOKUP_FINANCIAL_REGISTRY_INPUTS"
REGISTRY_RUN_ENV = "STOCK_LOOKUP_FINANCIAL_REGISTRY_RUN_ID"
_BOUND_REGISTRIES = None


def registry_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or ":" in relative or PurePosixPath(relative).is_absolute()
            or any(p in {"", ".", ".."} for p in relative.split("/"))):
        raise ValueError("REGISTRY_PATH_ESCAPE")
    root = root.resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError("REGISTRY_PATH_ESCAPE")
    # Refuse redirection even if a link happens to point back inside the checkout.
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
           for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError("REGISTRY_PATH_ESCAPE")
    return path


def registry_bytes(root: Path, relative: str) -> bytes:
    path = registry_path(root, relative)
    with path.open("rb") as stream:
        raw = stream.read(REGISTRY_LIMIT + 1)
    if len(raw) > REGISTRY_LIMIT:
        raise ValueError("REGISTRY_TOO_LARGE")
    return raw


def _registry_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("REGISTRY_DUPLICATE_KEY:" + key)
        result[key] = value
    return result


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("REGISTRY_FIELDS_INVALID")


def _string(value):
    if type(value) is not str or not value.strip():
        raise ValueError("REGISTRY_STRING_INVALID")


def _integer(value):
    if type(value) is not int or value < 1:
        raise ValueError("REGISTRY_INTEGER_INVALID")


def _digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("REGISTRY_DIGEST_INVALID")


def _instant(value, *, unknown=False):
    if value is None and unknown:
        return
    _string(value)
    if datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError("REGISTRY_TIME_INVALID")


def _review(value):
    _fields(value, ("reference", "recorded_at"))
    _string(value["reference"])
    _instant(value["recorded_at"], unknown=True)


def _strings(value):
    if type(value) is not list:
        raise ValueError("REGISTRY_LIST_INVALID")
    for item in value:
        _string(item)


def _entry(value, payload_fields, *, offline=False):
    _fields(value, ("revision", "supersedes", "review", "inputs", "timestamps", *payload_fields))
    _integer(value["revision"])
    if value["supersedes"] is not None:
        _digest(value["supersedes"])
    _review(value["review"])
    inputs = value["inputs"]
    _fields(inputs, ("provenance_refs", "reader_sha256", "render_meta_sha256"), ("tuple_readings",) if offline else ())
    _strings(inputs["provenance_refs"])
    if not inputs["provenance_refs"]:
        raise ValueError("REGISTRY_PROVENANCE_MISSING")
    if inputs["reader_sha256"] is not None:
        if type(inputs["reader_sha256"]) is not list or len(inputs["reader_sha256"]) != 2:
            raise ValueError("REGISTRY_READER_HASHES_INVALID")
        for item in inputs["reader_sha256"]:
            if item is not None:
                _digest(item)
    if inputs["render_meta_sha256"] is not None:
        _digest(inputs["render_meta_sha256"])
    if offline and type(inputs.get("tuple_readings")) is not bool:
        raise ValueError("REGISTRY_TUPLE_SHAPE_INVALID")
    _fields(value["timestamps"], ("evidence_observed_at", "registered_at", "knowledge_available_at"))
    for item in value["timestamps"].values():
        _instant(item, unknown=True)


@lru_cache(maxsize=16)
def _parsed_registry(raw: bytes, digest: str, role: str):
    if len(raw) > REGISTRY_LIMIT or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("REGISTRY_HASH_MISMATCH")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_registry_pairs,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError("REGISTRY_NUMBER_INVALID")))
    common = ("schema_version", "revision", "supersedes_sha256_lf", "review")
    _fields(value, (*common, *(('issuer_legal_names', 'entity_families') if role == 'issuers' else ('entries',))))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or role not in {"layouts", "issuers", "admissions"}:
        raise ValueError("REGISTRY_SCHEMA_UNKNOWN")
    _integer(value["revision"])
    if value["supersedes_sha256_lf"] is not None:
        _digest(value["supersedes_sha256_lf"])
    _review(value["review"])
    groups = ("issuer_legal_names", "entity_families") if role == "issuers" else ("entries",)
    for group in groups:
        if type(value[group]) is not dict or not value[group]:
            raise ValueError("REGISTRY_ENTRIES_INVALID")
        for key, entry in value[group].items():
            _string(key)
            if role == "layouts":
                _digest(key)
                _entry(entry, ("payload",))
                p = entry["payload"]
                _fields(p, ("ticker", "reporting_period", "statement_scope", "layout", "statement_pages", "current_headers", "comparative_headers", "metric_line_codes", "approval"), ("text_layer_verification",))
                for field in ("ticker", "reporting_period", "statement_scope", "layout", "approval"):
                    _string(p[field])
                if p["statement_scope"] != "consolidated" or type(p["statement_pages"]) is not list or not p["statement_pages"]:
                    raise ValueError("REGISTRY_LAYOUT_INVALID")
                for page in p["statement_pages"]:
                    _integer(page)
                if len(set(p["statement_pages"])) != len(p["statement_pages"]):
                    raise ValueError("REGISTRY_CONFLICTING_PAGES")
                for field in ("current_headers", "comparative_headers"):
                    _strings(p[field])
                _fields(p["metric_line_codes"], (), ("revenue", "net_income", "attributable_net_income", "total_assets", "shareholders_equity", "operating_cash_flow"))
                for code in p["metric_line_codes"].values():
                    if type(code) is not str or not code.isdigit():
                        raise ValueError("REGISTRY_LINE_CODE_INVALID")
                if "text_layer_verification" in p:
                    q = p["text_layer_verification"]
                    _fields(q, ("state",), ("tool", "pages_checked", "non_empty_pages", "verified_at", "reported_observation"))
                    for field, item in q.items():
                        if field in {"pages_checked", "non_empty_pages"}:
                            if type(item) is not int or item < 0:
                                raise ValueError("REGISTRY_PAGE_COUNT_INVALID")
                        else:
                            _string(item)
            elif role == "issuers":
                if not re.fullmatch(r"[A-Z0-9]{3,10}", key):
                    raise ValueError("REGISTRY_TICKER_INVALID")
                _entry(entry, ("exact", "folded") if group == "issuer_legal_names" else ("family",))
                if group == "entity_families":
                    if type(entry["family"]) is not str or entry["family"] not in {"corporate", "bank", "securities", "finance_company"}:
                        raise ValueError("REGISTRY_FAMILY_UNKNOWN")
                    continue
                _strings(entry["folded"])
                if len(entry["folded"]) > 1 or type(entry["exact"]) is not list:
                    raise ValueError("REGISTRY_NAMES_CONFLICT")
                for name in entry["exact"]:
                    _fields(name, ("literal", "provenance"))
                    _string(name["literal"])
                    q = name["provenance"]
                    _fields(q, ("document_sha256", "source_page", "source_host", "description"), ("image_sha256", "reader_files"))
                    _digest(q["document_sha256"]); _integer(q["source_page"])
                    _string(q["source_host"]); _string(q["description"])
                    if "image_sha256" in q:
                        _digest(q["image_sha256"])
                    if "reader_files" in q:
                        if type(q["reader_files"]) is not list:
                            raise ValueError("REGISTRY_READERS_INVALID")
                        for reader in q["reader_files"]:
                            _fields(reader, ("relative_path", "sha256"))
                            registry_path(REGISTRY_ROOT, reader["relative_path"])
                            _digest(reader["sha256"])
            else:
                _entry(entry, ("payload",), offline=True)
                p = entry["payload"]
                fields = ("ticker", "reporting_period", "document_sha256", "document_id", "original_subdir", "new_subdir", "page_key", "source_page", "printed_page", "image_sha256", "column_id", "readings", "image", "render_meta", "comparison_started_at")
                _fields(p, fields)
                for field in fields:
                    if field not in {"readings", "source_page"}:
                        _string(p[field])
                for field in ("document_sha256", "document_id", "image_sha256"):
                    _digest(p[field])
                _integer(p["source_page"]); _instant(p["comparison_started_at"])
                for field in ("original_subdir", "new_subdir", "image", "render_meta", "page_key"):
                    registry_path(REGISTRY_ROOT, p[field])
                if type(p["readings"]) is not list or len(p["readings"]) != 2:
                    raise ValueError("REGISTRY_READINGS_INVALID")
                for reading in p["readings"]:
                    if type(reading) is not list or len(reading) != 3:
                        raise ValueError("REGISTRY_READING_INVALID")
                    _string(reading[0]); registry_path(REGISTRY_ROOT, reading[1]); _instant(reading[2])
                if key != p["ticker"] + "-" + p["reporting_period"] + "-P" + str(p["source_page"]):
                    raise ValueError("REGISTRY_SPEC_CONFLICT")
    if role == "issuers":
        owners = {}
        for ticker, entry in value["issuer_legal_names"].items():
            for literal in [n["literal"] for n in entry["exact"]] + entry["folded"]:
                if literal in owners and owners[literal] != ticker:
                    raise ValueError("REGISTRY_CONFLICTING_ISSUER_NAMES")
                owners[literal] = ticker
    return value


def load_registry_snapshot(role: str, *, root: Path | None = None, relative: str | None = None,
                           expected_sha256_lf: str | None = None):
    if _BOUND_REGISTRIES is not None:
        bound_root, bindings, snapshots = _BOUND_REGISTRIES
        if (role not in snapshots or (root is not None and root.resolve() != bound_root)
                or relative not in (None, bindings[role]["path"])
                or expected_sha256_lf not in (None, bindings[role]["sha256_lf"])):
            raise ValueError("REGISTRY_BOUND_INPUT_CONFLICT")
        # Never reopen a verified file. Consumers receive detached cached values.
        return deepcopy(snapshots[role])
    root = root or REGISTRY_ROOT
    relative = relative or {"layouts": LAYOUT_SNAPSHOT, "issuers": ISSUER_SNAPSHOT}[role]
    raw = registry_bytes(root, relative).replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256_lf is not None and digest != expected_sha256_lf:
        raise ValueError("REGISTRY_HASH_MISMATCH")
    return deepcopy(_parsed_registry(raw, digest, role))


def _registry_json(raw: bytes):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_registry_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("REGISTRY_NUMBER_INVALID")))


def validate_financial_registry_bindings(bindings):
    _fields(bindings, ("layouts", "issuers", "capacity_receipt_sha256_lf"))
    _digest(bindings["capacity_receipt_sha256_lf"])
    for role in ("layouts", "issuers"):
        row = bindings[role]
        _fields(row, ("path", "revision", "sha256_lf"))
        _integer(row["revision"]); _digest(row["sha256_lf"])
        _registry_revision_path(role, row["path"], row["revision"])


def _registry_revision_path(role, path, revision):
    _string(path)
    directory = {"layouts": "official_financial_layouts", "issuers": "official_financial_issuers"}[role]
    if path != f"config/{directory}/r{revision:04d}.json":
        raise ValueError("REGISTRY_IMMUTABLE_PATH_INVALID")


def verify_financial_registry_inputs(root: Path, *, expected=None):
    """Read only selected shared snapshots; the capacity receipt is the sole digest anchor.

    The receipt's unrelated capacity history/limits retain their existing owner and schema.
    This gate strictly validates its selectors and the complete selected snapshot schemas.
    No feature flag, host-memory observation or receipt digest sidecar participates.
    """
    raw = registry_bytes(root, CAPACITY_RECEIPT).replace(b"\r\n", b"\n")
    receipt = _registry_json(raw)
    if (type(receipt) is not dict or receipt.get("schema") != "owner_daily_capacity_qualification/v1"
            or receipt.get("source_byte_normalization") != "CRLF_TO_LF"):
        raise ValueError("REGISTRY_CAPACITY_SCHEMA_INVALID")
    selectors = receipt.get("financial_registry_inputs")
    _fields(selectors, ("layouts", "issuers"))
    anchors = receipt.get("source_sha256")
    if type(anchors) is not dict:
        raise ValueError("REGISTRY_CAPACITY_ANCHOR_MISSING")
    bindings = {"capacity_receipt_sha256_lf": hashlib.sha256(raw).hexdigest()}
    snapshots = {}
    for role in ("layouts", "issuers"):
        selector = selectors[role]
        _fields(selector, ("role", "path", "revision", "approval_reference", "approved_at"))
        if type(selector["role"]) is not str or selector["role"] != role:
            raise ValueError("REGISTRY_SELECTOR_ROLE_INVALID")
        _integer(selector["revision"])
        _string(selector["approval_reference"]); _instant(selector["approved_at"])
        if selector["approval_reference"].strip().upper() in {"UNKNOWN", "PENDING", "UNAPPROVED", "NONE", "NULL"}:
            raise ValueError("REGISTRY_SELECTOR_UNAPPROVED")
        _registry_revision_path(role, selector["path"], selector["revision"])
        digest = anchors.get(selector["path"])
        _digest(digest)
        snapshot_raw = registry_bytes(root, selector["path"]).replace(b"\r\n", b"\n")
        # Hash and parse exactly these bytes, bypassing any prior unbound/default cache.
        snapshot = _parsed_registry(snapshot_raw, digest, role)
        if snapshot["revision"] != selector["revision"]:
            raise ValueError("REGISTRY_SELECTOR_REVISION_CONFLICT")
        snapshots[role] = deepcopy(snapshot)
        bindings[role] = {"path": selector["path"], "revision": selector["revision"], "sha256_lf": digest}
    if expected is not None:
        validate_financial_registry_bindings(expected)
        if bindings != expected:
            raise ValueError("REGISTRY_CHILD_BINDING_MISMATCH")
    return bindings, snapshots


def bind_financial_registry_inputs(root: Path, *, expected=None):
    global _BOUND_REGISTRIES
    bindings, snapshots = verify_financial_registry_inputs(root, expected=expected)
    if _BOUND_REGISTRIES is not None and (root.resolve(), bindings) != _BOUND_REGISTRIES[:2]:
        raise ValueError("REGISTRY_BOUND_INPUT_CONFLICT")
    _BOUND_REGISTRIES = (root.resolve(), deepcopy(bindings), deepcopy(snapshots))
    # Preserve references held by an already imported consumer, including ENTITY_FAMILY.
    if "LAYOUT_PROOFS" in globals():
        LAYOUT_PROOFS.clear(); LAYOUT_PROOFS.update(_layout_payloads())
        exact, folded, families = issuer_registry_values()
        for target, values in ((EXACT_REGISTERED_ISSUER_NAMES, exact),
                               (REGISTERED_ISSUER_FOLD, folded), (_ENTITY_FAMILIES, families)):
            target.clear(); target.update(values)
        currency = sys.modules.get("financial_evidence_currency_contract")
        if currency is not None and hasattr(currency, "ENTITY_FAMILY"):
            currency.ENTITY_FAMILY.clear(); currency.ENTITY_FAMILY.update(families)
    return deepcopy(bindings)


def _registry_child_directory(root: Path, run_id: str) -> Path:
    if type(run_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("REGISTRY_CHILD_RUN_ID_INVALID")
    return registry_path(root, "operations-review/owner-daily-journal-v1/financial-registry-children/" + run_id)


def registry_child_environment(root: Path, bindings: Mapping[str, Any], *, run_id: str | None = None):
    validate_financial_registry_bindings(bindings)
    run_id = uuid.uuid4().hex if run_id is None else run_id
    directory = _registry_child_directory(root, run_id)
    # A fresh token must never adopt another invocation's child attestations.
    directory.mkdir(parents=True, exist_ok=False)
    return {REGISTRY_BINDINGS_ENV: json.dumps(bindings, sort_keys=True), REGISTRY_RUN_ENV: run_id,
            "STOCKLOOKUP_FINANCIAL_REGISTRY_OWNER_PID": str(os.getpid())}


def _registry_ancestor_pids() -> list[int]:
    """Capture OS parentage while the importing child and its ancestors are alive."""
    owner = os.environ.get("STOCKLOOKUP_FINANCIAL_REGISTRY_OWNER_PID", "")
    if not re.fullmatch(r"[1-9][0-9]*", owner):
        raise ValueError("REGISTRY_CHILD_OWNER_PID_INVALID")
    owner_pid = int(owner)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class ProcessEntry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                        ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                        ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                        ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
                        ("flags", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value:
            raise ValueError("REGISTRY_CHILD_LINEAGE_UNAVAILABLE")
        parents = {}
        try:
            row = ProcessEntry(); row.size = ctypes.sizeof(row)
            found = kernel.Process32FirstW(handle, ctypes.byref(row))
            while found:
                parents[row.pid] = row.parent
                found = kernel.Process32NextW(handle, ctypes.byref(row))
        finally:
            kernel.CloseHandle(handle)
        parent_of = parents.get
    else:
        def parent_of(pid):
            # Linux procfs: comm may contain spaces or parentheses.
            return int((Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[1])
    ancestors = []
    pid = os.getpid()
    for _ in range(256):
        parent = parent_of(pid)
        if not parent or parent == os.getpid() or parent in ancestors:
            break
        ancestors.append(parent)
        if parent == owner_pid:
            return ancestors
        pid = parent
    raise ValueError("REGISTRY_CHILD_PID_NOT_DESCENDANT")


def _attest_registry_child(root: Path, run_id: str, bindings: Mapping[str, Any], *,
                           ancestor_pids=None) -> None:
    """Write the same run-bound record without importing the parent journal."""
    validate_financial_registry_bindings(bindings)
    directory = _registry_child_directory(root, run_id)
    if not directory.is_dir():
        raise ValueError("REGISTRY_CHILD_RUN_MISSING")
    path = directory / (str(os.getpid()) + ".json")
    if path.exists() or path.is_symlink():
        raise ValueError("REGISTRY_CHILD_ATTESTATION_EXISTS")
    value = {"pid": os.getpid(),
             "ancestor_pids": (_registry_ancestor_pids if ancestor_pids is None else ancestor_pids)(),
             "financial_registry_inputs": deepcopy(bindings)}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def verify_registry_children(root: Path, run_id: str, bindings: Mapping[str, Any], *, owner_pid=None):
    validate_financial_registry_bindings(bindings)
    directory = _registry_child_directory(root, run_id)
    owner_pid = os.getpid() if owner_pid is None else owner_pid
    if type(owner_pid) is not int or owner_pid <= 0:
        raise ValueError("REGISTRY_CHILD_OWNER_PID_INVALID")
    seen = set()
    for index, path in enumerate(directory.iterdir()):
        if index >= 256 or not re.fullmatch(r"[1-9][0-9]*\.json", path.name):
            raise ValueError("REGISTRY_CHILD_ATTESTATION_INVALID")
        relative = path.relative_to(root.resolve()).as_posix()
        try:
            row = _registry_json(registry_bytes(root, relative))
            if (type(row) is not dict or set(row) != {"pid", "ancestor_pids", "financial_registry_inputs"}
                    or type(row["pid"]) is not int or path.name != str(row["pid"]) + ".json"):
                raise ValueError("REGISTRY_CHILD_ATTESTATION_INVALID")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("REGISTRY_CHILD_ATTESTATION_INVALID") from exc
        ancestors = row["ancestor_pids"]
        if (type(ancestors) is not list or not 1 <= len(ancestors) <= 256
                or any(type(pid) is not int or pid <= 0 for pid in ancestors)
                or len(set(ancestors)) != len(ancestors) or row["pid"] in ancestors
                or ancestors[-1] != owner_pid):
            raise ValueError("REGISTRY_CHILD_PID_NOT_DESCENDANT")
        if row["pid"] in seen:
            raise ValueError("REGISTRY_CHILD_ATTESTATION_DUPLICATE")
        try:
            validate_financial_registry_bindings(row["financial_registry_inputs"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("REGISTRY_CHILD_ATTESTATION_INVALID") from exc
        if row["financial_registry_inputs"] != bindings:
            raise ValueError("REGISTRY_CHILD_BINDING_MISMATCH")
        seen.add(row["pid"])
    return sorted(seen)


def registry_child_attestations(root: Path, run_id: str, bindings: Mapping[str, Any]):
    pids = verify_registry_children(root, run_id, bindings)
    return {"pids": pids, "status": "BOUND" if pids else "REGISTRY_NOT_LOADED_BY_CHILD"}


def _bind_registry_child():
    encoded = os.environ.get(REGISTRY_BINDINGS_ENV)
    run_id = os.environ.get(REGISTRY_RUN_ENV)
    if encoded is None and run_id is None:
        return
    if encoded is None or run_id is None or len(encoded) > 8192:
        raise ValueError("REGISTRY_CHILD_BINDING_MISSING")
    expected = _registry_json(encoded.encode("utf-8"))
    bindings = bind_financial_registry_inputs(REGISTRY_ROOT, expected=expected)
    _attest_registry_child(REGISTRY_ROOT, run_id, bindings)


def _layout_payloads():
    entries = load_registry_snapshot("layouts")["entries"]
    result = {key: entry["payload"] for key, entry in entries.items()}
    for payload in result.values():
        for field in ("statement_pages", "current_headers", "comparative_headers"):
            payload[field] = tuple(payload[field])
    return result


def issuer_registry_values():
    snapshot = load_registry_snapshot("issuers")
    names = snapshot["issuer_legal_names"]
    return ({key: tuple(entry["exact"]) for key, entry in names.items() if entry["exact"]},
            {key: entry["folded"][0] for key, entry in names.items() if entry["folded"]},
            {key: entry["family"] for key, entry in snapshot["entity_families"].items()})


_bind_registry_child()
LAYOUT_PROOFS = _layout_payloads()


_AMOUNT = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})+\)?$")

BASELINE_TWO_CONTRACT = "ocr_baseline_u00b2_geometry/v1"
BASELINE_TWO_TOLERANCE = 0.10


def baseline_two_value(token: Mapping[str, Any], rendered_image_sha256: str) -> tuple[str, dict | None]:
    """Only U+00B2, proven at baseline against other ASCII digits of this exact token.

    Coordinates are top-origin pixels of the same retained render. Raw text is never changed.
    Missing, malformed, raised, small or mixed-damage character evidence fails closed.
    """
    raw = str(token.get("text") or "")
    if "²" not in raw:
        return raw, None
    evidence = token.get("glyph_evidence") or {}
    if not isinstance(evidence, Mapping):
        return raw, None
    boxes = evidence.get("boxes") or []
    if not isinstance(boxes, list) or not all(isinstance(b, Mapping) for b in boxes):
        return raw, None
    if (not re.fullmatch(r"\(?-?[0-9²]{1,3}(?:[.,][0-9²]{3})+\)?", raw)
            or not re.fullmatch(r"[0-9a-f]{64}", str(rendered_image_sha256))
            or evidence.get("rendered_image_sha256") != rendered_image_sha256
            or evidence.get("contract_version") != "tesseract_makebox_same_render/v1"
            or not evidence.get("engine_version") or not evidence.get("config")
            or "".join(str(b.get("text", "")) for b in boxes) != raw):
        return raw, None
    try:
        for b in boxes:
            if not all(math.isfinite(float(b[k])) for k in ("x0", "x1", "top", "bottom")):
                return raw, None
            if not (float(token["x0"]) - 1 <= float(b["x0"]) < float(b["x1"]) <= float(token["x1"]) + 1
                    and float(token["top"]) - 1 <= float(b["top"]) < float(b["bottom"]) <= float(token["bottom"]) + 1):
                return raw, None
        digits = [b for b in boxes if b["text"] in "0123456789"]
        if len(digits) < 3 or any(float(a["x1"]) > float(b["x0"]) + 1 for a, b in zip(boxes, boxes[1:])):
            return raw, None
        reference = {"top": median(float(b["top"]) for b in digits),
                     "bottom": median(float(b["bottom"]) for b in digits),
                     "height": median(float(b["bottom"]) - float(b["top"]) for b in digits)}
        tolerance = reference["height"] * BASELINE_TWO_TOLERANCE
        for b in boxes:
            if b["text"] == "²" and any(abs(v - reference[k]) > tolerance for k, v in (
                    ("top", float(b["top"])), ("bottom", float(b["bottom"])),
                    ("height", float(b["bottom"]) - float(b["top"])))):
                return raw, None
    except (KeyError, TypeError, ValueError):
        return raw, None
    normalized = raw.replace("²", "2")
    return normalized, {"contract_version": BASELINE_TWO_CONTRACT, "raw_value": raw,
        "normalized_value_text": normalized, "token_id": token.get("token_id"),
        "median_ascii_digit_box": reference, "tolerance_fraction": BASELINE_TWO_TOLERANCE,
        "tolerance_pixels": tolerance, "glyph_evidence": evidence,
        "rendered_image_sha256": rendered_image_sha256}


def numeric_token_value(raw: str, tokens: Iterable[Mapping[str, Any]], image_sha: str,
                        bbox: Mapping[str, Any]) -> tuple[str, dict | None]:
    try:
        matches = [t for t in tokens if t.get("text") == raw
                   and all(abs(float(t.get(k, -99999)) - float(bbox.get(k, -999))) <= 1
                           for k in ("x0", "x1", "top", "bottom"))]
    except (TypeError, ValueError):
        return raw, None
    return baseline_two_value(matches[0], image_sha) if len(matches) == 1 else (raw, None)


def bound_numeric_value(row: Mapping[str, Any], proof: Mapping[str, Any] | None) -> str:
    raw = str(row.get("raw_value_text") or "")
    ref = row.get("ocr_layout_proof") or {}
    if not proof or not ref.get("proof_sha256") or verify_proof_identity(
            proof, document_sha256=row.get("document_sha256"), proof_sha256=ref["proof_sha256"]):
        return raw
    page_number = row.get("source_page") or (row.get("source_lineage") or {}).get("source_page")
    page = (proof.get("pages") or {}).get(str(page_number)) or {}
    return numeric_token_value(raw, page.get("tokens") or [], page.get("rendered_image_sha256"),
        (row.get("ocr_row_object") or {}).get("current_value_bbox") or {})[0]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def layout_for(document_sha256: str | None) -> dict[str, Any] | None:
    return LAYOUT_PROOFS.get(str(document_sha256 or ""))


EXACT_REGISTERED_ISSUER_NAMES, REGISTERED_ISSUER_FOLD, _ENTITY_FAMILIES = issuer_registry_values()


def exact_registered_issuer_name(ticker: str, literal: str) -> bool:
    return any(item["literal"] == literal for item in EXACT_REGISTERED_ISSUER_NAMES.get(ticker, ()))


def retained_issuer_name_matches(row, proof, text: str) -> bool:
    """Exact registered originals may print their full legal name instead of ticker.

    No fuzzy letters, abbreviation, host or caller-selected issuer establishes this.
    The original bytes, source manifest and issuer host remain separately required.
    """
    from stocklookup_core.evidence.financial_row_identity import _identity_fold
    names = REGISTERED_ISSUER_FOLD
    sha = row.get('document_sha256')
    layout = layout_for(sha) or {}
    ref = row.get('ocr_layout_proof') or {}
    ticker = row.get('ticker')
    exact_name = any(re.search(r'(?<!\w)' + re.escape(item['literal']) + r'(?!\w)', text)
                     for item in EXACT_REGISTERED_ISSUER_NAMES.get(ticker, ()))
    return bool(proof and layout.get('ticker') == ticker
                and not verify_proof_identity(proof, document_sha256=sha, proof_sha256=ref.get('proof_sha256'))
                and (exact_name or (ticker in names and re.search(r'\b'+re.escape(names[ticker])+r'\b', _identity_fold(text)))))


def build_ocr_proof(*, document_sha256: str, materializations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Freeze the OCR tokens actually used for admission. Pages outside the registered layout are kept
    only for front-matter literals (period, scope, assurance, issuer)."""
    layout = layout_for(document_sha256)
    if layout is None:
        raise ValueError("OCR_LAYOUT_NOT_REGISTERED")
    pages: dict[str, Any] = {}
    engine, config = set(), set()
    for materialization in materializations:
        if materialization.get("document_sha256") != document_sha256:
            raise ValueError("OCR_PROOF_DOCUMENT_MISMATCH")
        for page in materialization.get("pages") or []:
            ocr = page.get("ocr_derived_text_evidence") or {}
            image = page.get("source_image_evidence") or {}
            if not ocr.get("tokens") or image.get("document_sha256") != document_sha256:
                raise ValueError("OCR_PROOF_PAGE_INCOMPLETE")
            engine.add(ocr.get("engine_version"))
            config.add(canonical_json(ocr.get("config")))
            pages[str(page["page_number"])] = {
                "rendered_image_sha256": image.get("rendered_image_sha256"),
                "ocr_adapters": page.get("ocr_adapters") or {},
                **({'native_failure_evidence': page['native_failure_evidence']}
                   if page.get('native_failure_evidence') else {}),
                "tokens": [{k: t.get(k) for k in ("token_id", "raw_token_order", "text", "x0", "x1", "top", "bottom",
                                                    "tsv_hierarchy", "source_text", "glyph_evidence")
                            if k != "glyph_evidence" or k in t} for t in ocr["tokens"]],
            }
    if len(engine) != 1 or len(config) != 1:
        raise ValueError("OCR_PROOF_ENGINE_OR_CONFIG_NOT_UNIQUE")
    body = {"contract_version": CONTRACT_VERSION, "document_sha256": document_sha256, "layout": layout["layout"],
            "engine_version": engine.pop(), "ocr_config": json.loads(config.pop()), "pages": pages}
    if any(t.get("glyph_evidence") for p in pages.values() for t in p["tokens"]):
        body["numeric_glyph_policy"] = {"contract_version": BASELINE_TWO_CONTRACT,
            "tolerance_fraction": BASELINE_TWO_TOLERANCE, "minimum_ascii_reference_digits": 3,
            "coordinate_tolerance_pixels": 1, "normalized_characters": {"²": "2"}}
    return {**body, "proof_sha256": hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()}


def verify_proof_identity(proof: Mapping[str, Any], *, document_sha256: str, proof_sha256: str | None) -> list[str]:
    body = {k: v for k, v in proof.items() if k != "proof_sha256"}
    actual = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    reasons = []
    if actual != proof.get("proof_sha256") or (proof_sha256 is not None and actual != proof_sha256):
        reasons.append("OCR_PROOF_HASH_MISMATCH")
    if proof.get("document_sha256") != document_sha256 or layout_for(document_sha256) is None:
        reasons.append("OCR_PROOF_DOCUMENT_OR_LAYOUT_MISMATCH")
    if proof.get("contract_version") != CONTRACT_VERSION:
        reasons.append("OCR_PROOF_CONTRACT_MISMATCH")
    for page in (proof.get("pages") or {}).values():
        for token in page.get("tokens") or []:
            glyph = token.get("glyph_evidence")
            if glyph and (not isinstance(glyph, Mapping)
                          or glyph.get("engine_version") != proof.get("engine_version")
                          or glyph.get("config") != proof.get("ocr_config")):
                reasons.append("OCR_GLYPH_ENGINE_OR_CONFIG_MISMATCH")
    return reasons


def page_text(proof: Mapping[str, Any], page_number: int) -> str:
    page = (proof.get("pages") or {}).get(str(page_number)) or {}
    lines: dict[tuple[int, int, int], list[str]] = {}
    for token in sorted(page.get("tokens") or [], key=lambda t: int(t.get("raw_token_order") or 0)):
        h = token.get("tsv_hierarchy") or {}
        lines.setdefault((int(h.get("block_num", 0)), int(h.get("par_num", 0)), int(h.get("line_num", 0))), []).append(
            str(token.get("text") or ""))
    return "\n".join(" ".join(words) for _, words in sorted(lines.items()))


def _tokens(proof: Mapping[str, Any], page_number: int) -> list[Mapping[str, Any]]:
    return list(((proof.get("pages") or {}).get(str(page_number)) or {}).get("tokens") or [])


def _overlap(a_top: float, a_bottom: float, b_top: float, b_bottom: float) -> float:
    height = min(a_bottom - a_top, b_bottom - b_top)
    return max(0.0, min(a_bottom, b_bottom) - max(a_top, b_top)) / height if height > 0 else 0.0


def _in_band(token: Mapping[str, Any], band: Mapping[str, Any] | None) -> bool:
    return bool(band) and float(token["x0"]) >= float(band["x0"]) - 2 and float(token["x1"]) <= float(band["x1"]) + 2


def _statement_declarations(proof: Mapping[str, Any], pages: Iterable[int], parse_unit) -> list[dict[str, Any]]:
    found = []
    for number in pages:
        for line in page_text(proof, number).splitlines():
            parsed = parse_unit(line)
            if parsed:
                found.append({"page": number, "text": line, "currency": parsed["currency"], "unit_scale": parsed["unit_scale"]})
    return found


def verify_statement_unit(unit_evidence: Mapping[str, Any] | None, proof: Mapping[str, Any], *, source_page: int,
                          header_top: float | None, currency: str, unit_scale: int, parse_unit) -> list[str]:
    """The fact's own table declaration, bound by token ids/page/SHA, above the table header,
    consistent with every parsed declaration in the document (front and statement pages)."""
    layout = layout_for(proof.get("document_sha256")) or {}
    reasons: list[str] = []
    unit = dict(unit_evidence or {})
    evidence = dict(unit.get("evidence") or {})
    if unit.get("state") != "QUALIFIED" or not evidence:
        return ["STATEMENT_UNIT_EVIDENCE_MISSING"]
    page = int(evidence.get("continuation_of_page") or evidence.get("page_number") or -1)
    if page not in layout.get("statement_pages", ()) or int(evidence.get("page_number") or -1) != source_page:
        reasons.append("STATEMENT_UNIT_NOT_BOUND_TO_FACT_TABLE")
    if evidence.get("document_sha256") != proof.get("document_sha256"):
        reasons.append("STATEMENT_UNIT_DOCUMENT_MISMATCH")
    ids = list((evidence.get("source_span") or {}).get("token_ids") or [])
    by_id = {t.get("token_id"): t for t in _tokens(proof, page)}
    if not ids or any(i not in by_id for i in ids):
        reasons.append("STATEMENT_UNIT_TOKENS_NOT_IN_PROOF")
    else:
        text = " ".join(str(by_id[i].get("text") or "") for i in ids)
        if " ".join(text.split()) != " ".join(str(evidence.get("evidence_text") or "").split()):
            reasons.append("STATEMENT_UNIT_TEXT_NOT_IN_PROOF")
        if header_top is not None and any(float(by_id[i]["bottom"]) > float(header_top) for i in ids):
            reasons.append("STATEMENT_UNIT_NOT_ABOVE_TABLE_HEADER")
    if (evidence.get("currency"), evidence.get("unit_scale")) != (currency, unit_scale):
        reasons.append("STATEMENT_UNIT_VALUE_MISMATCH")
    declarations = _statement_declarations(proof, sorted(int(p) for p in (proof.get("pages") or {})), parse_unit)
    semantics = {(d["currency"], d["unit_scale"]) for d in declarations}
    if semantics != {(currency, unit_scale)}:
        reasons.append("STATEMENT_UNIT_DECLARATIONS_CONFLICT")
    declared_pages = {d["page"] for d in declarations}
    if page not in declared_pages:
        reasons.append("STATEMENT_UNIT_PAGE_UNDECLARED")
    return sorted(set(reasons))


def verify_row(row_object: Mapping[str, Any] | None, proof: Mapping[str, Any], *, metric: str, source_page: int,
               line_code: str, raw_value: str, value: int, unit_scale: int, parse_amount) -> list[str]:
    """Same-row proof by OCR coordinates; replaces the contiguous label+value string check.

    ``parse_amount`` is the existing accounting-integer parser, injected by the root-level caller.
    """
    layout = layout_for(proof.get("document_sha256")) or {}
    row = dict(row_object or {})
    reasons: list[str] = []
    if source_page not in layout.get("statement_pages", ()):
        return ["ROW_PAGE_OUTSIDE_REGISTERED_LAYOUT"]
    tokens = _tokens(proof, source_page)
    if not tokens or not row:
        return ["ROW_PROOF_MISSING"]
    bands = ((row.get("column_bands") or {}).get("bands") or {})
    header = ((row.get("column_bands") or {}).get("header_evidence") or {})
    identities = header.get("period_identities") or {}
    cur_band, cmp_band, code_band = bands.get("current_period_value"), bands.get("comparative_period_value"), bands.get("line_code")
    vbox, row_box = row.get("current_value_bbox") or {}, row.get("row_bbox") or {}
    if not (cur_band and cmp_band and code_band and vbox and row_box):
        return ["ROW_GEOMETRY_MISSING"]
    expected = (layout.get("metric_line_codes") or {}).get(metric)
    if expected is None or str(line_code) != expected or str(row.get("line_code")) != expected:
        reasons.append("ROW_LINE_CODE_NOT_EXPECTED_FOR_METRIC")
    by_order = {int(t["raw_token_order"]): t for t in tokens}
    # Current-period header: exact registered text, its own tokens in the proof, above the row.
    current = identities.get("current") or {}
    if (current.get("raw_text") not in layout.get("current_headers", ())
            or row.get("current_period_label") != current.get("raw_text")):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_REGISTERED")
    header_tokens = [by_order.get(int(o)) for o in current.get("source_token_orders") or []]
    if not header_tokens or any(t is None for t in header_tokens) or " ".join(t["text"] for t in header_tokens) != current.get("raw_text"):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_IN_PROOF")
    elif max(float(t["bottom"]) for t in header_tokens) > float(vbox["top"]):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_ABOVE_ROW")
    elif not (float(cur_band["x0"]) - 2 <= min(float(t["x0"]) for t in header_tokens)
              and max(float(t["x1"]) for t in header_tokens) <= float(cur_band["x1"]) + 2):
        reasons.append("CURRENT_PERIOD_HEADER_NOT_OVER_VALUE_COLUMN")
    # Value token: exact text and exact box, inside the current band, not inside the comparative band.
    value_tokens = [t for t in tokens if str(t.get("text")) == raw_value
                    and abs(float(t["x0"]) - float(vbox["x0"])) <= 1 and abs(float(t["top"]) - float(vbox["top"])) <= 1]
    if len(value_tokens) != 1:
        reasons.append("VALUE_TOKEN_NOT_UNIQUE_IN_PROOF")
        return sorted(set(reasons))
    token = value_tokens[0]
    if not _in_band(token, cur_band) or _in_band(token, cmp_band):
        reasons.append("VALUE_NOT_IN_CURRENT_PERIOD_COLUMN")
    on_row = [t for t in tokens if _overlap(float(t["top"]), float(t["bottom"]), float(token["top"]), float(token["bottom"])) >= 0.5]
    # Line code on the value's own physical row, inside the line-code band.
    codes = [t for t in on_row if _in_band(t, code_band) and str(t["text"]).strip() == str(line_code)]
    if len(codes) != 1:
        reasons.append("LINE_CODE_NOT_ON_VALUE_ROW")
    # No second amount in the current column on that row; a distinct comparative amount present.
    image_sha = ((proof.get("pages") or {}).get(str(source_page)) or {}).get("rendered_image_sha256")
    current_amounts = [t for t in on_row if _in_band(t, cur_band)
                       and _AMOUNT.match(baseline_two_value(t, image_sha)[0])]
    if len(current_amounts) != 1:
        reasons.append("ADJACENT_AMOUNT_AMBIGUITY")
    comparative = [t for t in on_row if _in_band(t, cmp_band)
                   and _AMOUNT.match(baseline_two_value(t, image_sha)[0])]
    if len(comparative) != 1 or comparative[0]["text"] != row.get("comparative_raw_value"):
        reasons.append("COMPARATIVE_COLUMN_NOT_PROVEN")
    # Label tokens: exact fragments, label band, inside the row box, and one of them on the value's line band.
    orders = [int(o) for o in row.get("label_source_token_orders") or []]
    labels = [by_order.get(o) for o in orders]
    if not labels or any(t is None for t in labels) or [t["text"] for t in labels] != list(row.get("raw_label_fragments") or []):
        reasons.append("LABEL_TOKENS_NOT_IN_PROOF")
    else:
        if any(not _in_band(t, bands.get("label")) for t in labels):
            reasons.append("LABEL_OUTSIDE_LABEL_COLUMN")
        if any(float(t["top"]) < float(row_box["top"]) - 3 or float(t["bottom"]) > float(row_box["bottom"]) + 3 for t in labels):
            reasons.append("LABEL_OUTSIDE_ROW")
        bounds = (row.get("physical_line_reconstruction") or {}).get("row_baseline_bounds") or []
        if len(bounds) != 2 or not (float(bounds[0]) <= (float(token["top"]) + float(token["bottom"])) / 2 <= float(bounds[1])):
            reasons.append("VALUE_OUTSIDE_ROW_BASELINE")
    # Exact amount and sign.
    try:
        numeric_raw, _ = baseline_two_value(token, image_sha)
        if parse_amount(numeric_raw) * int(unit_scale) != int(value):
            reasons.append("VALUE_PARSE_MISMATCH")
        if (raw_value.startswith("(") and raw_value.endswith(")")) != (int(value) < 0):
            reasons.append("VALUE_SIGN_MISMATCH")
    except (ValueError, TypeError):
        reasons.append("VALUE_PARSE_MISMATCH")
    return sorted(set(reasons))


def statement_unit_metadata_claims(proof: Mapping[str, Any], front_pages: Iterable[int], parse_unit) -> dict[str, Any] | None:
    """Document currency/unit claims sourced from statement-page declarations (registered layout only).

    Every statement page must declare, all parsed declarations (including any on front pages) must agree,
    otherwise None (stays blocked)."""
    layout = layout_for(proof.get("document_sha256"))
    if layout is None:
        return None
    statement = _statement_declarations(proof, [p for p in layout["statement_pages"] if str(p) in (proof.get("pages") or {})], parse_unit)
    front = _statement_declarations(proof, [p for p in front_pages if str(p) in (proof.get("pages") or {})], parse_unit)
    semantics = {(d["currency"], d["unit_scale"]) for d in statement + front}
    pages_declared = {d["page"] for d in statement}
    # Each fact's own table declaration is enforced by verify_statement_unit; here every parsed
    # declaration in the document must agree, and at least one statement page must declare.
    if len(semantics) != 1 or not statement:
        return None
    currency, unit_scale = semantics.pop()
    first = sorted(statement, key=lambda d: d["page"])[0]
    return {"currency": currency, "unit_scale": unit_scale, "page": first["page"], "text": first["text"],
            "declared_pages": sorted(pages_declared)}


STATEMENT_UNIT_CITATION_KIND = "statement_page_unit_declaration"
REPLACED_BY_ROW_PROOF = ("VALUE_SPAN_NOT_IN_RETAINED_DOCUMENT",)
REPLACED_BY_UNIT_PROOF = ("RETAINED_UNIT_SCALE_NOT_EXPLICIT", "RETAINED_CURRENCY_NOT_EXPLICIT")


def proof_reference(proof: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION, "proof_sha256": proof["proof_sha256"],
            "relative_path": f"{PROOF_DIR}/{proof['document_sha256']}/{proof['proof_sha256']}.json"}


def apply_layout_proof(row: Mapping[str, Any], proof: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None,
                       reasons: list[str], missing: list[str], *, parse_amount, parse_unit) -> tuple[list[str], list[str]]:
    """Replace exactly the two text-layer checks with coordinate proofs; never remove any other reason.

    Applies only to a row that carries an ``ocr_layout_proof`` reference for a registered layout.
    Any failed proof adds its own reason codes; an unavailable proof keeps the fact UNKNOWN.
    """
    ref = row.get("ocr_layout_proof")
    sha = str(row.get("document_sha256") or "")
    layout = layout_for(sha)
    if not isinstance(ref, Mapping) or layout is None:
        return reasons, missing
    if proof is None:
        return reasons, missing + ["OCR_LAYOUT_PROOF_UNAVAILABLE"]
    proof_reasons = verify_proof_identity(proof, document_sha256=sha, proof_sha256=ref.get("proof_sha256"))
    if (row.get("ticker"), row.get("reporting_period"), row.get("statement_scope")) != (
            layout["ticker"], layout["reporting_period"], layout["statement_scope"]):
        proof_reasons.append("OCR_LAYOUT_SCOPE_MISMATCH")
    row_object = row.get("ocr_row_object") or {}
    lineage = row.get("source_lineage") or {}
    source_page = row.get("source_page") if row.get("source_page") is not None else lineage.get("source_page")
    line_code = row.get("line_code") if row.get("line_code") is not None else lineage.get("line_code")
    try:
        proof_reasons += verify_row(row_object, proof, metric=str(row.get("canonical_metric")),
                                    source_page=int(source_page or -1), line_code=str(line_code),
                                    raw_value=str(row.get("raw_value_text") or ""), value=int(row.get("normalized_value")),
                                    unit_scale=int(row.get("source_unit_scale") or 0), parse_amount=parse_amount)
    except (TypeError, ValueError, KeyError):
        proof_reasons.append("ROW_PROOF_MALFORMED")
    claims = (metadata or {}).get("metadata_claims") or {}
    statement_unit_claims = [name for name in ("currency", "unit_scale")
                             if (((claims.get(name) or {}).get("evidence_span") or {}).get("citation_kind")
                                 == STATEMENT_UNIT_CITATION_KIND)]
    if statement_unit_claims:
        header_top = ((((row_object.get("column_bands") or {}).get("header_evidence") or {}).get("bbox") or {}).get("top"))
        proof_reasons += verify_statement_unit(row.get("ocr_unit_evidence"), proof, source_page=int(source_page or -1),
                                               header_top=header_top, currency=str(row.get("currency")),
                                               unit_scale=int(row.get("source_unit_scale") or 0), parse_unit=parse_unit)
    if proof_reasons:
        return sorted(set(reasons + proof_reasons)), missing
    replaced = set(REPLACED_BY_ROW_PROOF) | (set(REPLACED_BY_UNIT_PROOF) if statement_unit_claims else set())
    return [r for r in reasons if r not in replaced], missing
