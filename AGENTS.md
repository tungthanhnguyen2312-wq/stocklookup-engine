# Repository guardrails

## Reading contract — start here

Ordinary work runs `python tools/stocklookup_roadmap.py --check --json`, then opens only the compact file the task table names. The navigation set remains, in this order:

1. This file (`AGENTS.md`).
2. [`docs/ACTIVE_STATE.md`](docs/ACTIVE_STATE.md) — what is true now: gate, launch conditions, blockers, next action.
3. [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) — every capability's status, contract, authority and blocker.
4. [`docs/AUTHORITY.md`](docs/AUTHORITY.md) — who may speak for what, with the controlling contract.
5. [`docs/DAILY_PIPELINE.md`](docs/DAILY_PIPELINE.md) — what runs Daily, in order.
6. [`docs/ROADMAP_CURRENT.md`](docs/ROADMAP_CURRENT.md) — NOW / NEXT EVIDENCE GATE / AFTER / LATER.
7. Only the specific contract, code and tests the task names (`docs/*_contract.md`, relevant modules).

`docs/STATE.md` (~920 KB), `docs/DECISIONS.md` (~1 MB) and `docs/ROADMAP.md` (~300 KB) are **preserved
history and deep-reference sources, not mandatory full reads and not the default current-state source**.
Search them with `git grep` when a task needs the history of one thing; see
[`docs/HISTORICAL_INDEX.md`](docs/HISTORICAL_INDEX.md). A task that changes authority, history-sensitive
semantics or a machine-parsed file may read the relevant historical sections in full. Do not ignore them
entirely, and never edit them without checking the consumers listed in the index.
`docs/ROADMAP_STATE.json` (~540 KB) is machine state: query it with `python tools/stocklookup_roadmap.py`
rather than reading it whole.

**Authority by domain** (one rule, no ladder and no new authority layer; identical in `docs/ACTIVE_STATE.md`):
- *Milestone execution state* (current / queued / blocked / startable, checkpoint verification):
  `docs/ROADMAP_STATE.json`, queried with `python tools/stocklookup_roadmap.py` (AI_RULES rule 11).
- *Capability semantics and authority limits*: the controlling contract (`docs/*_contract.md`, cited in
  `AUTHORITY.md`) and the code and tests that implement it.
- *Compact current-state docs* (`ACTIVE_STATE`, `CAPABILITIES`, `AUTHORITY`, `DAILY_PIPELINE`,
  `ROADMAP_CURRENT`): maintained navigation views of the two items above. They add **no** authority; if one
  disagrees with the first two, the first two govern and the view is corrected in the same change.
- *Preserved `STATE.md` / `ROADMAP.md` / `DECISIONS.md`*: history, rationale and recorded invariants; not the
  default current-state source. A compact view never overrides a recorded invariant: surface the conflict
  and obtain an explicit owner decision.

| Question | Read |
|---|---|
| What is active? | `ACTIVE_STATE.md` + `CAPABILITIES.md` |
| What is authoritative? | `AUTHORITY.md` + the controlling contract it cites |
| What runs Daily? | `DAILY_PIPELINE.md` |
| What happens next? | `ROADMAP_CURRENT.md` |
| What happened historically? | `HISTORICAL_INDEX.md` → legacy STATE / ROADMAP / DECISIONS / `docs/internal/` |

Chat memory, prior conversation and an agent's own recollection are **never** project authority; if a
prompt conflicts with the rule above or the sources it names, surface the conflict and ask for an explicit
owner override. When you change current state, update `ACTIVE_STATE.md` (and the capability/pipeline files
if they change) in the same change.

## Current direction

Core analytical product completion remains the priority. The native roadmap supplies
current/queued state; completed programs are not reopened and queued work never starts
without Owner authorization. Historical completions and supersessions are preserved in
[the original direction section](docs/archive/agent_bootstrap_context_20261014.md), outside ordinary bootstrap.

The architecture remains market universe → immutable raw lake → canonical/semantic/PIT →
feature-level measurements and eligibility → strategy policy → portfolio/risk → AI research
and human decision. Feature engines own measurements; strategy owns thresholds and policy.
See [the product feature spec](docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md).

Current Research is separate from Audit/PIT/Exact Mode. Missing audit authority blocks the
dependent exact use. Research proxies retain method, provenance, fitness and limitations;
never infer currency/scale, compatible units, PIT or execution authority. Peer methods/scopes
must be comparable; technical structure is deterministic inference, not institutional-flow proof.
Do not open specialist micro-milestones unless they directly block the core analytical product.

Capability-first acquisition, preserved raw evidence, and use-scoped qualification remain
binding. Provider parity is optional; retain existing evidence and route each capability to
sources that actually expose it. The doctrine below governs; no universal scoring system
or independent authority layer is introduced.

## Stable project doctrine

[`docs/DATA_FIRST_DOCTRINE.md`](docs/DATA_FIRST_DOCTRINE.md) is the stable owner doctrine for
Stock Lookup. It defines the non-negotiable direction:

`ACQUIRE BROADLY → PRESERVE RAW → EXTRACT → UNDERSTAND → CANONICALIZE → LABEL FITNESS FOR USE → DETERMINISTIC ANALYSIS → AI RESEARCH → HUMAN DECISION`.

