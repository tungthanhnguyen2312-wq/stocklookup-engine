# Official corporate-action HOSE ex-date qualification — closeout (2026-10-25)

Milestone: `OFFICIAL_CORPORATE_ACTION_EVENT_EVIDENCE` — PIT blocker closure, bounded real-source
qualification for HPG/PVD (SSI, POW refusal-scoped). Local checkpoint only: no push, PR, merge,
Daily, deploy, DB write or authority promotion.

## 0. Crash-safe recovery (before any new work)

- PR #191 worktree `worktrees/repository-layout-migration-20261025`, branch
  `refactor/repository-layout-migration-20261025`, HEAD `5209a47cbcb102738e3380e34d2758acea28856c`:
  no tracked change, no untracked file, no `*.lock` in the worktree or common git dir, HEAD equal to
  `origin/refactor/repository-layout-migration-20261025` (`git ls-remote`). Hosted CI 5/5 SUCCESS.
  Closed as PR REVIEW-READY; not reworked. The two interrupted local batches were not resumed.
- No `python.exe` running. Protected checkout `stock-core-private` (main, 105 behind origin) has only
  its long-standing untracked `data/` (newest file 2026-09-19); nothing under it changed after 2026-10-24.

## 1. Sources (Producer-retained; leads from ai-agent-inbox#51 `bbc153fb`)

Retained via `official_document_acquisition.acquire` (registry `hose`, `staticfile.hsx.vn`, 10 s
interval, 9 requests, 0 retries) under
`operations-review/official-ca-hose-ex-date-qualification-v1-20261025/official_document_retention/`.
All nine are image-only scans (`needs_ocr`). `published_at` is deliberately null.

| HOSE id | Ticker | Class | SHA-256 | Producer receipt (UTC) | #51 SHA |
|---|---|---|---|---|---|
| 2462408 | HPG | ex_right_notice (1121/TB) | `7051ea19…449f7c` | 2026-10-25T11:15:26Z | equal |
| 2477123 | HPG | listing_change_notice (1475/TB) | `12a009fb…5d5cce` | 11:15:36Z | equal |
| 2469047 | HPG | issuer result report 03/BC | `da24dbd7…71d543` | 11:15:48Z | new (was INCOMPLETE) |
| 2474001 | PVD | ex_right_notice (1421/TB) | `4c1153c8…1f58f78` | 11:15:57Z | equal |
| 2492067 | PVD | listing_change_notice (1775/TB) | `950148fd…3679d7` | 11:16:09Z | equal |
| 2483453 | PVD | result report of 28/07 (superseded) | `68048e51…ec4e18` | 11:16:19Z | new |
| 2484275 | PVD | correction of 29/07 + revised report | `e593ea81…9c572e1f` | 11:16:28Z | new |
| 2485374 | SSI | ex_right_notice (1634/TB) | `4be4d1f8…62e01e1a` | 11:16:46Z | equal |
| 2430881 | POW | listing_change_notice (72/TB) | `59a16702…e0767` | 11:16:56Z | equal |

Full hashes, URLs and HTTP headers: `official_document_acquisition_manifest.json` and the artifact.
HTTP `Last-Modified` is retained only as a server file clock: SSI's identical bytes report
`10:40:44 GMT` now versus `08:59:45 GMT` in #51's fetch, so it cannot be a publication clock.

## 2. Method (existing machinery, no second engine)

- `corporate_action_events.reviewed_scan_observation`: no OCR configuration gives both Vietnamese
  cues and clean digits (`vie` prints `²` for `2`; `vie+eng` drops diacritics) and tokens are never
  repaired. A reviewer cites each field's page and printed token; the value is parsed from the token
  and the token must occur verbatim on that page of the governed OCR sidecar
  (`derived/hose_scan_ocr_sidecar.json`, sha `b5cd0028…eeaa254f`, Tesseract 300 dpi, psm 6).
  Evidence method `VISUALLY_REVIEWED_SCAN_OCR_TOKEN_CORROBORATED`. Planned counts are
  `shares_planned`, never `shares_issued`.
- `official_corporate_action_ledger` (additive; legacy ledgers replay byte-identically):
  planned-count bridge through a document stating both counts; stated entitlement rate takes
  precedence over count-derived ratios; count-derived ratio over a treasury-inclusive total is refused;
  `ratio × entitled shares ≈ planned` corroboration (violation conflicts the entry); co-documented legs.
- `qualified_corporate_action_factor_chain`: a same-ex-date leg without adjustment policy (cash)
  blocks the share factor (`OTHER_EVIDENCE_GAP`).
