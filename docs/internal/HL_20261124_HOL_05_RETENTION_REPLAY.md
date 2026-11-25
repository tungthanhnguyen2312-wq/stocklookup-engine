# HL-20261124-HOL-05 review receipt

Base: `6883f8b9ec06974f85160e04e371b25807b0fa0b`. Single-writer local patch;
no network, download, Daily, production/runtime write, deployment, commit or push.
Owner decision 2026-11-24: VSDC is official for registered-securities counts and
share-changing events, market-wide where supported. Registered, listed and
outstanding ex-treasury remain distinct; publication, record and effective/listing
dates remain distinct. The prototype registry flag remains OFF.

## Changes

- [Acquirer](../../stocklookup_core/evidence/official_document_acquisition.py):
  exclusive finite operator VSDC notice scope, validated as a whole before side
  effects; financial cohort and all transport/registry/storage controls unchanged.
- [Retention CLI](../../tools/retain_vsdc_share_notices.py): CSV validation,
  discovery provenance, dry-run plan and governed acquisition.
- [Replay CLI](../../tools/replay_vsdc_valuation_impact.py): explicit retained inputs,
  source identity verification, aware cutoff, real resolver OFF/ON, existing valuation
  builder, all changed tickers including those outside the valuation universe.
  Reports original provider shares even where the baseline resolver withholds them.
- [Focused tests](../../tests/test_vsdc_notice_retention_replay.py): fake-fetcher
  retention, whole-list refusal, registry/host controls, cache/interval checks,
  CSV dry-run and four committed registration fixtures through both real engines.
- [Capacity receipt](../../config/owner_daily_capacity_qualification.json) and
  [transition test](../../tests/test_owner_daily_host_preflight.py): changed acquirer
  pin, two added-tool pins and `vsdc_market_wide_retention_corrective`.
- [Contract](../official_document_acquisition_pilot.md), [active state](../ACTIVE_STATE.md),
  [capabilities](../CAPABILITIES.md): scope, Owner decision and remaining gates.

## Operator CSV dry-run

Input `vsdc_notice_urls_for_retention.csv` SHA-256:
`53c7cee82df0841ec82d9fb1688fa19391ccff99a017c8b71a76fc1573a488fd`.

```json
{"execution_allowed":true,"minimum_interval_seconds":15.0,"minimum_wall_seconds":4035.0,"planned_requests":270,"rejected_rows":[],"rows":270,"timing_basis":"UNCACHED_ONE_ATTEMPT_NO_REDIRECTS_EXCLUDES_HTTP_DURATION","unique_tickers":192}
```

169 registration-change and 101 record-date notices. Minimum spacing: 67 minutes
15 seconds, excluding HTTP duration, retries and redirects. No rejected rows;
no HTTP or destination creation during dry-run.

## Validation and pins

Final focused run: **159 passed, 5 subtests passed**, in 134.26 seconds. Selection:
`test_vsdc_notice_retention_replay.py`, `test_official_document_acquisition.py`,
`test_vsdc_hose_share_events.py`, `test_acquisition_registry_gate.py`,
`test_market_wide_current_valuation_input_scaleout.py`, `test_repository_layout.py`,
and `test_owner_daily_host_preflight.py::test_offline_financial_capacity_transition_preserves_the_qualified_daily_source`.
All pytest runs used the task-designated core-313 interpreter, a scratch USERPROFILE
and an explicit worktree-local basetemp. The first bounded
retention/resolver suite passed 79 tests and 5 subtests. An expanded run before
adding the two future tracked-file pins had 206 passed, 1 skipped, 5 subtests
passed and 1 failure: `test_windows_inventory_real_probe_is_read_only_and_usable`
received `processes=None` from the sandboxed Windows CIM inventory. No host-policy
change was made. `git diff --check` passed.

E4 v2 source digest (unchanged):
`1d583174707853c1efd3b4835e0b73b8dbc741363f1ea0a79b681e5f1c2f120a`.
All candidate source pin hashes match their bytes; no unexplained unpinned tracked
paths. The only pin paths missing from Git enumeration are the two new tools.

The shared Git worktree index lies outside the writable sandbox. An attempted
intent-to-add failed with `index.lock: Permission denied`; it changed no index.
Consequently live capacity `source_matches` will remain false until the reviewer
stages the two new tools. Pins are prepared for that staged candidate; this is
not a fresh capacity measurement or Daily qualification. After staging, rerun
the source-match and receipt-transition tests from the normal review workspace.

## Remaining gaps and resume

The four-fixture test uses exact VDS/FPT/NVL/SSB committed registration bytes
and explicitly synthetic same-ISIN venue witnesses. It proves resolver adoption
of 299,200,000 / 1,885,727,648 / 2,403,805,052 / 3,468,800,000 registered shares
at a stated cutoff. Synthetic witnesses are linkage tests, not retained venue
proof. The real 270-notice set supplies the operator's actual venue witnesses.

The current valuation builder does not admit `official_registered_shares` as a
research tier. The tests prove that OFF metrics can be research-usable while ON
metrics are BLOCKED, with null after-values and percentage changes. This is a
real boundary, not a numeric zero or a formula failure. A numeric registered-share
sensitivity requires a reviewed valuation-use decision; this task does not silently
equate registered and current common-outstanding shares.

The real downloads and full-market replay await Claude after review. Replay takes
the same exact price/fundamental/share-promotion/official-financial-panel source
artifacts as the existing materializer, not the downstream financial-analysis or
integrated-decision artifact. Pass all baseline event roots plus the new retained
VSDC root and a stable read-only provider inventory. See the contract for CLI flags.

The referenced `operations-review/HEAD_LEADER_CONTRACT.md` was absent; the standing
rules in the task instruction were followed. No workaround or agent delegation.