`docs/STATE.md`, `docs/ROADMAP.md` and `docs/DECISIONS.md` are the preserved narrative (recorded
invariants, sequencing history and implementation rationale); current operational state is read through the
Reading contract and its **Authority by domain** rule above. None of them, and no compact current-state doc,
may silently redefine the doctrine. If current operational state appears to conflict with the doctrine, surface the conflict
instead of following the most recent technical thread by inertia.

The doctrine also establishes capability-first source routing: DNSE/Livespeed is the primary
market-data direction, FHSC may supply complementary capabilities, and overlapping DNSE/FHSC
claims should be used for cross-validation rather than artificial provider-parity requirements.
Approved agents may use bounded online discovery/extraction when the task permits it, but retained
source evidence—not AI-generated text—is factual authority.

## Default lightweight bootstrap

For a normal bounded implementation milestone:

1. Run `python tools/stocklookup_roadmap.py --check --json`; when an Owner-designated coordinator exists, pass its exact `--state-file` and your `--repo`. Copied state grants no lane admission. `GIT_NOT_CHECKED` is not a live Git pass.
2. Read the authority section of this file. Open only the compact file the task table names.
   Read [`docs/DATA_FIRST_DOCTRINE.md`](docs/DATA_FIRST_DOCTRINE.md) when the task touches evidence or authority.
3. Open `STATE.md`, `DECISIONS.md`, or `ROADMAP.md` only for a heading the JSON or the task names.
   `python tools/handoff.py` skips those files; `--historical` reads them.
4. Do **not** read `STATE.md`, `DECISIONS.md` or `ROADMAP.md` in full, and do not scan all handoffs, all
   decisions, or the full roadmap, by default.

Perform a full authority refresh (the active set **plus** the relevant historical sections of `STATE.md`,
`ROADMAP.md`, `DECISIONS.md`, `AI_RULES.md` and the current handoff) only when changing architecture, program
priority, governance, or authority; entering a new major program; promoting/demoting a source or
capability; resolving a conflict with/staleness in the active set; finding contradictory repository
docs; or when the owner explicitly requests a rebaseline/governance audit. A new session, a new
agent, or a normal bounded milestone is not by itself a trigger.

Operations reviews, handoffs, historical roadmaps and Consumer/Dashboard notes are evidence/reference,
not competing current authority.

## Owner-only Daily launch

- Only the Owner starts Daily, by clicking the Desktop `Stock Lookup Daily.cmd` after freeing resources
  (closing apps or rebooting). Agents never launch Daily, simulate an Owner launch, or trigger it via a
  wrapper, scheduler, test harness or recovery command.
- Chrome and AI agents run during development, so RAM/commit headroom below Daily host-preflight
  thresholds is normal: not a Producer defect, not a blocker to offline work, no reason to ask the
  Owner to close apps or reboot.
- Never lower memory thresholds, change pagefile policy or add an alternative launcher. Daily readiness
  is evaluated only when the Owner starts it.

## AI context hygiene

- **No recursive `operations-review/` scan** by default; read **exact evidence paths only** when required.
- **Source placement:** implementation in `stocklookup_core/`, reusable tools in `tools/`; no root helpers. CI enforces `config/repository_layout.json`; root exceptions need a reviewed compatibility reason.
- **Temporary helpers:** outside repo or in `.stocklookup/scratch/`.
- **Single production entrypoint:** `stocklookup.ps1 daily` remains the only owner entrypoint.
- **No blanket scans:** use [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) rather than scanning all handoffs/decisions/tests.
- **Edit over proliferate:** edit an existing capability module unless a distinct contract boundary exists.

## Repository boundaries

### First-party source-route qualification

Classify each source surface by role (universe enumeration, lookup, issuer detail, disclosure index, event calendar, attachment, bulk download) before concluding. Inspect bounded adjacent first-party surfaces before closing a source family. Retain supported raw observations with route provenance, then resolve/promote each use-case authority fail-closed; search/autocomplete is never universe-enumeration evidence. Upstream parent metadata proves provenance only via exact linkage. Closures name sibling surfaces checked and reopening evidence.

Codex is the executor. Producer owns raw-source contracts, canonicalization, and artifact authority. For cross-repo tasks, read the sibling guardrail and Producer active set (`docs/ACTIVE_STATE.md` + named contract); never reconstruct truth from chat memory or old handoffs.

- Work only inside this repo unless explicitly given another workspace; use `STOCK_LOOKUP_RUNTIME_ROOT` (never hard-code runtime paths).
- Keep repo docs portable (relative links only); machine-specific steps go in local operator docs.
- Never edit databases, generated artifacts, backups, credentials, or deploy outputs unless requested.
- Preserve raw observations/provenance when semantics are unknown; mark `UNKNOWN` and fail closed only where required.
- No new market-data provider without owner decision (DNSE/Livespeed primary; EODHD rejected); no auto-starting later milestones without Owner authorization.
- Internal records: [`docs/internal/`](docs/internal/); decision archives: [`docs/archive/decisions/`](docs/archive/decisions/).