- Knowledge cutoff: per-document `project_official_evidence_temporal_metadata` → first observed,
  `FROM_FIRST_OBSERVED_FORWARD_ONLY`; entry cutoff = latest receipt among its documents. The governed
  calendar ends 2026-09-04, so the research session stays unresolved and is reported as such.

## 3. Event results

| Event | Result | Facts proven | Gate |
|---|---|---|---|
| HPG stock dividend 10% | `FACTOR_CHAIN_QUALIFIED` (offline scope), factor 1/1.1 | ex 2026-05-25 (HOSE 1121), record 2026-05-26; planned 767,546,585 → executed 767,498,665 (47,920 fractions cancelled); 7,675,465,855 + 767,498,665 = 8,442,964,520 across docs; treasury 0 (outstanding stated); rate × outstanding ≈ planned | knowledge from 2026-10-25T11:15:48Z only |
| PVD bonus 66.9% | `FACTOR_CHAIN_QUALIFIED` (offline scope), factor 1/1.669 | ex 2026-07-14 (HOSE 1421), record 2026-07-15; planned 371,883,724 → executed 371,862,185; 556,296,006 + 371,862,185 = 928,158,191; entitled = 555,880,006 outstanding (416,000 treasury excluded) — rate × outstanding ≈ planned proves the basis | knowledge from 2026-10-25T11:16:28Z only |
| SSI cash 1,000 VND | not a ledger entry; no cash factor policy | ex 2026-08-17, record 2026-08-18, payment 2026-09-14 preserved as its own leg | cash: `REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY` |
| SSI bonus 5:1 | not a ledger entry (`record_date_confirmed`) | ex 2026-08-17, ratio 0.2; planned count `500.²19.550` unreadable in every OCR read → not cited | no Producer-retained execution document |
| POW 4% + 15% | no ex-date, legs not separable | listing change 444,949,496 combined, after 2,786,821,096, effective 2026-01-13, trading 2026-01-27 | `MISSING_EXPLICIT_EX_DATE` |

Corrections to #51: PVD listing notice is 1775/TB, QĐ 669 dated 20/08/2026, effective 24/08, trading
07/09; POW QĐ 29 dated 09/01/2026, trading 27/01/2026 (was UNKNOWN); PVD correction changed only the
"total distributed" line (371,883,632.03 → 371,862,185), executed count unchanged; the HPG/PVD
ledger links #51 reported as MET could not form under the existing ledger (planned ≠ executed key)
until the issuer result reports were retained.

## 4. Boundary (unchanged authority)

Historical PIT eligible: NO for every event (factor known after every ex-date; downstream gate returns
`PIT_FACTOR_NOT_KNOWABLE_BY_DECISION_CUTOFF`). PIT backtest, execution replay, `ACTIVE_UNIVERSE`,
applicable-CA coverage and event-free intervals: UNKNOWN/blocked. HOSE VND prices have no
representation contract to join any other scale. Observed price ratios are never factors.
`AUTHORITY.md` CA row is unchanged.

## 5. Tests and resources

`tests/test_official_ca_hose_ex_date_qualification.py`: 28 pass (2 need the ignored PDF bytes and
skip in CI). Targeted regression (20 modules, one process): 486 pass; 4 fail identically on clean
`origin/main` 92fe7612 in the same location (missing `mva-daily` retained artifact; Consumer p1g
runtime upstream files) — pre-existing, environmental. Free RAM 1.3–1.7 GB of 15.7 GB throughout;
C: 49 GB free. Logs under the evidence `logs/` folder (ignored).

## 5a. Review acceptance (second pass, same day)

- Reproduction: with only the tracked manifest copied into an empty root, `acquire()` re-downloaded
  all nine HOSE originals with identical bytes (`cached_valid`, `refreshed_same_bytes`) and left the
  manifest byte-identical. A reviewer can therefore restore the ignored PDFs with
  `--acquire` and un-skip the two byte-level tests.
- Every cited page (HPG 1121 p1, 1475 p1, 03/BC p1–2; PVD 1421 p1, 1775 p1, revised report p6–7,
  original p3/p8, correction p1; SSI 1634 p1; POW 72 p1) was compared against the rendered original.
  Each cited token matches what is printed on its page.
- Fix: token corroboration now refuses a value inside a longer number (`10%` in `110%`, `1.000` in
  `21.000`). The artifact replayed byte-identically under the stricter rule.
