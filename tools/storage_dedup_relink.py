"""Exact-path hardlink dedup of SHA-identical retained copies (D4 historical). Offline only.

Default is a read-only plan. ``--apply`` requires the exact canonical packet SHA and touches
only rows the packet classifies ELIGIBLE_FOR_OWNER_REVIEW, restricted to ``--kinds``. Every
original path keeps identical bytes; only the alias's file id changes. No content is deleted.
``--rollback RECEIPT`` gives each relinked alias an independent verified copy again.

Never run during Daily. Relinking IID changes file id / ChangeTime of both names, so T+
receipt anchors must be re-seeded out of Daily before the next Daily; Vault fingerprint
leases of covered sessions are re-verified on the next snapshot.

python -B -m tools.storage_dedup_relink --root RETAINED --packet FILE --packet-sha SHA
       --out DIR [--kinds FULL_UNIVERSE,SESSION_BUNDLE,VALUATION,IID] [--hash] [--apply]
python -B -m tools.storage_dedup_relink --root RETAINED --out DIR --rollback RECEIPT.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from tools.vault_snapshot import Refused, canonical, locked_file, require, safe_path

SCHEMA = "storage_d4_exact_path_dedup_packet/v1"
ELIGIBLE = "ELIGIBLE_FOR_OWNER_REVIEW"
KINDS = {"IID", "FULL_UNIVERSE", "SESSION_BUNDLE", "VALUATION"}
PROTECTED_PARTS = {"prospective-decision-retention-v1", "thesis-evidence-t0-v1"}
CHUNK = 8 << 20


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
            row["alias_file_id_before"] = st.st_ino
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
    for row in rows:
        if row["state"] != "READY":
            continue
        keep, alias = _path(root, row["keep"]), _path(root, row["alias"])
        # Re-prove both sides immediately before publishing; hashes are taken under deny-write handles.
        require(_locked_sha(keep) == row["sha256"] and _locked_sha(alias) == row["sha256"], "content changed")
        before = keep.stat()
        require(before.st_ino == row["keep_file_id"], "keep changed")
        stage = alias.with_name(".dedup-relink-" + str(before.st_ino) + ".tmp")
        stage.unlink(missing_ok=True)
        try:
            os.link(keep, stage)
            st = stage.stat()
            require((st.st_ino, st.st_size, st.st_mtime_ns) == (before.st_ino, before.st_size, before.st_mtime_ns),
                    "stage is not the keep inode")
            os.replace(stage, alias)
        finally:
            stage.unlink(missing_ok=True)
        after = alias.stat()
        require(after.st_ino == before.st_ino and after.st_size == row["size"], "alias not linked")
        _append(receipt, {**row, "state": "RELINKED", "alias_file_id_after": after.st_ino})
        done += 1
    return {"relinked": done, "projected_bytes": sum(r["size"] for r in rows if r["state"] == "READY")}


def rollback(root: Path, receipt: Path, out: Path) -> dict:
    restored = 0
    for line in receipt.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("state") != "RELINKED":
            continue
        keep, alias = _path(root, row["keep"]), _path(root, row["alias"])
        if alias.stat().st_ino != keep.stat().st_ino:
            continue  # already independent
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
            os.replace(stage, alias)
        finally:
            stage.unlink(missing_ok=True)
        _append(out / "rollback.jsonl", {**row, "state": "ROLLED_BACK", "alias_file_id_after": alias.stat().st_ino})
        restored += 1
    return {"rolled_back": restored}


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
    a = ap.parse_args(argv)
    root = a.root.resolve()
    try:
        require(root not in a.out.resolve().parents and a.out.resolve() != root, "out must be outside root")
        a.out.mkdir(parents=True, exist_ok=True)
        if a.rollback:
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
                      "projected_bytes": sum(r["size"] for r in rows if r["state"] == "READY"), "applied": False}
            if a.apply:
                result.update(apply(root, rows, a.out / "relink.jsonl"), applied=True)
    except Refused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
