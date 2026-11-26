"""Focused checks for the bounded nine-host owner promotion."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from official_source_registry import ADMITTED, REASON_HOST_NOT_ALLOWED, admit, load_registry
from stocklookup_core.evidence.official_source_registry_owner_promotion import OWNER_APPROVED_HOSTS, build_artifact


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "official_source_registry.json"


def _issuer_source() -> dict:
    registry = load_registry(REGISTRY_PATH)
    return next(source for source in registry["sources"] if source["source_id"] == "issuer_ir")


def test_only_the_nine_owner_approved_hosts_were_added() -> None:
    previous = json.loads(
        subprocess.check_output(
            ["git", "show", "de1e5b5f47ae77aaa8db01cf7061c9da87f2046b:config/official_source_registry.json"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
    )
    before = next(source for source in previous["sources"] if source["source_id"] == "issuer_ir")
    # The promotion is judged on the registry it produced (the exact, hash-verified VSDC-flag
    # successor 2645eac7). The later reviewed issuer-coverage amendment is verified separately
    # and may only add hosts on top of it.
    from tools import verify_retention_reader_transition as vrt
    archive = (ROOT / vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    promoted_bytes = archive[:2] + vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_LINE + archive[2:]
    assert hashlib.sha256(promoted_bytes).hexdigest() == "2645eac76e3c99533a131c622a473d98cd895f536518aeab4f98f10bee441ed4"
    current = REGISTRY_PATH.read_bytes().replace(b"\r\n", b"\n")
    assert vrt._official_source_registry_reviewed_amendment_bytes(ROOT, current) == current
    promoted = next(source for source in json.loads(promoted_bytes)["sources"] if source["source_id"] == "issuer_ir")
    added = set(promoted["allowed_hosts"]) - set(before["allowed_hosts"])
    assert added == set(OWNER_APPROVED_HOSTS.values())
    assert set(promoted["allowed_hosts"]) <= set(_issuer_source()["allowed_hosts"])


def test_activation_replay_is_exactly_nine_sha_bound_and_deterministic() -> None:
    before = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    first = build_artifact()
    second = build_artifact()
    assert first == second
    assert hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest() == before
    assert first["summary_counts"] == {
        "authorized_routes": 9,
        "ownership_qualified_routes": 9,
        "ownership_evidence_missing_routes": 0,
    }
    assert {row["ticker"] for row in first["activated_route_replay"]} == set(OWNER_APPROVED_HOSTS)
    assert all(row["evidence_integrity_valid"] for row in first["activated_route_replay"])
    assert all(row["route_approval_eligible"] for row in first["activated_route_replay"])
    assert all(row["evidence_provenance"]["source_artifact_identity"] for row in first["activated_route_replay"])


def test_bid_final_host_and_aat_conflict_boundary_are_preserved() -> None:
    artifact = build_artifact()
    rows = {row["ticker"]: row for row in artifact["activated_route_replay"]}
    bid = rows["BID"]
    assert bid["owner_approved_host"] == bid["candidate_host"] == "bidv.com.vn"
    assert bid["evidence_provenance"]["requested_url"] == "https://www.bidv.com.vn/vn/quan-he-nha-dau-tu"
    assert bid["evidence_provenance"]["final_url"] == "https://bidv.com.vn/vn/quan-he-nha-dau-tu"
    assert bid["evidence_provenance"]["redirect_authority_verdict"] == "SAFE_SAME_AUTHORITY_REDIRECT"
    assert rows["AAT"]["owner_approved_host"] == "tiensonaus.com"
    assert artifact["owner_authorization"]["excluded_hosts"] == ["aquatexbentre.com", "tienson.vn"]


def test_registry_admission_is_limited_to_activated_hosts() -> None:
    registry = load_registry(REGISTRY_PATH)
    for host in OWNER_APPROVED_HOSTS.values():
        result = admit("issuer_ir", f"https://{host}/document", "annual_report", registry=registry)
        assert result["decision"] == ADMITTED
    for host in ("www.bidv.com.vn", "tienson.vn", "aquatexbentre.com"):
        result = admit("issuer_ir", f"https://{host}/document", "annual_report", registry=registry)
        assert result["reason"] == REASON_HOST_NOT_ALLOWED