- Boundary: the PIT_BACKTEST gate refuses both factors for every governed session close
  (2026-06-03..2026-09-04) and for one second before each receipt instant.
- PR interaction: #191 moves `market_only_pit_eligibility.py` into `stocklookup_core/evidence/`. The
  test imports it from either location. #189 and #191 edit other `ACTIVE_STATE.md` lines; with all
  three merged, the active set is 102,391 of 102,400 bytes.

## 6. Handoff

Branch `feature/official-ca-hose-qualification-20261025`, worktree
`worktrees/official-ca-hose-qualification-20261025`, based on `origin/main` 92fe7612; one local commit.
Replay: `python tools/run_official_ca_hose_ex_date_qualification.py` (offline; `--acquire`/`--ocr`
only to rebuild retention). Owner decisions open: (1) whether reviewed-scan facts may feed any
non-PIT current-research adjusted series; (2) SSI execution needs a HOSE staticfile locator for
715/QĐ or 1935/TB (only CafeF mirrors known); (3) POW needs an official ex-date document; (4) a cash
adjustment policy; (5) governed calendar coverage past 2026-09-04.

## 7. PR #192 integration closeout after PR #191

Owner-authorized bounded closeout `OFFICIAL_CA_HOSE_EX_DATE_PR192_INTEGRATION_CLOSEOUT`;
this is not a new native roadmap milestone. The preceding sections remain the
original implementation-time record.

- Verified live main `2957a55f77757afb67ba8297bcde970f403d0719`, after merged #189,
  #190 and #191, and unchanged PR head `51892169702e292bd1a1f7da0929576c626a352b`.
  GitHub reported mergeable and `git merge-tree --write-tree` independently found
  a clean merge. Main was merged normally into the existing branch at
  `69e5658a3dc3b704d2c6e92886bcbbb479a5bd0a`; no conflict was invented or history rewritten.
- The existing test's `canonical_market_bars.pit` reference reaches the moved
  package owner and preserves the contract. No compatibility shim, source retarget
  workaround or corporate-action engine change was required.
- Added the HOSE qualification and repository-layout source-transition tests to
  the existing Producer focused CI selection. Only the changed workflow's LF
  fingerprint in `daily_path_launchers.json` was refreshed; launcher targets and
  frozen identity inputs are unchanged.
- Compact CA navigation now explicitly distinguishes offline-qualified HPG/PVD
  factors from zero historically knowable factors. The active set is 102,374 of
  the unchanged 102,400-byte budget. The CA row in `AUTHORITY.md` remains byte-identical.
- Focused qualification/ledger/factor, source-transition, active-navigation and
  offline production call-shape checks: **76 passed**, including all 28 HOSE tests
  against the already-retained originals. Exact offline artifact replay matched
  the committed JSON; manifest, OCR sidecar and original artifact bytes were not written.
- Named E2/E3 pins, archived migration sources, live retargeted orchestrators,
  E4/E5 fixture boundaries and provider-bundle fixture boundaries match merged
  main. Python 3.11 syntax parsing passed for the changed Python files. No frozen
  digest, historical receipt or original acquisition clock was refreshed.
- The first local curated-selection attempt hit six import-time refusals from
  this workstation's real `active_workspace.json`: a development worktree is not
  the active production writer. The identical six refusals were reproduced on a
  detached checkout of the **actual** base `2957a55f`. No guard was weakened and
  the binding was neither moved nor edited. The unchanged selection is rerun in
  one foreground pytest interpreter with an isolated test-only `Path.home` and
  no inherited Stock Lookup workspace variables, matching a clean hosted runner.
  Final counts and exact hosted source-head validation are recorded on PR #192.
- GrokBot #51/#52 terminal reports were reviewed only for relevant boundaries:
  Hub chains are leads, not Producer qualification; #52 reports no qualified
  historical ACTIVE interval and no OHLC unit/basis/board-scope closure. No
  acquisition, browser search, credentialed probe, source registration or new
  authority follows from those reports.

HPG remains factor `0.909090909091`, known from
`2026-10-25T11:15:48.164930Z`; PVD remains `0.599161174356`, known from
`2026-10-25T11:16:28.534785Z`. Exact HOSE citations and receipt semantics are
unchanged. Historical PIT, RAW_AS_TRADED, execution, market-wide CA authority,
SSI cash/bonus factors and POW factors remain unpromoted/refused. Owner-authorized
normal PR publication/merge is conditional on the final exact-head hosted checks;
no Daily, production/DB/runtime write, Consumer/Dashboard change, deployment or
successor milestone is included.
