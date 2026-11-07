"""Closed-world route discovery: candidate evidence is never source approval.

Before a new official-financial-source acquisition, check retained Stock Lookup
evidence, then any Inbox report already identified for the same issuer, period,
and topic. Reuse the exact URL, source identity, hash, and unresolved questions
as locators. Re-read bytes on an authorized route when the product needs them.
OCR or new extraction only for pages that are not already qualified, then pass
evidenced observations through the existing qualification pipeline. This module
does not scan the Hub, does not put the Hub on the Daily path, and does not
treat a Grokbot DONE label as Product Verified.
"""
from __future__ import annotations
import hashlib, json
from collections import Counter
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"
def _hash(x: Any) -> str: return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def prior_inbox_research_lead(*, issue: int, reported_sha256: str, byte_sha256: str) -> dict[str, Any]:
    """A Hub report locates a document. Matching bytes do not admit a fact."""
    return {
        "hub_issue": issue,
        "authority": "RESEARCH_ONLY_NOT_PRODUCT_VERIFIED",
        "reported_sha256": reported_sha256,
        "bytes_rechecked": reported_sha256 == byte_sha256,
        "hub_memo_is_fact_authority": False,
        "done_label_is_product_verified": False,
        "periodic_hub_scan": False,
        "daily_critical_path": False,
    }


def discover_routes(cohort: Sequence[Mapping[str, Any]], signals: Mapping[str, Mapping[str, Any]], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Classify every supplied target once, admitting only explicit existing registry hosts."""
    approved_hosts = {host.lower() for source in registry.get("sources", []) if source.get("activation") == "approved" for host in source.get("allowed_hosts", [])}
    rows=[]
    for target in sorted(cohort, key=lambda x: str(x.get("ticker"))):
        ticker=str(target.get("ticker") or "").upper(); signal=dict(signals.get(ticker) or {})
        url=str(signal.get("candidate_url") or ""); host=url.split("/")[2].lower() if url.startswith(("http://","https://")) and len(url.split("/"))>2 else ""
        evidence=signal.get("issuer_domain_evidence")
        if host and evidence and host in approved_hosts:
            state="APPROVABLE_OFFICIAL_ROUTE_DISCOVERED"; blocker=None; recommendation="existing_approved_source_class"
        elif host and evidence:
            state="CANDIDATE_ROUTE_NEEDS_MORE_EVIDENCE"; blocker="HOST_NOT_IN_APPROVED_REGISTRY"; recommendation="no_registry_change_without_owner_authority"
        elif host:
            state="IDENTITY_AMBIGUOUS"; blocker="ISSUER_DOMAIN_OWNERSHIP_EVIDENCE_MISSING"; recommendation="not_approved"
        else:
            state="NO_OFFICIAL_ROUTE_DISCOVERABLE"; blocker="NO_RETAINED_ISSUER_DOMAIN_OR_EXCHANGE_DETAIL_SIGNAL"; recommendation="not_approved"
        rows.append({"canonical_instrument":ticker,"issuer_legal_identity":signal.get("issuer_legal_identity"),"candidate_url":url or None,"candidate_domain":host or None,"source_class":signal.get("source_class"),"discovery_mechanism":signal.get("discovery_mechanism","retained_closed_world_signal_inventory"),"issuer_domain_evidence":evidence,"observed_at":signal.get("observed_at"),"provenance":signal.get("provenance",[]),"authority_recommendation":recommendation,"disposition":state,"blockers":[blocker] if blocker else []})
    return {"schema_version":VERSION,"route_candidates":rows,"disposition_counts":dict(sorted(Counter(x["disposition"] for x in rows).items())),"identity":_hash(rows)}
