"""Offline checks for the read-only storage ledger and the runway probe."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

import owner_daily_progress as progress
from tools import storage_ledger as ledger

VN = timezone(timedelta(hours=7))


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSampler:
    def __init__(self, disk: int) -> None:
        self.disk = disk

    def set_child_pid(self, _pid):
        return None

    def set_run_output_paths(self, _paths):
        return None

    def sample(self):
        return {
            "rss_bytes": 20, "peak_rss_bytes": 20, "child_rss_bytes": None,
            "recursive_child_tree_rss_bytes": None, "disk_free_bytes": self.disk, "run_output_bytes": None,
        }


def test_report_counts_physical_bytes_duplicates_and_runway():
    rows = [
        {"path": "a", "size": 100, "dev": 1, "ino": 1, "nlink": 2, "group": "iid",
         "family": "iid-runtime", "session": "20261102", "sha256": "aa"},
        {"path": "a-link", "size": 100, "dev": 1, "ino": 1, "nlink": 2, "group": "iid",
         "family": "iid-runtime", "session": "20261102", "sha256": "aa"},
        {"path": "b", "size": 100, "dev": 1, "ino": 2, "nlink": 1, "group": "retained_evidence",
         "family": "market-wide-current-valuation-v1", "session": "20261103", "sha256": "aa"},
    ]
    report = ledger.build_report(rows, volume_total=1000, volume_used=200, volume_free=800,
                                 hash_budget=10, hashed_bytes=200)
    assert report["authority_effect"] == "NONE_OPERATIONAL_OBSERVABILITY_ONLY"
    assert report["scanned_physical_bytes"] == 200
    assert report["scanned_logical_bytes"] == 300
    assert report["volume_agreement_within_2_percent"] is True
    assert report["physical_duplicates"]["content_duplicate_excess_bytes"] == 100
    assert report["physical_duplicates"]["hardlink_file_rows"] == 2
    assert report["runway"]["warning"] == "CRITICAL"
    assert report["per_session"][1]["growth_bytes"] == 0
    assert report["artifact_physical"]["iid"]["physical_bytes"] == 100
    assert report["artifact_physical"]["iid"]["logical_bytes"] == 200
    assert report["artifact_physical"]["valuation"]["physical_bytes"] == 100
    assert report["artifact_physical"]["full_universe"]["physical_bytes"] == 0
    shifted = ledger.build_report(rows, volume_total=1000, volume_used=210, volume_free=800,
                                  hash_budget=10, hashed_bytes=0)
    assert shifted["volume_agreement_within_2_percent"] is False


def test_scan_resumes_without_double_counting_and_classifies(tmp_path):
    root = tmp_path / "vol"
    retained = root / "retained"
    valuation = retained / "market-wide-current-valuation-v1-20261104"
    valuation.mkdir(parents=True)
    (valuation / "body.bin").write_bytes(b"abc")
    iid = root / "scratch" / "iid-runtime-memory-evidence"
    iid.mkdir(parents=True)
    (iid / "model.bin").write_bytes(b"abcd")
    sidecar = retained / "prospective-decision-outcome-feedback"
    sidecar.mkdir()
    (sidecar / "rows.sidecar").write_bytes(b"z")
    roots = {"retained_evidence": retained, "scratch": root / "scratch",
             "recovery_checkpoints": None, "worktree_archives": None}
    state = tmp_path / "state.json"
    ledger.scan(root, roots, state, guard=lambda: None)
    ledger.scan(root, roots, state, guard=lambda: None)
    rows = {row["path"]: row for row in ledger.load_records(Path(json.loads(state.read_text())["files"]))}
    assert len(rows) == 3
    body = next(row for row in rows.values() if row["path"].endswith("body.bin"))
    assert body["group"] == "retained_evidence"
    assert body["session"] == "20261104"
    assert body["family"] == "market-wide-current-valuation-v1"
    assert next(row["group"] for row in rows.values() if row["path"].endswith("model.bin")) == "iid"
    assert next(row["group"] for row in rows.values() if row["path"].endswith("rows.sidecar")) == "tplus_sidecars"
    hashed = ledger.hash_pending(list(rows.values()), budget=4, guard=lambda: None)
    assert hashed == 4
    assert sum(1 for row in rows.values() if row.get("sha256")) == 1


def test_session_dates_ignore_hash_fragments_and_keep_dashed_days(tmp_path):
    retained = tmp_path / "retained"
    day = retained / "operations-review" / "daily-research-session-operations-v1" / "2026-11-04"
    day.mkdir(parents=True)
    hashed = day / "ab20261105cd20000198ef.json"
    hashed.write_bytes(b"x")
    family, session = ledger.family_and_session(hashed, retained)
    assert session == "20261104"
    assert family == "operations-review"
    compact = retained / "market-wide-current-valuation-v1-20261103" / "body.bin"
    compact.parent.mkdir()
    compact.write_bytes(b"y")
    family, session = ledger.family_and_session(compact, retained)
    assert session == "20261103"
    assert family == "market-wide-current-valuation-v1"
    assert ledger.calendar_day("20000198") is None
    report = ledger.build_report(
        [{"path": "h", "size": 5, "dev": 1, "ino": 9, "nlink": 1, "group": "other",
          "family": None, "session": "20000198", "sha256": None},
         {"path": "d", "size": 7, "dev": 1, "ino": 10, "nlink": 1, "group": "retained_evidence",
          "family": "daily", "session": "20261104", "sha256": None}],
        volume_total=100, volume_used=12, volume_free=80, hash_budget=0, hashed_bytes=0)
    assert [row["session"] for row in report["per_session"]] == ["20261104"]
    horizon = ledger.build_report(
        [{"path": "future", "size": 721047, "dev": 1, "ino": 1, "nlink": 1, "group": "other",
          "family": None, "session": "20270916", "sha256": None},
         {"path": "today", "size": 50, "dev": 1, "ino": 2, "nlink": 1, "group": "retained_evidence",
          "family": "daily", "session": "20261104", "sha256": None}],
        volume_total=1000, volume_used=50, volume_free=800, hash_budget=0, hashed_bytes=0,
        as_of="20261105")
    assert horizon["runway"]["sample_sessions"] == ["20261104"]
    assert horizon["runway"]["bytes_per_session"] == 50


def test_daily_guard_blocks_a_process_a_lock_and_an_unproven_window(tmp_path):
    morning = datetime(2026, 11, 5, 10, 30)
    assert ledger.daily_block_reason(now=morning, run_logs=tmp_path, command_lines=[]) is None
    assert ledger.daily_block_reason(now=morning, run_logs=tmp_path, command_lines=["python run_owner_daily.py"]) == "DAILY_PROCESS"
    (tmp_path / "writer.lock").write_text("busy", encoding="utf-8")
    assert ledger.daily_block_reason(now=morning, run_logs=tmp_path, command_lines=[]) == "DAILY_LOCK"
    (tmp_path / "writer.lock").unlink()
    evening = datetime(2026, 11, 5, 16, 0)
    assert ledger.daily_block_reason(now=evening, run_logs=tmp_path, command_lines=[]) == "DAILY_WINDOW_UNPROVEN"
    (tmp_path / "stock_lookup_daily_20261105_final.result.json").write_text(
        json.dumps({"status": "PASS"}), encoding="utf-8")
    assert ledger.daily_block_reason(now=evening, run_logs=tmp_path, command_lines=[]) is None


def test_disk_probe_follows_the_output_volume(tmp_path, monkeypatch):
    seen = []
    original = shutil.disk_usage

    def usage(path):
        seen.append(Path(path))
        return original(path)

    monkeypatch.setattr(progress.shutil, "disk_usage", usage)
    sampler = progress.ResourceSampler()
    assert sampler.sample()["disk_free_bytes"] is None and seen == []
    target = tmp_path / "session"
    target.mkdir()
    sampler.set_run_output_paths([target])
    assert sampler.sample()["disk_free_bytes"] is not None
    assert seen == [Path(tmp_path.resolve().anchor)]
    explicit = progress.ResourceSampler(disk_path=tmp_path)
    explicit.set_run_output_paths([target])
    assert explicit.disk_path == tmp_path


def test_runway_warnings_do_not_change_authority(tmp_path):
    assert progress.AUTHORITY_EFFECT == "NONE_OPERATIONAL_OBSERVABILITY_ONLY"
    safe = progress.RUNWAY_FLOOR_BYTES + 12 * progress.PLANNING_SESSION_BYTES
    warning = progress.RUNWAY_FLOOR_BYTES + 7 * progress.PLANNING_SESSION_BYTES
    critical = progress.RUNWAY_FLOOR_BYTES + 3 * progress.PLANNING_SESSION_BYTES
    assert progress.runway_level(safe) is None
    assert progress.runway_level(warning) == "WARNING"
    assert progress.runway_level(critical) == "CRITICAL"
    lines = []
    clock = FakeClock()
    sampler = FakeSampler(warning)
    emitter = progress.OwnerDailyProgress(
        tmp_path / "progress.jsonl", sampler=sampler, clock=clock, human_sink=lines.append,
        wall_clock=lambda: datetime(2026, 11, 5, 10, tzinfo=VN),
    )
    event = emitter.emit(phase_index=2, component="Prospective decision feedback", status="RUNNING")
    assert event["authority_effect"] == progress.AUTHORITY_EFFECT
    assert "còn dưới 10 phiên" in lines[-1] and "còn dưới 5 phiên" not in lines[-1]
    sampler.disk = critical
    clock.value = 30
    emitter.emit(phase_index=2, component="Prospective decision feedback", status="RUNNING")
    assert "còn dưới 5 phiên" in lines[-1]
