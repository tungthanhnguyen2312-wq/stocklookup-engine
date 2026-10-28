"""Cheap Producer-seal Consumer binding. No acquisition, IID, or Producer."""
import json
import os
from pathlib import Path

import pytest

import tests.preseal_consumer_dependency as dependency

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != "nt" or not dependency.PROFILE.exists(), reason="Owner-host genuine Consumer acceptance; fixture refusal remains hermetic")
def test_production_seal_path_keeps_the_sibling_expression():
    dependency.seal_sources_present(ROOT)
    qualified = dependency.qualify_consumer()
    dependency.production_sibling_matches(qualified)
    assert qualified["branch"] == "main"
    assert qualified["origin"].rstrip("/").endswith("stocklookup-ai-research.git")
    assert (ROOT.parent / "ai-core-private").exists() is False


@pytest.mark.skipif(os.name != "nt" or not dependency.PROFILE.exists(), reason="Owner-host genuine Consumer acceptance")
def test_relocated_worktree_resolves_the_real_consumer():
    report = dependency.preflight_producer_seal_consumer(ROOT)
    probe = report["probe"]
    genuine = Path(report["qualified"]["consumer"])
    assert report["status"] == "PASS"
    assert report["relocated_sibling_existed"] is False
    assert report["isolated_binding_created"] is True
    assert Path(probe["resolved"]) == genuine
    assert Path(probe["source"]).is_relative_to(genuine)
    assert probe["accepted_ticker"] == "ABB"
    assert probe["accepted_status"] is None
    assert probe["malformed_status"] == "malformed"
    assert probe["head"] == report["qualified"]["head"]
    assert "builders/build_ticker_context.py" in probe["loaded"]
    assert "builders/vn_time.py" in probe["loaded"]
    assert not (ROOT.parent / "ai-core-private").exists()


@pytest.mark.skipif(os.name != "nt" or not dependency.PROFILE.exists(), reason="Owner-host same-volume junction acceptance")
def test_occupied_sibling_fails_closed(tmp_path):
    # Junctions cannot cross volumes. Keep the fixture on the Consumer volume.
    parent = Path(r"T:\StockLookup\scratch") / ("preseal-occupied-" + tmp_path.name)
    parent.mkdir()
    try:
        relocated = parent / "relocated-producer"
        relocated.mkdir()
        occupied = parent / "ai-core-private"
        occupied.mkdir()
        (occupied / "builders").mkdir()
        genuine = Path(dependency.qualify_consumer()["consumer"])
        with pytest.raises(dependency.ConsumerDependencyError, match="CONSUMER_SIBLING_OCCUPIED"):
            dependency.bind_relocated_consumer(relocated, genuine)
        assert occupied.is_dir() and not occupied.is_junction()
    finally:
        for path in sorted(parent.rglob("*"), reverse=True):
            if path.is_file() or (path.is_dir() and not path.is_junction()):
                path.rmdir() if path.is_dir() else path.unlink()
        parent.rmdir()


def test_unqualified_profile_fails_closed(tmp_path):
    profile = tmp_path / "workspace-v1.json"
    profile.write_text(json.dumps({
        "schema": "stocklookup_workspace/v1",
        "parent": str(tmp_path),
        "roles": {"consumer": str(tmp_path / "missing-consumer")},
    }), encoding="utf-8")
    with pytest.raises(dependency.ConsumerDependencyError, match="CONSUMER_PROFILE_UNQUALIFIED"):
        dependency.qualify_consumer(profile)


@pytest.mark.skipif(os.name != "nt" or not dependency.PROFILE.exists(), reason="Owner-host genuine Consumer acceptance")
def test_unbind_refuses_a_real_consumer_directory():
    genuine = Path(dependency.qualify_consumer()["consumer"])
    with pytest.raises(dependency.ConsumerDependencyError, match="REFUSE_UNBIND_NOT_GENUINE_JUNCTION"):
        dependency.unbind_relocated_consumer(dependency.PRODUCTION_PRODUCER, genuine)
    assert genuine.is_dir() and not genuine.is_junction()
