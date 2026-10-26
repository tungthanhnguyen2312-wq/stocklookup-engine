"""Immutable corporate-action event ledger built from official document observations.

WHAT THIS IS
    The reconciliation layer of pillar B: many documents, one event. It links the typed
    observations produced by `corporate_action_events.py` into deduplicated ledger entries,
    resolves each entry's lifecycle state, records amendments and supersessions without
    editing anything, and derives a price-adjustment factor **only** where the evidence
    directly supports one.

    It is separate from the existing `corporate_action_ledger.py`, which is the qualified
    per-ticker MVP over `semantic_evidence_bridge`. That module keeps its contract and its
    callers; this one is the official-document path the pillar-B design specifies.

HOW DOCUMENTS ARE LINKED INTO ONE EVENT
    Two observations describe the same event when they agree on the issuer, the event type,
    and the **share-change identity** -- the number of shares issued -- which is the field
    Vietnamese notices state most consistently and most precisely. Dates are deliberately not
    part of the link key: the whole point of linking is that an issuer disclosure, an exchange
    notice and a depository notice carry *different* dates for one event.

    Where two observations of one event both state a field, they must agree. A disagreement
    is recorded as a conflict on the entry and blocks promotion, rather than being resolved
    by preferring a source.

CROSS-DOCUMENT CORROBORATION IS REAL EVIDENCE
    In the bounded slice, the issuer notice yields `shares_before` and `shares_issued`, and
    the exchange notice yields `shares_issued` and `shares_after`. Neither document alone
    states all three, and the scanned issuer notice's own `shares_after` is OCR-damaged. The
    ledger checks `before + issued == after` **across the two documents** and records the
    result as an arithmetic corroboration with both hashes cited. That is stronger evidence
    than either document alone, and it is what promotes the entry's ratio to qualified.

WHY MOST ENTRIES STILL PRODUCE NO ADJUSTMENT FACTOR
    A price-adjustment factor places a corporate action on the price timeline, which requires
    an **explicit official ex-date**. `docs/DECISIONS.md` already fixes that a record date
    never substitutes for one. Neither retained HPG document states an ex-date, so the slice's
    event is a complete, executed, fully-cited ledger entry with `adjustment_factor_status =
    not_ready` and a named missing field. This is the fail-closed case the milestone asks the
    slice to demonstrate, and it is the correct outcome, not a shortfall.

    Factors derived here are explicitly outside production authority: `authority_state` is
    `outside_production_authority` on every one, and nothing in this module writes to
    `data/official-evidence/`, which `evidence_promotion.py` alone may do.

DETERMINISTIC REPLAY
    The same retained documents always produce the same ledger: entries are keyed by content
    hashes, ordered by a total ordering with an `event_key` tiebreaker, and no field depends
    on the clock or on iteration order. `replay_fingerprint` is the value that claim is made
    about.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

VERSION = "1.0.0"
LEDGER_SCHEMA_VERSION = "1.0.0"
ADJUSTMENT_POLICY_VERSION = "1.0.0"

ADJUSTMENT_AUTHORITY = "official_corporate_action_ledger"
AUTHORITY_STATE = "outside_production_authority"

FACTOR_READY = "ready"
FACTOR_NOT_READY = "not_ready"
FACTOR_NOT_APPLICABLE = "not_applicable"

#: Event types whose execution mechanically changes the share count and therefore the price.
_DILUTIVE = frozenset({"stock_dividend", "bonus_shares", "stock_split"})
_CONCENTRATING = frozenset({"reverse_split"})

_LIFECYCLE_RANK = {
    "unknown": 0, "proposed": 1, "approved": 2, "announced": 3,
    "record_date_confirmed": 4, "executed": 5,
}

#: Fields that must agree wherever two observations of one event both state them.
_AGREEMENT_FIELDS = (
    "shares_before", "shares_after", "shares_issued", "ex_date", "record_date",
    "payment_or_execution_date", "cash_amount_per_share", "subscription_price",
    "shares_planned", "shares_outstanding_before", "treasury_shares_before",
    "rights_ratio", "treasury_shares_after", "issuance_completion_date",
    "unrestricted_shares", "restricted_shares", "unrestricted_trading_date", "restricted_trading_date",
    "combined_shares_issued", "co_issued_shares", "shares_outstanding_after",
)

#: Fields taken from whichever observation states them, once agreement has been checked.
_MERGE_FIELDS = _AGREEMENT_FIELDS + (
    "trading_date", "approval_date", "stock_ratio", "ratio_basis", "rights_ratio",
    "fractional_shares_cancelled",
)

#: Entry fields that only reviewed-scan observations state. They are emitted only when stated,
#: so a ledger built from observations that never carry them replays byte-identically.
_OPTIONAL_ENTRY_FIELDS = ("shares_planned", "shares_outstanding_before", "treasury_shares_before",
                          "fractional_shares_cancelled", "treasury_shares_after", "issuance_completion_date",
                          "unrestricted_shares", "restricted_shares", "unrestricted_trading_date", "restricted_trading_date")
_OPTIONAL_ENTRY_FIELDS += ("combined_shares_issued", "co_issued_shares", "shares_outstanding_after")

#: Must equal `corporate_action_events.RATIO_SOURCE_EXPLICIT`. Kept literal so this module stays
#: free of extractor imports.
_RATIO_SOURCE_EXPLICIT = "explicit_official_entitlement"

#: Event types whose price effect is the share factor alone. Any other leg on the same notice is
#: a separate, unadjusted price effect on the same ex-date.
_SHARE_FACTOR_TYPES = _DILUTIVE | _CONCENTRATING


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def event_key(observation: Mapping[str, Any]) -> tuple[str, str, str]:
    """The identity two documents must share to describe one event."""
    issued = observation.get("shares_issued")
    if issued is None and observation.get("shares_after") is not None \
            and observation.get("shares_before") is not None:
        issued = int(observation["shares_after"]) - int(observation["shares_before"])
    if issued is None and observation.get("shares_planned") is not None:
        # A planned count is an identity of the plan, never of the executed issuance. It links
        # only through a document that states both counts (`_bridge_planned_groups`).
        return (str(observation.get("ticker") or ""), str(observation.get("event_type") or "unknown"),
                f"planned:{int(observation['shares_planned'])}")
    return (
        str(observation.get("ticker") or ""),
        str(observation.get("event_type") or "unknown"),
        str(issued) if issued is not None else "unidentified",
    )


def _bridge_planned_groups(grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]]
                           ) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]]]:
    """Join plan-only observations to the executed event whose own documents state that plan.

    An exchange ex-right notice states the planned issuance ("dự kiến phát hành"); a listing
    change states the executed count, smaller by the cancelled fractions. Neither cites the
    other. An issuer result report states both counts in one document, which is a stated
    identity, not an inference from dates or ratios. A plan group joins exactly one executed
    group whose members state its planned count; zero or several candidates leave it separate.
    """
    bridges: dict[tuple[str, str, str], dict[str, Any]] = {}
    ambiguous: list[dict[str, Any]] = []
    for key in sorted(k for k in grouped if k[2].startswith("planned:")):
        planned = int(key[2].split(":", 1)[1])
        targets = sorted(k for k in grouped if k[:2] == key[:2] and not k[2].startswith("planned:")
                         and any(o.get("shares_planned") is not None and int(o["shares_planned"]) == planned
                                 for o in grouped[k]))
        if len(targets) != 1:
            if targets:
                ambiguous.append({"planned_shares": planned, "candidate_share_changes": [t[2] for t in targets],
                                  "reason": "planned count stated by more than one executed event"})
            continue
        target = targets[0]
        stating = sorted({str(o.get("document_id")) for o in grouped[target]
                          if o.get("shares_planned") is not None and int(o["shares_planned"]) == planned
                          and o.get("shares_issued") is not None})
        if not stating:
            continue
        bridges[target] = {"planned_shares": planned, "bridged_document_ids": sorted(
                               {str(o.get("document_id")) for o in grouped[key]}),
                           "stating_document_ids": stating,
                           "basis": "one document states both the planned and the executed count"}
        grouped[target].extend(grouped.pop(key))
    return bridges, ambiguous


def _co_documented_legs(entry: Mapping[str, Any],
                        observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Other event legs recited by the same retained documents as this entry.

    A notice that fixes one ex-date for a cash dividend and a share issuance is one document
    about two price effects. Linking is unchanged; the entry only records what else its own
    documents state, so a share factor is never read as the whole price effect of that date.
    """
    hashes = set(entry.get("source_content_hashes") or [])
    own = set(entry.get("source_observation_ids") or [])
    legs = [{"event_type": o.get("event_type"), "ex_date": o.get("ex_date"), "record_date": o.get("record_date"),
             "cash_amount_per_share": o.get("cash_amount_per_share"), "payment_date": o.get("payment_date"),
             "observation_id": o.get("observation_id"), "document_id": o.get("document_id")}
            for o in observations
            if str(o.get("content_sha256")) in hashes and str(o.get("observation_id")) not in own
            and o.get("event_type") != entry.get("event_type")]
    return sorted(legs, key=lambda leg: (str(leg["event_type"]), str(leg["observation_id"])))


