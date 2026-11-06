"""D4 historical relink tool: exact packet, plan-only default, verified apply and rollback."""
import hashlib
import json
import os
import threading
from pathlib import Path

import pytest

from tools import storage_dedup_relink as relink

DATA = b'{"rows": [1, 2, 3]}\n' * 1000


def _fixture(tmp_path, *, kind="FULL_UNIVERSE", classification=relink.ELIGIBLE, keep_rel=None, alias_rel=None):
    root = tmp_path / "retained"
    keep_rel = keep_rel or "operations-review/daily-research-session-operations-v1/2026-10-02/op/ai_research_full_universe.ndjson"
    alias_rel = alias_rel or "operations-review/daily-producer-runs-v1/2026-10-02/run/ai_research_full_universe.ndjson"
    for rel in (keep_rel, alias_rel):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(DATA)
    ks, st = (root / keep_rel).stat(), (root / alias_rel).stat()
    packet = {"schema": relink.SCHEMA, "execute": False, "deletion_authorized": False, "groups": [{
        "session": "20261002", "kind": kind, "sha256": hashlib.sha256(DATA).hexdigest(), "size": len(DATA),
        "classification": classification, "keep_path": keep_rel.replace("/", "\\"), "keep_file_id": ks.st_ino,
        "alias_paths": [{"path": alias_rel.replace("/", "\\"), "file_id": st.st_ino, "nlink": 1, "mtime_ns": st.st_mtime_ns}]}]}
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    return root, path, relink.packet_sha(packet), root / keep_rel, root / alias_rel


def _run(*args):
    args = [str(a) for a in args]
    if ("--apply" in args or "--rollback" in args) and "--writer-root" not in args:
        # A per-test writer root: its kernel lease never collides with Production's.
        args += ["--writer-root", str(Path(args[args.index("--out") + 1]).parent / "writer-repo")]
    return relink.main(args)


