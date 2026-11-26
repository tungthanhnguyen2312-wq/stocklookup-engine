"""Test-session bootstrap for the source/runtime split.

`stock-core-private` holds source only; the generated runtime state it operates on
(`vn_stock.db`, `data_bctc/`, `financial_snapshot.*`, the published frontend files)
lives in the runtime root -- `dashboard-runtime` in this workspace. Production code
resolves that split through `STOCK_LOOKUP_RUNTIME_ROOT` (see `runtime_paths.py`).

Without the variable set, every module-level path constant falls back to its legacy
default (the source directory), so an unconfigured `pytest` run read empty inputs and
reported failures that say nothing about the code under test. `tests/test_export_ai_bundle.py`
already discovered and exported the variable at import time; doing it once here makes
every module see the same root regardless of collection order, while still honouring an
explicitly configured value.
"""

from __future__ import annotations

import os
from copy import deepcopy

import pytest

from _runtime_root import RUNTIME_ROOT, _RUNTIME_ROOT_ENV

if not os.getenv(_RUNTIME_ROOT_ENV, "").strip():
    os.environ[_RUNTIME_ROOT_ENV] = str(RUNTIME_ROOT)

# A provisioned owner host must not change test outcomes: the Windows production OS-enforcement
# backend is disabled for the test session (disable-only switch, inherited by subprocesses; see
# provider_windows_os_backend.DISABLE_ENV). Tests of the real backend clear it explicitly.
os.environ["STOCKLOOKUP_PROVIDER_OS_BACKEND"] = "disabled"

# Explicit test tiers (hermetic / retained-evidence / provider-runtime); see tests/_test_tiers.py.
from _test_tiers import (  # noqa: E402,F401 -- re-exported as this conftest's pytest hooks
    pytest_collection_modifyitems,
    pytest_configure as _configure_test_tiers,
    pytest_runtest_setup,
)

# No test may write into canonical retained evidence (RETAINED_EVIDENCE_INCIDENT_20260925);
# see tests/_canonical_evidence_write_guard.py. Installed before any test module is imported.
import _canonical_evidence_write_guard as _evidence_write_guard  # noqa: E402
from _canonical_evidence_write_guard import (  # noqa: E402,F401 -- re-exported fixture and hook
    canonical_evidence_write_guard,
    pytest_sessionfinish,
)

_evidence_write_guard.install()


def pytest_configure(config):
    _configure_test_tiers(config)
    config.addinivalue_line(
        "markers", "registry_gate_real: exercise the real financial registry integrity gate")


@pytest.fixture(autouse=True)
def legacy_owner_daily_registry_inputs(request, monkeypatch):
    """Keep legacy workflow fixtures focused on their own boundaries, without source inputs.

    Real registry tests opt out explicitly and retain the production integrity gate.
    These fixed synthetic bindings are parser-valid test data, never approval evidence.
    """
    if request.node.get_closest_marker("registry_gate_real") is not None:
        return
    from tools import run_owner_daily
    bindings = {
        "layouts": {"path": "config/official_financial_layouts/r0001.json",
                    "revision": 1, "sha256_lf": "a" * 64},
        "issuers": {"path": "config/official_financial_issuers/r0001.json",
                    "revision": 1, "sha256_lf": "b" * 64},
        "capacity_receipt_sha256_lf": "c" * 64,
    }
    monkeypatch.setattr(run_owner_daily, "_require_financial_registry_inputs",
                        lambda root, **kwargs: deepcopy(bindings))