def _composite_execution_anchor(members, observations):
    """A directly reported component total may match one executed aggregate listing.

    Do not attach the aggregate quantity as this leg's issued quantity. The
    issuer report must state its own leg, companion, total, before and after.
    Only the exchange listing anchor supplies executed lifecycle authority.
    """
    anchors = {}
    for report in members:
        required = ("shares_before", "shares_issued", "co_issued_shares", "combined_shares_issued", "shares_after")
        if (report.get("document_type") != "corporate_action_notice"
                or report.get("source_authority") not in {"issuer_ir", "exchange"}
                or any(not isinstance(report.get(k), int) or isinstance(report.get(k), bool)
                       or report[k] <= 0 for k in required)):
            continue
        before, own, companion, total, after = (report[k] for k in required)
        if own + companion != total or before + total != after:
            continue
        for anchor in observations:
            if (anchor.get("ticker") == report.get("ticker") and anchor.get("event_type") is None
                    and anchor.get("document_type") == "listing_change_notice"
                    and anchor.get("source_authority") == "exchange"
                    and len(str(anchor.get("content_sha256") or "")) == 64
                    and anchor.get("lifecycle_state") == "executed"
                    and anchor.get("shares_issued") == total and anchor.get("shares_after") == after):
                anchors[str(anchor["observation_id"])] = anchor
    return next(iter(anchors.values())) if len(anchors) == 1 else None