def test_default_is_plan_only_and_changes_nothing(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    before = (keep.stat().st_ino, alias.stat().st_ino)
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out", "--hash") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] == 1 and result["applied"] is False and result["projected_bytes"] == len(DATA)
    assert (keep.stat().st_ino, alias.stat().st_ino) == before


def test_apply_links_alias_to_keep_with_identical_bytes_then_is_idempotent(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    args = ("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out")
    assert _run(*args, "--apply") == 0
    assert json.loads(capsys.readouterr().out)["relinked"] == 1
    assert alias.stat().st_ino == keep.stat().st_ino and keep.stat().st_nlink == 2
    assert alias.read_bytes() == keep.read_bytes() == DATA
    assert not list(alias.parent.glob(".dedup-*"))
    assert _run(*args, "--apply") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["already_linked"] == 1 and result["relinked"] == 0


def test_rollback_restores_an_independent_verified_copy(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    out = tmp_path / "out"
    _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", out, "--apply")
    assert _run("--root", root, "--out", out, "--rollback", out / "relink.jsonl") == 0
    assert "rolled_back" in capsys.readouterr().out
    assert alias.stat().st_ino != keep.stat().st_ino and keep.stat().st_nlink == 1
    assert alias.read_bytes() == DATA


def test_wrong_packet_sha_refuses(tmp_path, capsys):
    root, packet, _sha, *_ = _fixture(tmp_path)
    assert _run("--root", root, "--packet", packet, "--packet-sha", "0" * 64, "--out", tmp_path / "out", "--apply") == 2
    assert "packet sha mismatch" in capsys.readouterr().out


def test_same_size_changed_content_blocks_apply(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    data = bytearray(DATA)
    data[0] = ord("[")
    stat = alias.stat()
    alias.write_bytes(bytes(data))
    os.utime(alias, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out", "--apply") == 2
    assert "blocked" in capsys.readouterr().out
    assert alias.stat().st_ino != keep.stat().st_ino


def test_replaced_alias_file_id_blocks(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    alias.unlink()
    alias.write_bytes(DATA)  # same bytes, new inode written after the packet
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out") == 0
    rows = json.loads((tmp_path / "out" / "plan.json").read_text())
    assert rows[0]["problems"] == ["ALIAS_CHANGED"]


def test_iid_needs_explicit_kind_and_protected_rows_are_skipped(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path, kind="IID")
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out", "--apply") == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 0
    root, packet, sha, keep, alias = _fixture(tmp_path / "b", classification="PROTECTED_RECENT_SESSION")
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out2",
                "--kinds", "FULL_UNIVERSE,IID", "--apply") == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 0


def test_t0_domain_is_refused(tmp_path, capsys):
    root, packet, sha, *_ = _fixture(tmp_path, alias_rel="operations-review/prospective-decision-retention-v1/x/a.ndjson")
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out") == 2
    assert "protected evidence domain" in capsys.readouterr().out


def test_out_inside_root_is_refused(tmp_path, capsys):
    root, packet, sha, *_ = _fixture(tmp_path)
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", root / "out") == 2


def test_apply_refuses_while_production_writer_lease_is_held(tmp_path, capsys):
    from tools.capture_writer_lease import writer_lease
    root, packet, sha, keep, alias = _fixture(tmp_path)
    repo, held, release = tmp_path / "repo", threading.Event(), threading.Event()

    def daily():
        with writer_lease(repo):
            held.set()
            release.wait(30)
    worker = threading.Thread(target=daily)
    worker.start()
    try:
        assert held.wait(30)
        assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", tmp_path / "out",
                    "--apply", "--writer-root", repo) == 2
        assert "PRODUCTION_WRITER_ACTIVE" in capsys.readouterr().out
        assert alias.stat().st_ino != keep.stat().st_ino
    finally:
        release.set()
        worker.join()
    assert relink.main([str(a) for a in ("--root", root, "--packet", packet, "--packet-sha", sha,
                                         "--out", tmp_path / "out2", "--apply")]) == 2
    assert "--writer-root" in capsys.readouterr().out


def test_projected_bytes_count_only_inodes_whose_every_link_is_replaced(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    os.link(alias, alias.with_name("outside-plan-link.ndjson"))  # a second name the packet does not cover
    doc = json.loads(packet.read_text())
    doc["groups"][0]["alias_paths"][0]["nlink"] = 2
    packet.write_text(json.dumps(doc))
    assert _run("--root", root, "--packet", packet, "--packet-sha", relink.packet_sha(doc),
                "--out", tmp_path / "out", "--apply") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["relinked"] == 1 and result["projected_bytes"] == 0
    assert "measured_free_delta_bytes" in result


def test_alias_touched_after_plan_refuses_apply(tmp_path):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    rows = relink.plan(root, relink.load_packet(packet, sha), {"FULL_UNIVERSE"}, hash_content=True)
    st = alias.stat()
    os.utime(alias, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    with pytest.raises(relink.Refused, match="alias changed since plan"):
        relink.apply(root, rows, tmp_path / "relink.jsonl")
    assert alias.stat().st_ino != keep.stat().st_ino


def test_crash_after_replace_is_still_rolled_back_from_intent(tmp_path, capsys):
    root, packet, sha, keep, alias = _fixture(tmp_path)
    out = tmp_path / "out"
    original_mtime = alias.stat().st_mtime_ns
    assert _run("--root", root, "--packet", packet, "--packet-sha", sha, "--out", out, "--apply") == 0
    receipt = out / "relink.jsonl"
    lines = receipt.read_text().splitlines()
    assert [json.loads(x)["state"] for x in lines] == ["RELINK_INTENT", "RELINKED"]
    receipt.write_text(lines[0] + chr(10))  # crash before the RELINKED row became durable
    capsys.readouterr()
    assert _run("--root", root, "--out", out, "--rollback", receipt) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["rolled_back"] == 1 and result["semantic_recovery"] == "BYTES_ONLY"
    row = json.loads((out / "rollback.jsonl").read_text().splitlines()[-1])
    assert row["original_file_id_restored"] is False  # bytes back, original inode/fingerprint not
    assert alias.stat().st_ino != keep.stat().st_ino and alias.read_bytes() == DATA
    assert alias.stat().st_mtime_ns == original_mtime
