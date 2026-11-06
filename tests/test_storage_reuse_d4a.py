"""D4a storage reuse: Owner switches, IID working-view hardlink and delivery-reuse wiring.

Only how equal bytes are stored may change. Paths, bytes, identities and failure
behaviour must equal the copy path; switches are off unless the Owner turns them on.
"""
import json
import os

import pytest

import canonical_post_close_pipeline as pipeline
import prospective_decision_outcome_feedback as feedback
from _integrated_decision_fixture import integrated_decision
from test_canonical_post_close_pipeline import _patch_full_pipeline_stages

SESSION = "2026-10-02"


def _written(tmp_path):
    artifact = integrated_decision(SESSION, ["FPT"])
    source, destination = tmp_path / "canonical.json", tmp_path / "view/iid.json"
    receipt = pipeline._write_json(source, artifact, capture_iid_receipt=True)
    destination.parent.mkdir()
    destination.write_bytes(b'{"previous":"valid"}\n')
    return artifact, source, destination, receipt


def _config(tmp_path, value):
    path = tmp_path / "daily_storage_reuse.json"
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return path


def test_shipped_config_is_valid_and_every_switch_is_off():
    assert pipeline.storage_reuse_switches() == {"iid_working_view_hardlink": False, "reuse_immutable_delivery": False}


def test_absent_config_means_off(tmp_path):
    assert set(pipeline.storage_reuse_switches(tmp_path / "missing.json").values()) == {False}


def test_valid_config_is_honoured(tmp_path):
    path = _config(tmp_path, {"schema": "daily_storage_reuse/v1", "iid_working_view_hardlink": True,
                              "reuse_immutable_delivery": False})
    assert pipeline.storage_reuse_switches(path) == {"iid_working_view_hardlink": True, "reuse_immutable_delivery": False}


@pytest.mark.parametrize("value", [
    "{not json",
    [],
    {"schema": "other/v1", "iid_working_view_hardlink": True, "reuse_immutable_delivery": True},
    {"schema": "daily_storage_reuse/v1", "iid_working_view_hardlink": "true", "reuse_immutable_delivery": False},
    {"schema": "daily_storage_reuse/v1", "iid_working_view_hardlink": 1, "reuse_immutable_delivery": False},
    {"schema": "daily_storage_reuse/v1", "iid_working_view_hardlink": True},
    {"schema": "daily_storage_reuse/v1", "iid_working_view_hardlink": True, "reuse_immutable_delivery": True, "extra": True},
])
def test_malformed_config_refuses(tmp_path, value):
    with pytest.raises(pipeline.CanonicalPostCloseError, match="STORAGE_REUSE_CONFIG"):
        pipeline.storage_reuse_switches(_config(tmp_path, value))


def test_link_publishes_one_inode_with_identical_bytes(tmp_path):
    artifact, source, destination, receipt = _written(tmp_path)
    before_bytes, before = source.read_bytes(), source.stat()
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    after = source.stat()
    assert destination.read_bytes() == before_bytes
    assert (destination.stat().st_dev, destination.stat().st_ino) == (after.st_dev, after.st_ino)
    assert after.st_nlink == 2
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    assert feedback._source_fingerprint(source) == feedback._source_fingerprint(destination)
    assert not list(destination.parent.glob(".iid-*"))


def test_link_is_idempotent_on_replay(tmp_path):
    artifact, source, destination, receipt = _written(tmp_path)
    for _ in range(2):
        pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    assert source.stat().st_nlink == 2 and destination.read_bytes() == source.read_bytes()


def test_canonical_rewrite_after_link_never_changes_the_view(tmp_path):
    artifact, source, destination, receipt = _written(tmp_path)
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    view = destination.read_bytes()
    other = integrated_decision(SESSION, ["FPT", "VNM"])
    pipeline._write_json(source, other, capture_iid_receipt=True)  # the replace-only canonical writer
    assert destination.read_bytes() == view
    assert source.stat().st_ino != destination.stat().st_ino
    assert destination.stat().st_nlink == 1


def test_view_rewrite_after_link_never_changes_canonical(tmp_path):
    artifact, source, destination, receipt = _written(tmp_path)
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    canonical = source.read_bytes()
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=False)
    assert source.read_bytes() == canonical and source.stat().st_nlink == 1


def test_link_refusal_falls_back_to_verified_copy(tmp_path, monkeypatch):
    artifact, source, destination, receipt = _written(tmp_path)
    monkeypatch.setattr(pipeline.os, "link", lambda *a: (_ for _ in ()).throw(OSError("links unsupported")))
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_ino != source.stat().st_ino and source.stat().st_nlink == 1


def test_cross_volume_falls_back_to_copy(tmp_path, monkeypatch):
    artifact, source, destination, receipt = _written(tmp_path)
    real = pipeline._link_iid_working_view

    class Other:
        def __init__(self, st):
            self.st_dev, self.st_ino = st.st_dev + 1, st.st_ino
    monkeypatch.setattr(pipeline, "_link_iid_working_view",
                        lambda s, d, r, before: real(s, d, r, Other(before)))
    pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    assert destination.read_bytes() == source.read_bytes() and source.stat().st_nlink == 1


def test_same_stat_corruption_refuses_link_and_keeps_previous_view(tmp_path):
    artifact, source, destination, receipt = _written(tmp_path)
    data, stat = bytearray(source.read_bytes()), source.stat()
    data[10] = ord("X") if data[10] != ord("X") else ord("Y")
    source.write_bytes(bytes(data))
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    previous = destination.read_bytes()
    with pytest.raises(pipeline.CanonicalPostCloseError, match="SOURCE_BYTES_MISMATCH"):
        pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=receipt, link=True)
    assert destination.read_bytes() == previous and source.stat().st_nlink == 1
    assert not list(destination.parent.glob(".iid-*"))


def test_unbound_receipt_still_refuses_in_link_mode(tmp_path):
    artifact, source, destination, _receipt = _written(tmp_path)
    previous = destination.read_bytes()
    with pytest.raises(pipeline.CanonicalPostCloseError, match="RECEIPT_MISMATCH"):
        pipeline._copy_iid_working_view(source, destination, session=SESSION, artifact=artifact, receipt=None, link=True)
    assert destination.read_bytes() == previous


@pytest.mark.parametrize("switch", [False, True])
def test_daily_producer_receives_owner_delivery_switch(tmp_path, monkeypatch, switch):
    order, seen = [], {}
    _patch_full_pipeline_stages(monkeypatch, order, tmp_path)
    fake = pipeline.run_daily_producer
    monkeypatch.setattr(pipeline, "run_daily_producer", lambda *a, **k: seen.update(k) or fake(*a, **k))
    monkeypatch.setattr(pipeline, "storage_reuse_switches",
                        lambda path=None: {"iid_working_view_hardlink": False, "reuse_immutable_delivery": switch})
    pipeline.run_canonical_post_close(tmp_path, tmp_path / "runtime", "2026-08-26")
    assert seen["reuse_immutable_delivery"] is switch