def build_ledger(observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Link, deduplicate and reconcile observations into an immutable event ledger."""
    deduplicated: dict[str, Mapping[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for observation in observations:
        identifier = str(observation.get("observation_id"))
        if identifier in deduplicated:
            duplicates.append({"observation_id": identifier,
                               "document_id": observation.get("document_id"),
                               "reason": "identical observation identity already linked"})
            continue
        deduplicated[identifier] = observation

    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    unlinked: list[dict[str, Any]] = []
    for observation in deduplicated.values():
        key = event_key(observation)
        if key[1] == "unknown" or key[2] == "unidentified":
            unlinked.append({
                "observation_id": observation.get("observation_id"),
                "document_id": observation.get("document_id"),
                "reason": ("no event type detected" if key[1] == "unknown"
                           else "no share-change identity; cannot be linked to an event"),
            })
            continue
        grouped.setdefault(key, []).append(observation)

    bridges, ambiguous_plans = _bridge_planned_groups(grouped)
    entries = [_reconcile(key, members, bridge=bridges.get(key),
                          composite_anchor=_composite_execution_anchor(members, deduplicated.values()))
               for key, members in sorted(grouped.items())]
    for entry in entries:
        legs = _co_documented_legs(entry, deduplicated.values())
        if legs:
            entry["co_documented_legs"] = legs
    entries.sort(key=_ordering_key)

    superseded = _apply_supersession(entries)

    replay = _fingerprint({
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": [{key: entry[key] for key in sorted(entry)
                     if key not in {"source_documents"}} for entry in entries],
    })
    result = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_version": VERSION,
        "adjustment_policy_version": ADJUSTMENT_POLICY_VERSION,
        "adjustment_authority": ADJUSTMENT_AUTHORITY,
        "authority_state": AUTHORITY_STATE,
        "entries": entries,
        "entry_count": len(entries),
        "duplicate_observations": duplicates,
        "unlinked_observations": unlinked,
        "superseded_entry_ids": superseded,
        "replay_fingerprint": replay,
        "qualified_event_count": sum(1 for entry in entries
                                     if entry["qualification_state"] == "qualified"),
        "adjustment_factor_counts": _tally(entries, "adjustment_factor_status"),
        "lifecycle_counts": _tally(entries, "lifecycle_state"),
    }
    if ambiguous_plans:
        result["ambiguous_planned_count_bridges"] = ambiguous_plans
    return result


def _tally(entries: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        value = str(entry.get(field))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _ordering_key(entry: Mapping[str, Any]) -> tuple:
    far = "9999-99-99"
    return (
        str(entry.get("ticker") or ""),
        str(entry.get("payment_or_execution_date") or far),
        str(entry.get("record_date") or far),
        str(entry.get("ex_date") or far),
        str(entry.get("announcement_date") or far),
        str(entry.get("event_id") or ""),
    )


def _reconcile(key: tuple[str, str, str],
               members: Sequence[Mapping[str, Any]], *,
               bridge: Mapping[str, Any] | None = None,
               composite_anchor: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One ledger entry from every observation that describes one event."""
    ticker, event_type, issued_key = key
    ordered = sorted(members, key=lambda item: (str(item.get("content_sha256") or ""),
                                                str(item.get("observation_id") or "")))

    merged: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    entry_warnings: set[str] = set()
    # A directly stated entitlement rate ("Tỷ lệ thực hiện") is the factor operand. A ratio
    # derived from share counts is not: it absorbs cancelled fractions and, with treasury
    # shares, divides by shares that receive nothing. Stated rates must agree with each other.
    explicit = [(observation, observation["stock_ratio"]) for observation in ordered
                if observation.get("ratio_source") == _RATIO_SOURCE_EXPLICIT
                and observation.get("stock_ratio") is not None]
    if explicit:
        if len({_comparable(value) for _, value in explicit}) > 1:
            conflicts.append({"field": "stock_ratio", "values": [
                {"value": value, "document_id": observation.get("document_id"),
                 "content_sha256": observation.get("content_sha256")} for observation, value in explicit]})
        else:
            merged["stock_ratio"], merged["ratio_basis"] = explicit[0][1], explicit[0][0].get("ratio_basis")
        if any(observation.get("stock_ratio") is not None and observation.get("ratio_source") != _RATIO_SOURCE_EXPLICIT
               for observation in ordered):
            entry_warnings.add("count_derived_stock_ratio_superseded_by_explicit_entitlement")
    for field in _MERGE_FIELDS:
        if explicit and field in {"stock_ratio", "ratio_basis"}:
            continue
        stated = [(observation, observation.get(field)) for observation in ordered
                  if observation.get(field) is not None]
        if not stated:
            continue
        values = {_comparable(value) for _, value in stated}
        if field in _AGREEMENT_FIELDS and len(values) > 1:
            conflicts.append({
                "field": field,
                "values": [
                    {"value": value, "document_id": observation.get("document_id"),
                     "content_sha256": observation.get("content_sha256")}
                    for observation, value in stated
                ],
            })
            continue
        merged[field] = stated[0][1]

    ratio_refusal = None
    if not explicit and merged.get("stock_ratio") is not None and merged.get("treasury_shares_before"):
        # Treasury shares receive no entitlement, so issued/before over a total that includes
        # them is not the per-share entitlement rate. Refuse it rather than adjust prices by it.
        merged.pop("stock_ratio")
        merged.pop("ratio_basis", None)
        ratio_refusal = "stock_ratio_denominator_includes_treasury_shares"

    source_members = ordered + ([composite_anchor] if composite_anchor is not None else [])
    corroboration = _corroborate(merged, source_members)
    ratio_basis_check = _ratio_basis_corroboration(merged)
    lifecycle = max((str(observation.get("lifecycle_state") or "unknown")
                     for observation in source_members),
                    key=lambda state: _LIFECYCLE_RANK.get(state, 0))

    identity = {"ticker": ticker, "event_type": event_type, "share_change": issued_key,
                "schema_version": LEDGER_SCHEMA_VERSION}
    entry_id = _fingerprint(identity)

    warnings = sorted({warning for observation in ordered
                       for warning in observation.get("warnings") or []})
    absent = {}
    for observation in ordered:
        for field, reason in (observation.get("absent_fields") or {}).items():
            if merged.get(field) is None:
                absent.setdefault(field, reason)

    qualification, qualification_reason = _qualify(merged, conflicts, corroboration, lifecycle,
                                                   ratio_basis_check)
    factor = _adjustment_factor(event_type, merged, qualification, ratio_refusal=ratio_refusal)
    optional: dict[str, Any] = {field: merged[field] for field in _OPTIONAL_ENTRY_FIELDS
                                if merged.get(field) is not None}
    if ratio_basis_check is not None:
        optional["ratio_basis_corroboration"] = ratio_basis_check
    if bridge is not None:
        optional["planned_count_bridge"] = dict(bridge)
    if composite_anchor is not None:
        optional["composite_execution_anchor"] = {
            "document_id": composite_anchor["document_id"], "content_sha256": composite_anchor["content_sha256"],
            "observation_id": composite_anchor["observation_id"],
            "basis": "reported_component_plus_companion_equals_reported_total_and_executed_aggregate_listing"}
    if explicit:
        optional["ratio_source"] = _RATIO_SOURCE_EXPLICIT
    if ratio_refusal:
        entry_warnings.add(ratio_refusal)
    if entry_warnings:
        warnings = sorted(set(warnings) | entry_warnings)

    return {
        **optional,
        "event_id": entry_id,
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_version": VERSION,
        "ticker": ticker,
        "event_type": event_type,
        "lifecycle_state": lifecycle,
        "execution_status": lifecycle,
        "approval_date": merged.get("approval_date"),
        "announcement_date": min(
            (str(observation.get("announcement_date")) for observation in ordered
             if observation.get("announcement_date")), default=None),
        "ex_date": merged.get("ex_date"),
        "record_date": merged.get("record_date"),
        "payment_or_execution_date": merged.get("payment_or_execution_date"),
        "trading_date": merged.get("trading_date"),
        "shares_before": merged.get("shares_before"),
        "shares_issued": merged.get("shares_issued"),
        "shares_after": merged.get("shares_after"),
        "share_count_identity": _count_identity(ordered, 'share_count_identity') or 'unknown',
        "share_class": _count_identity(ordered, 'share_class'),
        "cash_amount_per_share": merged.get("cash_amount_per_share"),
        "stock_ratio": merged.get("stock_ratio"),
        "ratio_basis": merged.get("ratio_basis"),
        "rights_ratio": merged.get("rights_ratio"),
        "subscription_price": merged.get("subscription_price"),
        "source_document_ids": sorted({str(observation.get("document_id"))
                                       for observation in source_members}),
        "source_content_hashes": sorted({str(observation.get("content_sha256"))
                                         for observation in source_members}),
        "source_observation_ids": sorted({str(observation.get("observation_id"))
                                          for observation in source_members}),
        "source_documents": [
            {"document_id": observation.get("document_id"),
             "document_type": observation.get("document_type"),
             "source_authority": observation.get("source_authority"),
             "source_url": observation.get("source_url"),
             "content_sha256": observation.get("content_sha256"),
             "share_count_identity": observation.get('share_count_identity'),
             "share_class": observation.get('share_class'),
             "citations": observation.get("citations") or []}
            for observation in source_members
        ],
        "arithmetic_corroboration": corroboration,
        "conflicts": conflicts,
        "conflict_status": "conflicted" if conflicts else "consistent",
        "absent_fields": dict(sorted(absent.items())),
        "warnings": warnings,
        "qualification_state": qualification,
        "qualification_reason": qualification_reason,
        "superseded_by": None,
        "supersedes": None,
        **factor,
    }


def _comparable(value: Any) -> Any:
    return round(float(value), 6) if isinstance(value, (int, float)) else str(value)


def _count_identity(observations: Sequence[Mapping[str, Any]], field: str) -> str | None:
    """Preserve only unanimous explicit semantics of documents stating shares_after."""
    values = {str(o[field]) for o in observations if o.get('shares_after') is not None
              and o.get(field) not in (None, '', 'unknown')}
    return next(iter(values)) if len(values) == 1 else None


def _corroborate(merged: Mapping[str, Any],
                 members: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`shares_before + shares_issued == shares_after`, across whichever documents state them."""
    before, issued, after = (merged.get("shares_before"), merged.get("shares_issued"),
                             merged.get("shares_after"))
    total, companion = merged.get("combined_shares_issued"), merged.get("co_issued_shares")
    if total is not None or companion is not None:
        if any(value is None for value in (before, issued, after, total, companion)):
            return {"state": "not_testable", "reason": "composite issuance needs stated component, companion, total, before and after", "documents": []}
        holds = int(issued) + int(companion) == int(total) and int(before) + int(total) == int(after)
        contributors = sorted({str(o.get("content_sha256")) for o in members})
        return {"state": "confirmed" if holds else "violated",
                "reason": f"component {issued} + companion {companion} = total {total}; {before} + {total} = {after}",
                "documents": contributors, "cross_document": len(contributors) > 1,
                "basis": "REPORTED_COMPOSITE_ISSUANCE_NOT_INDIVIDUAL_LEG_TOTAL"}
    if None in (before, issued, after):
        present = [name for name, value in (("shares_before", before),
                                            ("shares_issued", issued),
                                            ("shares_after", after)) if value is not None]
        return {"state": "not_testable",
                "reason": (f"only {', '.join(present) or 'no share count'} is stated; the "
                           "identity needs all three"),
                "documents": []}
    holds = int(before) + int(issued) == int(after)
    contributors = sorted({
        str(observation.get("content_sha256"))
        for observation in members
        if any(observation.get(field) is not None
               for field in ("shares_before", "shares_issued", "shares_after"))
    })
    return {
        "state": "confirmed" if holds else "violated",
        "reason": (f"{before} + {issued} "
                   f"{'=' if holds else '!='} {after}"),
        "documents": contributors,
        "cross_document": len(contributors) > 1,
    }


def _ratio_basis_corroboration(merged: Mapping[str, Any]) -> dict[str, Any] | None:
    """`stock_ratio x entitled shares` against the stated planned count, when all are stated.

    Entitled shares are the outstanding shares before the issuance -- stated directly, or the
    issued total less stated treasury shares. The planned count is that product rounded to a
    whole share, so agreement within one share proves the denominator the rate applies to; a
    larger gap means the rate, the plan or the treasury basis is misread.
    """
    ratio, planned = merged.get("stock_ratio"), merged.get("shares_planned")
    entitled = merged.get("shares_outstanding_before")
    if entitled is None and merged.get("shares_before") is not None and merged.get("treasury_shares_before") is not None:
        entitled = int(merged["shares_before"]) - int(merged["treasury_shares_before"])
    if ratio is None or planned is None or entitled is None:
        return None
    product = Decimal(str(ratio)) * int(entitled)
    holds = abs(product - int(planned)) < 1
    return {"state": "confirmed" if holds else "violated",
            "reason": f"{ratio} x {entitled} = {product} {'~' if holds else '!='} planned {planned}",
            "entitled_shares": int(entitled)}


def _qualify(merged: Mapping[str, Any], conflicts: Sequence[Mapping[str, Any]],
             corroboration: Mapping[str, Any], lifecycle: str,
             ratio_basis_check: Mapping[str, Any] | None = None) -> tuple[str, str]:
    if conflicts:
        return "conflicted", ("documents disagree on: "
                              + ", ".join(sorted(str(item["field"]) for item in conflicts)))
    if corroboration["state"] == "violated":
        return "conflicted", f"share-count identity does not hold ({corroboration['reason']})"
    if ratio_basis_check is not None and ratio_basis_check["state"] == "violated":
        return "conflicted", f"entitlement ratio does not reproduce the planned count ({ratio_basis_check['reason']})"
    if _LIFECYCLE_RANK.get(lifecycle, 0) < _LIFECYCLE_RANK["executed"]:
        return "provisional", (f"lifecycle is {lifecycle!r}; only an executed event is a "
                               "qualified historical fact")
    # A `not_testable` identity is an absent third number, not a disagreement. It withholds
    # corroboration, which the entry records, but it does not impeach an executed event that
    # an exchange notice states completely. Only a `violated` identity does, and that is
    # handled above.
    if corroboration["state"] == "confirmed":
        return "qualified", ("executed, internally consistent, and the share-count identity is "
                             "confirmed"
                             + (" across independent documents"
                                if corroboration.get("cross_document") else ""))
    return "qualified", ("executed and internally consistent; the share-count identity is not "
                         f"testable from the retained documents ({corroboration['reason']})")


def _adjustment_factor(event_type: str, merged: Mapping[str, Any],
                       qualification: str, *, ratio_refusal: str | None = None) -> dict[str, Any]:
    """A factor only where the evidence directly supports placing the event on the timeline."""
    base = {
        "adjustment_authority": ADJUSTMENT_AUTHORITY,
        "adjustment_policy_version": ADJUSTMENT_POLICY_VERSION,
        "authority_state": AUTHORITY_STATE,
        "adjustment_factor": None,
        "adjustment_factor_status": FACTOR_NOT_READY,
        "adjustment_factor_reason": "",
        "adjustment_factor_blocked_by": [],
    }
    if event_type not in _DILUTIVE | _CONCENTRATING:
        if event_type == "rights_issue":
            return {**base, "adjustment_factor_status": FACTOR_NOT_APPLICABLE,
                    "adjustment_factor_reason": "UNSUPPORTED_FACTOR_TYPE: rights require a qualified subscription/reference-price factor policy",
                    "adjustment_factor_blocked_by": ["UNSUPPORTED_FACTOR_TYPE"]}
        return {**base, "adjustment_factor_status": FACTOR_NOT_APPLICABLE,
                "adjustment_factor_reason": (
                    f"{event_type} does not mechanically rescale the share count; a factor "
                    "for it needs a cash amount and a reference price, which this ledger "
                    "does not hold")}

    blocked: list[str] = []
    if qualification != "qualified":
        blocked.append(f"event_qualification:{qualification}")
    if not merged.get("ex_date"):
        blocked.append("missing_explicit_official_ex_date")
    ratio = merged.get("stock_ratio")
    if ratio is None:
        blocked.append(ratio_refusal or "missing_stock_ratio")

    if blocked:
        return {**base, "adjustment_factor_blocked_by": sorted(blocked),
                "adjustment_factor_reason": (
                    "a price-adjustment factor places the event on the price timeline and "
                    "needs an explicit official ex-date; a record, payment or listing date is "
                    "never substituted for one")}

    factor = round(1.0 / (1.0 + float(ratio)), 12)
    return {**base, "adjustment_factor": factor, "adjustment_factor_status": FACTOR_READY,
            "adjustment_factor_reason": (
                f"1 / (1 + {ratio}) applied to closes strictly before the ex-date "
                f"{merged.get('ex_date')}; derived for a directly supported event and held "
                "outside production authority")}


def _apply_supersession(entries: Sequence[dict[str, Any]]) -> list[str]:
    """Link amendments and cancellations to what they replace. Nothing is edited in place.

    A `cancellation` or `amendment` entry supersedes the most recent earlier entry for the
    same issuer whose share-change identity it repeats. The superseded entry keeps every
    field it had and gains only a `superseded_by` pointer, so the ledger stays append-only.
    """
    superseded: list[str] = []
    for index, entry in enumerate(entries):
        if entry["event_type"] not in {"cancellation", "amendment"}:
            continue
        for candidate in reversed(entries[:index]):
            if candidate["ticker"] != entry["ticker"]:
                continue
            if candidate["shares_issued"] != entry["shares_issued"]:
                continue
            if candidate["superseded_by"] is not None:
                continue
            candidate["superseded_by"] = entry["event_id"]
            candidate["lifecycle_state"] = (
                "cancelled" if entry["event_type"] == "cancellation" else "amended")
            candidate["execution_status"] = candidate["lifecycle_state"]
            entry["supersedes"] = candidate["event_id"]
            superseded.append(candidate["event_id"])
            break
    return sorted(superseded)
