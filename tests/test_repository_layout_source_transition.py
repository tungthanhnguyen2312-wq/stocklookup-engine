"""Repository layout source transition: import-retarget only, versioned, no receipt adoption."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tools.verify_retention_reader_transition import (
    LAYOUT_BASE, LAYOUT_MANIFEST, LAYOUT_SOURCES, historical_bytes, layout_source_receipt_admissible,
    layout_transition_identity,
    CAPACITY_SOURCE, CAPACITY_ARCHIVE, CAPACITY_MANIFEST, _capacity_prior_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _base(relative: str) -> bytes:
    return _lf(subprocess.check_output(["git", "show", f"{LAYOUT_BASE}:{relative}"], cwd=ROOT))


class _Imports(ast.NodeTransformer):
    """Replace every import with a placeholder and record the names it binds."""

    def __init__(self):
        self.bound = []

    def _record(self, node):
        for alias in node.names:
            plain = alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name
            self.bound.append(alias.asname or plain)
        return ast.copy_location(ast.Pass(), node)

    visit_Import = visit_ImportFrom = _record


def _without_imports(source: bytes):
    visitor = _Imports()
    tree = visitor.visit(ast.parse(source.decode("utf-8-sig")))
    return ast.dump(tree, include_attributes=False), visitor.bound


def test_transition_binds_base_archive_live_bytes_and_unchanged_historical_pins():
    identity = layout_transition_identity(ROOT)
    spec = json.loads((ROOT / LAYOUT_MANIFEST).read_bytes())
    base_pins = json.loads(_base("tests/fixtures/e2e3_frozen_sources.json"))["source_sha256_lf"]
    pins = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    assert pins == base_pins
    assert identity["historical_receipt_adoption"] is False and identity["release_authority"] == "NOT_GRANTED"
    for relative, governing in LAYOUT_SOURCES.items():
        row = identity["sources"][relative]
        archive = _lf((ROOT / spec["sources"][relative]["archive"]).read_bytes())
        assert archive == _base(relative)
        # The archived base bytes reproduce the digest the governing transition declared at the base.
        assert json.loads(_base(governing))["sources"][relative]["active_sha256_lf"] == row["prior_sha256_lf"]
        assert hashlib.sha256(_lf((ROOT / relative).read_bytes())).hexdigest() == row["active_sha256_lf"]
        assert hashlib.sha256(historical_bytes(ROOT, relative)).hexdigest() == pins[relative] == row["historical_pin_sha256_lf"]
        assert len({row["historical_pin_sha256_lf"], row["prior_sha256_lf"], row["active_sha256_lf"]}) == 3


def test_only_import_lines_change_and_every_bound_name_is_preserved():
    for relative in LAYOUT_SOURCES:
        base_body, base_names = _without_imports(_base(relative))
        live = _lf((ROOT / relative).read_bytes())
        # Preserve this historical import-only proof at its exact boundary.
        # The capacity successor is separately constrained to _run_daily below.
        layout_live = _capacity_prior_bytes(ROOT, relative, live)
        live_body, live_names = _without_imports(layout_live)
        assert base_body == live_body, relative
        assert base_names == live_names, relative


def test_superseded_and_original_receipts_never_prove_the_live_source():
    identity = layout_transition_identity(ROOT)
    for relative, row in identity["sources"].items():
        assert layout_source_receipt_admissible(ROOT, relative, row["active_sha256_lf"])
        assert not layout_source_receipt_admissible(ROOT, relative, row["prior_sha256_lf"])
        assert not layout_source_receipt_admissible(ROOT, relative, row["historical_pin_sha256_lf"])


def _copy_boundary(tmp_path: Path) -> None:
    spec = json.loads((ROOT / LAYOUT_MANIFEST).read_bytes())
    paths = {LAYOUT_MANIFEST, "tests/fixtures/e2e3_frozen_sources.json", *LAYOUT_SOURCES, *LAYOUT_SOURCES.values(),
             "tests/fixtures/retention_reader_transition_v2.json", CAPACITY_MANIFEST, CAPACITY_ARCHIVE}
    for relative, row in spec["sources"].items():
        paths.add(row["archive"])
        for manifest in set(LAYOUT_SOURCES.values()):
            governing = json.loads((ROOT / manifest).read_bytes())
            if relative in governing["sources"]:
                paths.add(governing["sources"][relative]["archive"])
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_tampered_live_source_fails_the_binding(tmp_path):
    _copy_boundary(tmp_path)
    assert layout_transition_identity(tmp_path)["sources"]
    target = tmp_path / "canonical_post_close_pipeline.py"
    target.write_bytes(target.read_bytes() + b"\n# tamper\n")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        layout_transition_identity(tmp_path)


def test_an_extra_source_is_outside_the_transition_scope(tmp_path):
    _copy_boundary(tmp_path)
    manifest = tmp_path / LAYOUT_MANIFEST
    spec = json.loads(manifest.read_bytes())
    spec["sources"]["runtime_paths.py"] = spec["sources"]["stocklookup.py"]
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        layout_transition_identity(tmp_path)


def test_a_governing_manifest_that_still_declares_the_base_digest_is_refused(tmp_path):
    _copy_boundary(tmp_path)
    governing = tmp_path / LAYOUT_SOURCES["tools/run_owner_daily.py"]
    spec = json.loads(governing.read_bytes())
    layout = json.loads((tmp_path / LAYOUT_MANIFEST).read_bytes())
    spec["sources"]["tools/run_owner_daily.py"]["active_sha256_lf"] = layout["sources"]["tools/run_owner_daily.py"]["prior_sha256_lf"]
    governing.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        layout_transition_identity(tmp_path)


def test_capacity_changes_only_child_launch_control_and_preserves_all_historical_manifests():
    prior = _lf((ROOT / CAPACITY_ARCHIVE).read_bytes())
    base = "c19f72d794dccdeb34ecfe23a40e9ad7dbeef676"
    assert prior == _lf(subprocess.check_output(["git", "show", f"{base}:{CAPACITY_SOURCE}"], cwd=ROOT))
    before = ast.parse(prior.decode())
    after = ast.parse((ROOT / CAPACITY_SOURCE).read_text(encoding="utf-8-sig"))
    def without_launch(tree):
        tree.body = [node for node in tree.body if not (isinstance(node, ast.FunctionDef) and node.name == "_run_daily")]
        return ast.dump(tree, include_attributes=False)
    assert without_launch(before) == without_launch(after)
    for relative in {LAYOUT_MANIFEST, *LAYOUT_SOURCES.values(), "tests/fixtures/e2e3_frozen_sources.json"}:
        assert _lf((ROOT / relative).read_bytes()) == _lf(subprocess.check_output([
            "git", "show", f"{base}:{relative}"], cwd=ROOT))
