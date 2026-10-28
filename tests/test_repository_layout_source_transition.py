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
    CAPACITY_SOURCE, CAPACITY_ARCHIVE, CAPACITY_MANIFEST, _capacity_prior_bytes, _launcher_prior_bytes, LAUNCHER_MANIFEST, LAUNCHER_SOURCES,
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
             "tests/fixtures/retention_reader_transition_v2.json", CAPACITY_MANIFEST, CAPACITY_ARCHIVE, LAUNCHER_MANIFEST,
             "tests/fixtures/owner_daily_iid_runtime_memory_source_transition_v1.json",
             "tests/fixtures/owner_daily_preseal_consumer_memory_source_transition_v1.json",
             "tests/fixtures/owner_daily_preseal_consumer_memory_v1_sources/canonical_daily_operation.py.txt",
             *("tests/fixtures/owner_daily_launcher_v1_sources/" + p + ".txt" for p in LAUNCHER_SOURCES),
             *("tests/fixtures/owner_daily_iid_runtime_memory_v1_sources/" + p + ".txt"
               for p in ("tools/run_owner_daily.py", "canonical_post_close_pipeline.py",
                         "stocklookup_core/decision/integrated_investment_decision_product.py"))}
    for relative, row in spec["sources"].items():
        paths.add(row["archive"])
        for manifest in set(LAYOUT_SOURCES.values()):
            governing = json.loads((ROOT / manifest).read_bytes())
            if relative in governing["sources"]:
                paths.add(governing["sources"][relative]["archive"])
    final = "tests/fixtures/owner_daily_streamed_final_source_transition_v1.json"
    paths.add(final)
    paths.update(row["archive"] for row in json.loads((ROOT / final).read_bytes())["sources"].values())
    capture = "tests/fixtures/owner_daily_capture_only_source_transition_v1.json"
    paths.add(capture)
    paths.add(json.loads((ROOT / capture).read_bytes())["archive"])
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
    after = ast.parse(_launcher_prior_bytes(ROOT, CAPACITY_SOURCE, _lf((ROOT / CAPACITY_SOURCE).read_bytes())).decode())
    def without_launch(tree):
        tree.body = [node for node in tree.body if not (isinstance(node, ast.FunctionDef) and node.name == "_run_daily")]
        return ast.dump(tree, include_attributes=False)
    assert without_launch(before) == without_launch(after)
    for relative in {LAYOUT_MANIFEST, *LAYOUT_SOURCES.values(), "tests/fixtures/e2e3_frozen_sources.json"}:
        assert _lf((ROOT / relative).read_bytes()) == _lf(subprocess.check_output([
            "git", "show", f"{base}:{relative}"], cwd=ROOT))


def test_launcher_successor_preserves_every_workflow_body_and_historical_boundary():
    spec = json.loads((ROOT / LAUNCHER_MANIFEST).read_bytes())
    class StripImports(ast.NodeTransformer):
        def visit_Import(self, node):
            return None
        visit_ImportFrom = visit_Import
    additions = {"materialize_release_ready_runtime", "materialize_canonical_trusted_subset", "__getattr__",
                 "supervised_main", "validate_relaunch_request", "write_relaunch_failure"}
    def body(source):
        tree = ast.parse(source)
        tree.body = [n for n in tree.body if not (
            isinstance(n, ast.FunctionDef) and n.name in additions | {"relaunch_on_advanced_code", "_resolve_intended_session"}
            or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"RELAUNCH_PATH_ENV", "RELAUNCH_EXIT"} for t in n.targets)
            or isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__")]
        return ast.dump(StripImports().visit(tree), include_attributes=False)
    for relative, row in spec["sources"].items():
        archived = _lf((ROOT / row["archive"]).read_bytes())
        base = _lf(subprocess.check_output(["git", "show", f"{spec['base_commit']}:{relative}"], cwd=ROOT))
        assert archived == base
        live = _lf((ROOT / relative).read_bytes())
        assert _launcher_prior_bytes(ROOT, relative, live) == base
        if relative == CAPACITY_SOURCE:
            pre_corrective = _lf((ROOT / "tests/fixtures/owner_daily_iid_runtime_memory_v1_sources/tools/run_owner_daily.py.txt").read_bytes())
            assert body(base) == body(pre_corrective)
        else:
            assert ast.dump(ast.parse(live.replace(b"owner_daily.supervised_main(", b"owner_daily.main("))) == ast.dump(ast.parse(base))
    historical = {LAYOUT_MANIFEST, CAPACITY_MANIFEST, CAPACITY_ARCHIVE, *LAYOUT_SOURCES.values(),
                  "tests/fixtures/e2e3_frozen_sources.json"}
    for relative in historical:
        assert _lf((ROOT / relative).read_bytes()) == _lf(subprocess.check_output([
            "git", "show", f"{spec['base_commit']}:{relative}"], cwd=ROOT))


@pytest.mark.parametrize("tamper", ["live", "archive", "scope"])
def test_launcher_successor_rejects_tampering(tmp_path, tamper):
    _copy_boundary(tmp_path)
    source = tmp_path / CAPACITY_SOURCE
    if tamper == "live":
        source.write_bytes(source.read_bytes() + b"# tamper\n")
    elif tamper == "archive":
        (tmp_path / ("tests/fixtures/owner_daily_launcher_v1_sources/" + CAPACITY_SOURCE + ".txt")).write_bytes(b"tamper")
    else:
        manifest = tmp_path / LAUNCHER_MANIFEST
        spec = json.loads(manifest.read_bytes())
        spec["sources"]["runtime_paths.py"] = spec["sources"][CAPACITY_SOURCE]
        manifest.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="(?:LAUNCHER|IID_RUNTIME_MEMORY|CAPTURE_WRITER)_SOURCE_TRANSITION"):
        _capacity_prior_bytes(tmp_path, CAPACITY_SOURCE, _lf(source.read_bytes()))
