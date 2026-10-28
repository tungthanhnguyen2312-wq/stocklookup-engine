"""Process-local reader reuse in retained_evidence_catalog never widens what is accepted."""
import shutil

import pytest

import retained_evidence_catalog as catalog
from tools import vault_snapshot as vault
from tests.test_storage_portability import volumes, write_catalog  # noqa: F401 -- shared fixture


@pytest.fixture(autouse=True)
def fresh_reader_caches():
    for cache in (catalog._LOADED, catalog._VOLUMES, catalog._VERIFIED_CONTENT):
        cache.clear()
    yield
    for cache in (catalog._LOADED, catalog._VOLUMES, catalog._VERIFIED_CONTENT):
        cache.clear()


def registered(volumes, payload=b'{"fixture":"immutable"}'):
    source, hot, _cold, ids, _observer = volumes
    original = source / "operations-review/fixture/dependency.json"
    original.parent.mkdir(parents=True)
    original.write_bytes(payload)
    target = hot / "operations-review/fixture/dependency.json"
    target.parent.mkdir(parents=True)
    shutil.copyfile(original, target)
    proof = catalog.register_copy(original, target, hot / "proof.json", artifact_identity="fixture:dependency",
                                  session="2026-10-05", expected_volume=ids["T"], provenance={"fixture": "reuse"})
    entry = dict(relative_path="operations-review/fixture/dependency.json", original_path=str(original),
                 session_identity="2026-10-05", artifact_identity="fixture:dependency", artifact_role="fixture_dependency",
                 state="PRESENT_QUALIFIED", original_size=len(payload), sha256=vault.sha(original),
                 source_seal_provenance="fixture:original", storage_location=proof)
    write_catalog(hot, [entry])
    return hot, target, entry


def test_catalog_reuse_requires_identical_bytes_and_returns_copies(volumes):
    hot, _target, entry = registered(volumes)
    first = catalog.load(hot)
    first[0]["state"] = "MUTATED_BY_CALLER"
    assert catalog.load(hot) == [entry]
    write_catalog(hot, [{**entry, "state": "NOT_A_STATE"}])
    with pytest.raises(catalog.EvidenceIntegrityError, match="catalog invalid"):
        catalog.load(hot)


def test_verified_bytes_are_not_rehashed_until_fingerprint_changes(volumes, monkeypatch):
    hot, target, entry = registered(volumes)
    calls = []
    real_sha = vault.sha
    monkeypatch.setattr(vault, "sha", lambda path: calls.append(str(path)) or real_sha(path))
    assert catalog.resolve(hot, entry["relative_path"], session_identity="2026-10-05") == "PRESENT_QUALIFIED"
    assert catalog.resolve(hot, entry["relative_path"], session_identity="2026-10-05") == "PRESENT_QUALIFIED"
    assert calls.count(str(target)) == 1
    target.write_bytes(b'{"fixture":"tampered"}')  # same size; fingerprint and bytes differ
    with pytest.raises(vault.Refused, match="STORAGE_CONTENT_OR_FINGERPRINT_CHANGED"):
        catalog.resolve(hot, entry["relative_path"], session_identity="2026-10-05")


def test_volume_attestation_reused_only_for_genuine_observer_within_bound(volumes, monkeypatch):
    _source, hot, _cold, ids, _observer = volumes
    calls = []

    def genuine(path):
        calls.append(str(path))
        return ids["T"].copy()
    monkeypatch.setattr(vault, "native_volume", genuine)
    monkeypatch.setattr(catalog, "_NATIVE_VOLUME", genuine)
    clock = iter([100.0, 110.0, 100.0 + catalog.VOLUME_REUSE_SECONDS + 1])
    monkeypatch.setattr(catalog.time, "monotonic", lambda: next(clock))
    for _ in range(3):
        assert catalog._reader_volume(hot) == ids["T"]
    assert len(calls) == 2  # second call reused; third exceeded the bound

    substituted = []
    monkeypatch.setattr(vault, "native_volume", lambda path: substituted.append(path) or ids["T"].copy())
    catalog._reader_volume(hot)
    catalog._reader_volume(hot)
    assert len(substituted) == 2


def test_wrong_volume_still_refused_with_reuse(volumes):
    hot, _target, entry = registered(volumes)
    _source, _hot, _cold, ids, _observer = volumes
    catalog.resolve(hot, entry["relative_path"], session_identity="2026-10-05")
    with pytest.raises(vault.Refused):
        catalog.verify_location(entry["storage_location"], original_path=entry["original_path"],
                                artifact_identity=entry["artifact_identity"], session="2026-10-05",
                                observer=lambda path: ids["W"])
