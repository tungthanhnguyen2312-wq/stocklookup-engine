"""Exact-path hardlink dedup of SHA-identical retained copies (D4 historical). Offline only.

Default is a read-only plan. ``--apply`` requires the exact canonical packet SHA and touches
only rows the packet classifies ELIGIBLE_FOR_OWNER_REVIEW, restricted to ``--kinds``. Every
original path keeps identical bytes; only the alias's file id changes. No content is deleted.
``--rollback RECEIPT`` gives each relinked alias an independent verified copy again. That is a
byte-level recovery only: the alias gets a NEW file id/ChangeTime, never its original fingerprint.

Apply and rollback hold the shared Production writer lease (non-blocking: refuse while Daily or
capture runs). Projected bytes count an alias inode only when every one of its links is relinked;
the receipt reports the measured volume free-space delta separately (other writers can move it).

Never run during Daily. Relinking IID changes file id / ChangeTime of both names, so T+
receipt anchors must be re-seeded out of Daily before the next Daily; Vault fingerprint
leases of covered sessions are re-verified on the next snapshot.

python -B -m tools.storage_dedup_relink --root RETAINED --packet FILE --packet-sha SHA
       --out DIR [--kinds FULL_UNIVERSE,SESSION_BUNDLE,VALUATION,IID] [--hash] [--apply --writer-root REPO]
python -B -m tools.storage_dedup_relink --root RETAINED --out DIR --rollback RECEIPT.jsonl --writer-root REPO
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from tools.vault_snapshot import Refused, canonical, locked_file, require, safe_path

SCHEMA = "storage_d4_exact_path_dedup_packet/v1"
ELIGIBLE = "ELIGIBLE_FOR_OWNER_REVIEW"
KINDS = {"IID", "FULL_UNIVERSE", "SESSION_BUNDLE", "VALUATION"}
PROTECTED_PARTS = {"prospective-decision-retention-v1", "thesis-evidence-t0-v1"}
CHUNK = 8 << 20
ROLLBACK_RESERVE_BYTES = 1 << 30


@contextmanager
def _writer_lease(writer_root):
    """The same kernel lease Owner Daily and capture-only hold; busy means refuse, never wait."""
    require(writer_root is not None, "--writer-root (Production repo) required for apply/rollback")
    from tools.capture_writer_lease import writer_lease
    try:
        with writer_lease(Path(writer_root)):
            yield
    except BlockingIOError as exc:
        raise Refused("PRODUCTION_WRITER_ACTIVE: Daily/capture holds the writer lease") from exc


def projected_freed_bytes(rows: list[dict]) -> int:
    """An alias inode frees space only when all of its links are replaced by this plan."""
    ready = [r for r in rows if r.get("state") == "READY"]
    seen = Counter(r["alias_file_id_before"] for r in ready)
    sizes = {r["alias_file_id_before"]: (r["size"], r["alias_nlink_before"]) for r in ready}
    return sum(size for inode, (size, nlink) in sizes.items() if seen[inode] >= nlink)


def packet_sha(packet: dict) -> str:
    return hashlib.sha256(canonical(packet)).hexdigest()


def _locked_sha(path: Path) -> str:
    h = hashlib.sha256()
    with locked_file(path) as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _path(root: Path, relative: str) -> Path:
    relative = relative.replace("\\", "/")
    require(not any(part.casefold() in PROTECTED_PARTS for part in relative.split("/")), "protected evidence domain")
    return safe_path(root, relative)


def load_packet(path: Path, expected_sha: str) -> dict:
    packet = json.loads(path.read_text(encoding="utf-8"))
    require(packet.get("schema") == SCHEMA, "packet schema")
    require(packet.get("execute") is False and packet.get("deletion_authorized") is False, "packet flags")
    require(packet_sha(packet) == expected_sha, "packet sha mismatch")
    return packet


def plan(root: Path, packet: dict, kinds: set[str], *, hash_content: bool) -> list[dict]:
    rows = []
    for group in packet["groups"]:
        if group["classification"] != ELIGIBLE or group["kind"] not in kinds:
            continue
        keep = _path(root, group["keep_path"])
        ks = keep.stat()
        problems = []
        if ks.st_ino != group["keep_file_id"] or ks.st_size != group["size"]:
            problems.append("KEEP_CHANGED")
        if hash_content and not problems and _locked_sha(keep) != group["sha256"]:
            problems.append("KEEP_SHA_MISMATCH")
        for alias in group["alias_paths"]:
            target = _path(root, alias["path"])
            row = {"session": group["session"], "kind": group["kind"], "sha256": group["sha256"], "size": group["size"],
                   "keep": group["keep_path"], "keep_file_id": ks.st_ino, "alias": alias["path"], "problems": list(problems)}
            try:
                st = target.stat()
            except FileNotFoundError:
                row["problems"].append("ALIAS_MISSING")
                rows.append(row)
                continue
            row.update(alias_file_id_before=st.st_ino, alias_nlink_before=st.st_nlink,
                       alias_mtime_ns_before=st.st_mtime_ns)
            if st.st_ino == ks.st_ino and st.st_dev == ks.st_dev:
                row["state"] = "ALREADY_LINKED"
            elif (st.st_ino, st.st_nlink, st.st_size) != (alias["file_id"], alias["nlink"], group["size"]) or st.st_dev != ks.st_dev:
                row["problems"].append("ALIAS_CHANGED")
            elif hash_content and _locked_sha(target) != group["sha256"]:
                row["problems"].append("ALIAS_SHA_MISMATCH")
            row.setdefault("state", "BLOCKED" if row["problems"] else "READY")
            rows.append(row)
    return rows


def _append(receipt: Path, row: dict) -> None:
    with receipt.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def apply(root: Path, rows: list[dict], receipt: Path) -> dict:
    require(all(r["state"] in {"READY", "ALREADY_LINKED"} for r in rows), "plan has blocked rows")
    done = 0
    free_before = shutil.disk_usage(root).free
    for row in rows:
        if row["state"] != "READY":
            continue
        keep, alias = _path(root, row["keep"]), _path(root, row["alias"])
        # Re-prove both sides immediately before publishing; hashes are taken under deny-write handles.
        require(_locked_sha(keep) == row["sha256"] and _locked_sha(alias) == row["sha256"], "content changed")
        before = keep.stat()
        require(before.st_ino == row["keep_file_id"], "keep changed")
        current = alias.stat()
        require((current.st_ino, current.st_nlink, current.st_size, current.st_mtime_ns) == (
            row["alias_file_id_before"], row["alias_nlink_before"], row["size"], row["alias_mtime_ns_before"]),
            "alias changed since plan")
        stage = alias.with_name(".dedup-relink-" + str(before.st_ino) + ".tmp")
        stage.unlink(missing_ok=True)
        try:
            os.link(keep, stage)
            st = stage.stat()
            require((st.st_ino, st.st_size, st.st_mtime_ns) == (before.st_ino, before.st_size, before.st_mtime_ns),
                    "stage is not the keep inode")
            # Durable intent first: a crash after replace stays visible to rollback.
            _append(receipt, {**row, "state": "RELINK_INTENT"})
            os.replace(stage, alias)
        finally:
            stage.unlink(missing_ok=True)
        after = alias.stat()
        require(after.st_ino == before.st_ino and after.st_size == row["size"], "alias not linked")
        _append(receipt, {**row, "state": "RELINKED", "alias_file_id_after": after.st_ino})
        done += 1
    free_after = shutil.disk_usage(root).free
    return {"relinked": done, "projected_bytes": projected_freed_bytes(rows),
            "measured_free_delta_bytes": free_after - free_before,
            "measurement_note": "volume-wide delta; concurrent writers and MFT-resident files move it"}


def rollback(root: Path, receipt: Path, out: Path) -> dict:
    restored = 0
    rows = {}
    for line in receipt.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("state") in {"RELINK_INTENT", "RELINKED"}:
            rows[row["alias"]] = row  # intent alone covers a crash between replace and RELINKED
    for row in rows.values():
        keep, alias = _path(root, row["keep"]), _path(root, row["alias"])
        if alias.stat().st_ino != keep.stat().st_ino:
            continue  # already independent (never replaced, or rolled back before)
        require(keep.stat().st_ino == row["keep_file_id"], "keep changed since relink")
        require(shutil.disk_usage(root).free >= row["size"] + ROLLBACK_RESERVE_BYTES,
                "INSUFFICIENT_CAPACITY_FOR_ROLLBACK")
        stage = alias.with_name(".dedup-unlink-" + str(alias.stat().st_ino) + ".tmp")
        h = hashlib.sha256()
        try:
            with locked_file(keep) as source, stage.open("xb") as target:
                for block in iter(lambda: source.read(CHUNK), b""):
                    h.update(block)
                    target.write(block)
                target.flush()
                os.fsync(target.fileno())
            require(h.hexdigest() == row["sha256"], "rollback copy sha mismatch")
            if row.get("alias_mtime_ns_before") is not None:
                os.utime(stage, ns=(row["alias_mtime_ns_before"], row["alias_mtime_ns_before"]))
            os.replace(stage, alias)
        finally:
            stage.unlink(missing_ok=True)
        after = alias.stat()
        _append(out / "rollback.jsonl", {**row, "state": "ROLLED_BACK", "alias_file_id_after": after.st_ino,
                                         "semantic_recovery": "BYTES_ONLY",
                                         "original_file_id_restored": after.st_ino == row.get("alias_file_id_before")})
        restored += 1
    return {"rolled_back": restored, "semantic_recovery": "BYTES_ONLY",
            "note": "new file id/ChangeTime; fingerprint-bound anchors (T+, Vault leases) need requalification"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--packet", type=Path)
    ap.add_argument("--packet-sha")
    ap.add_argument("--kinds", default="FULL_UNIVERSE,SESSION_BUNDLE,VALUATION")
    ap.add_argument("--hash", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", type=Path)
    ap.add_argument("--writer-root", type=Path, help="Production repo whose writer lease apply/rollback must hold")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    try:
        require(root not in a.out.resolve().parents and a.out.resolve() != root, "out must be outside root")
        a.out.mkdir(parents=True, exist_ok=True)
        if a.rollback:
            with _writer_lease(a.writer_root):
                result = rollback(root, a.rollback, a.out)
        else:
            kinds = set(a.kinds.split(","))
            require(kinds <= KINDS, "unknown kind")
            packet = load_packet(a.packet, a.packet_sha)
            rows = plan(root, packet, kinds, hash_content=a.hash or a.apply)
            (a.out / "plan.json").write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")
            result = {"rows": len(rows), "ready": sum(r["state"] == "READY" for r in rows),
                      "blocked": sum(r["state"] == "BLOCKED" for r in rows),
                      "already_linked": sum(r["state"] == "ALREADY_LINKED" for r in rows),
                      "projected_bytes": projected_freed_bytes(rows), "applied": False}
            if a.apply:
                with _writer_lease(a.writer_root):
                    result.update(apply(root, rows, a.out / "relink.jsonl"), applied=True)
    except Refused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
