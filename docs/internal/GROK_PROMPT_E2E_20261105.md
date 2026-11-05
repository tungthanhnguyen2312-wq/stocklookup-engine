# GROK PROMPT — Sustainability E2E run, 2026-11-05

You are the executor (single writer) for Stock Lookup's `STOCKLOOKUP_SUSTAINABILITY_PROGRAM_V1`.
The Tech Lead is Claude. Lead's decisions and their basis are in
`docs/internal/LEAD_REVIEW_20261105_SUSTAINABILITY_NEXT.md` on branch `docs/lead-review-20261105`
of `stocklookup-engine`. Read §5 and §8 before you start. The Owner has delegated full decision
authority to the Lead. Everything authorized below is authorized; anything not listed is NOT.

Work folder for logs, results and HANDOFF: `T:\StockLookup\scratch\grok-e2e-20261105\`.
Python: `T:\StockLookup\production-v1\environments\core-313\Scripts\python.exe`.
Run the phases in order. Finish each phase with a JSON result file and a line in `HANDOFF.md`
before you start the next phase. If a phase hits a STOP condition, record it, skip the phases
that depend on it, and continue with the independent ones (B–D do not depend on E; E does not
depend on B–D).

## Global rules (apply to every phase)

1. **Daily guard.** Before every heavy-IO step (copy, hash, benchmark, seed, scrub, vault), check
   that no Owner Daily is running. Check process command lines for `run_owner_daily` and
   `owner_daily`, and check the Daily journal/lock under `T:\StockLookup\production-v1\run-logs`.
   If a Daily is running, or the local time is 15:00–20:00 and you cannot prove today's Daily
   already finished, do light work only (code, unit tests, docs) and wait. Never compete with a
   Daily for T: or RAM.
2. **One heavy-IO job at a time.** Never overlap copy/hash/benchmark/vault.
3. **Production is read-only.** Never modify anything under `T:\StockLookup\production-v1\`.
   The only exception is creating new checkpoint folders that a phase names explicitly.
   No deploy, no `git pull` in the Production checkout, no seed/scrub against Production state.
4. **No deletion** except the exact paths in A1/A2, and only after their verification gates pass.
5. **Git.** Push branches and open PRs. **Do not merge.** The Lead reviews and merges.
6. **Evidence.** Every number goes into a JSON file with its path. Never report a number that
   has no result file behind it.
7. **RAM.** The child job ceiling stays 2 GiB, the deadline stays 1,200 s, and the T: rehearsal
   floor stays 340 GiB. Never lower any of them.
8. **Invariants.** Feedback contract, classification, horizon, maturity, ordering,
   `artifact_identity` and output bytes for identical inputs stay unchanged.

## Phase A1 — Retire merged M1 scratch (D-S1)

Targets, and no others:
- `T:\StockLookup\scratch\tplus-v2-rehearsal-20261104`
- the worktree `T:\StockLookup\scratch\wt-tplus-incremental-v2-baseline-20261104`

Steps:
1. Prove there are no references: `git worktree list` in every repo under `T:\StockLookup`;
   no open handles (no process has a cwd or open file inside). If either check fails, STOP A1
   and report the blocker.
2. Copy `*-result.json`, `*-host.json`, `*proof*.json`, `HANDOFF*.md`, `PROMPT*.md`, `*.log`
   (only files < 50 MB) into the new folder
   `T:\StockLookup\production-v1\recovery-checkpoints\20261105-scratch-retire\` with a
   `MANIFEST.sha256`. This new folder is the only write allowed under `production-v1`.
3. Remove the worktree with `git worktree remove` (no `--force` unless it is clean), then delete
   the rehearsal folder.
4. Gate: T: free increases by ≥ 10 GiB. Result: `A1-result.json`.

## Phase A2 — Archive and retire preseal rehearsal sandboxes (D-S2)

Targets, and no others:
- `T:\StockLookup\scratch\preseal-producer-seal-20261026-r8` (~177 GiB)
- `T:\StockLookup\scratch\preseal-producer-seal-20261026-r10` (~179 GiB)

These are 27–28/10 preseal memory rehearsal sandboxes. In r10, `guard-result.json` shows
returncode 1 and `BLOCKED_RUNTIME_RELEASE`, and authority effect is NONE.

Steps:
1. Identity check: W: must be label `WD4TB_BACKUP`, volume
   `{853437c5-ce35-43eb-ad4f-083d09e9fbe4}`, Healthy. T: must be label `uhigasi`, volume
   `{e12216ac-1354-41da-a384-305f67ae820e}`. On any mismatch, STOP A2.
2. Re-confirm there are no references: grep `stock-core-private`, `operator-config`, `run-logs`
   (last 14 days) and every worktree's `config/` for `preseal-producer-seal-20261026`. Re-confirm
   no writes since 2026-11-04 (include hidden files). If either fails, STOP A2 and report.
3. Build a full SHA-256 manifest of each source tree (path, size, sha256, mtime) **before** copying.
4. Copy each tree, as is, to `W:\ProjectVault\StockLookup\scratch-archive\20261105\<name>\`.
   Use robocopy `/E /COPY:DAT /DCOPY:DAT /R:2 /W:5 /NP /LOG:`, one tree at a time.
5. Re-hash every file on W: and compare it with the source manifest. The gate is **100% match**
   (count, size, sha256). Store both manifests, and the comparison, on W: and in the work folder.
6. Only after the gate passes: delete the source tree from T:. Then do the next tree.
7. Also measure and report, but do NOT touch: `owner-daily-16gb-recovery-20261028`,
   `iid-runtime-memory-evidence`, `T:\StockLookup\worktree-archives`, the other `wt-*` worktrees.
   For each one, report size, link count of its largest files, references, and last write time.
8. Gate: T: free ≥ 680 GiB (approx.). Result: `A2-result.json`.

## Phase B — M1b final-code release candidate (P-2)

Worktree `T:\StockLookup\scratch\wt-tplus-m1b-20261104`, branch
`fix/tplus-incremental-cost-v2-m1b`, HEAD `3a9cc727`. Read its scratch HANDOFF at
`T:\StockLookup\scratch\tplus-m1b-rehearsal-20261104\HANDOFF.md`.

1. Integrate `origin/main` = `63c92f48` (6 main-only commits, including PR #211). Prefer a merge
   commit if the rebase conflicts in owner-daily files. Record which method you used, and why.
   Resolve conflicts without changing semantics. Re-run the source-transition and roadmap tests.
2. Run all focused M1b tests (200+) and the related suites. All must PASS. Record which ones are
   pre-existing failures, each proven on unmodified main.
3. Real-corpus measurements **on the final code**, using the existing rehearsal state/oracle
   harness (`run_corpus.py`, `prepare_*.ps1` in the rehearsal folder):
   cold parity vs oracle (62,271 rows; artifact `28b9c2af…`; raw `3bd9080e…`), add (one new T0),
   post, and R2 all-invalidated.
   Rehearsal scratch growth ≤ 8 GiB. Clean up after, with a manifest.
4. Mandatory gates (contract text, unchanged):
   - byte parity;
   - add ≤ 600 s;
   - add + post ≤ 900 s;
   - child peak private ≤ 2 GiB.

   R2 and discovery are recorded only. They are not gates.
5. Forbidden: editing `prospective_decision_outcome_feedback._source_fingerprint`,
   `prospective_decision_retention._original_reuse_reasons`, catalog qualification (that is M1c,
   later), the roadmap status, and Production.
6. Update the M1b receipt `docs/internal/TPLUS_INCREMENTAL_COST_V2_M1B_REHEARSAL_20261104.json`
   with the final-code numbers. Result: `B-result.json`.

If a mandatory gate fails, STOP B and C, and go to D.

## Phase C — M1b PR + activation script (P-3, preparation only)

1. Push the branch and open a PR to `main`. The PR body should hold the gates table, parity
   hashes, the seed/scrub expectations, and the activation procedure. Wait for CI. Fix only CI
   failures caused by this branch.
2. Write `tools/ops/Invoke-M1bActivation.ps1`, or put it next to the existing
   `claude-reports/sustainability-program-20261103/m1-activation/Invoke-M1Activation.ps1` pattern
   if the repo has no ops folder. It must:
   - run preflight: RAM, no writer, T: floor, the Production HEAD equals the expected prior HEAD,
     and a registry hash guard;
   - ff-only deploy to the merged SHA, passed as a parameter;
   - run `--seed-state-only` and accept **only if** exit code is 33 **and** the stdout JSON
     shows `status == "SEEDED"` **and** the T0/legacy/sidecar counts match the inventory;
   - run `--scrub-sources` and require exit 0;
   - write a receipt to `recovery-checkpoints\<date>-m1b-activation\`;
   - use `--root` = `--state-root` = `T:\StockLookup\production-v1\retained-evidence`;
   - read big files with `[IO.File]::ReadAllText`, never `Get-Content -Raw`;
   - support a `-PreflightOnly` switch.
3. **Do not run the script against Production.** Run only `-PreflightOnly`, and record its output.
   The Owner runs activation after the Lead merges.
4. Result: `C-result.json`, with the PR URL and CI status.

## Phase D — M2 storage ledger + disk probe (P-5)

New worktree `T:\StockLookup\scratch\wt-m2-storage-ledger-20261105` from `origin/main`, on branch
`feature/m2-storage-ledger`. Do not touch any `prospective_decision_*` file.

1. Add a read-only ledger tool, for example `tools/storage_ledger.py`. It must produce:
   - physical bytes per group (retained-evidence by artifact family and session, T+ store and
     sidecars, IID, physical duplicates by sha256 + nlink + file-ID, scratch, recovery-checkpoints,
     worktree-archives);
   - per-session growth;
   - runway in sessions and at 30/90 days, against the 160 GiB floor;
   - output that agrees within ±2% with the volume's free/used bytes.

   Hashing must be bounded and resumable. It takes no locks, and it obeys the Daily guard.
2. Fix `owner_daily_progress.py:327`: probe the volume of the Daily output_root, not `C:\`.
   Runway < 10 sessions = WARNING, < 5 = CRITICAL warning. **Warnings only**:
   `AUTHORITY_EFFECT` stays `NONE_OPERATIONAL_OBSERVABILITY_ONLY`, and admission/preflight do not
   change. Follow the repo's source-transition/AST-pin rules if this file is pinned.
3. Tests, a contract doc entry under the existing M2 slot of
   `docs/tplus_incremental_cost_v2_contract.md` (respect the active-docs reading budget), push,
   PR, CI. Do not merge.
4. Run the ledger once against real T: (after A2), and save `D-ledger.json`.
5. Write a **D4a proposal**: forward-only dedupe of IID ×2, full-universe ×2, valuation ×3 for
   new sessions. Include measured bytes per session, the mechanism, how seal, identity and T+
   fingerprints are preserved, and the risks. Proposal only, no implementation.
   Result: `D-result.json`.

## Phase E — D3 vault backup + restore rehearsal (P-4)

1. Use the existing Vault V1 tools (`tools/vault_snapshot.py`, `tools/vault_post_daily_adapter.py`,
   `tools/vault_retention.py`) and the procedure that produced the last receipt (2026-10-16) under
   `W:\ProjectVault\StockLookup` / `W:\ProjectVault\Manifests`. Find that procedure; do not invent
   a new one.
2. Scope: sealed sessions after the last receipt (10-16) up to the latest sealed session.
   Copy-only. The explicit payload budget above the 64 MiB default is authorized for this run by
   the Lead (D3). Record the budget you used.
3. If the tools need a completion boundary or adapter that does not exist for these sessions,
   STOP E. Report exactly what is missing. Do not hand-craft boundaries, and do not fall back to a
   plain copy for Production evidence.
4. Restore rehearsal: restore 1 session from W: into `T:\StockLookup\scratch\restore-rehearsal-20261105\`
   (after A2 has freed space). Run `restore_verify` and byte-compare with the original. Record how
   the restored files' volume ID/file ID differ (input for D5). Delete the restore copy afterwards.
5. Result: `E-result.json`, with the receipt and manifest paths on W:.

## Final HANDOFF (`T:\StockLookup\scratch\grok-e2e-20261105\HANDOFF.md`)

One table per phase: status (DONE / STOPPED + reason), key numbers, result file path, commits,
PR URLs, T: free before/after, peak RAM.

Then list:
- what the Lead must review;
- what the Owner must run (M1b activation);
- every deviation from this prompt.

Do not start M1c (discovery, D6), D4a implementation, D4 or D5.
