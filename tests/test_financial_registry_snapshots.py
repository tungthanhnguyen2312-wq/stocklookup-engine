"""Complete frozen membership, strict parsing, and retained offline replay parity."""
from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from stocklookup_core.evidence import official_ocr_layout_proof as layouts
from tools import run_dual_reader_transcription_admission as runner

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests/fixtures/registry_migration_v1/baseline_registries.json"
BASE = "74017553c7a17c33a5464ec735f3700df669bbd5"


def _wire(value):
    return json.loads(json.dumps(value))


def test_complete_baseline_entry_equality():
    import financial_evidence_currency_contract as currency
    import official_financial_filing_evidence as filing
    baseline = json.loads(BASELINE.read_bytes())
    actual = {"specs": runner.SPECS, "layouts": layouts.LAYOUT_PROOFS,
              "exact_issuer_names": layouts.EXACT_REGISTERED_ISSUER_NAMES,
              "folded_issuer_names": layouts.REGISTERED_ISSUER_FOLD,
              "entity_families": currency.ENTITY_FAMILY, "cohort": currency.COHORT,
              "attachment_hosts": {k: sorted(v) for k, v in filing._EXISTING_ISSUER_ATTACHMENT_HOSTS.items()}}
    for name, value in actual.items():
        assert _wire(value) == baseline[name], name
    assert [k for k, v in runner.SPECS.items() if isinstance(v["readings"], tuple)] == baseline["tuple_readings"]
    assert all(isinstance(p["statement_pages"], tuple) for p in layouts.LAYOUT_PROOFS.values())
    assert all(isinstance(v, tuple) for v in layouts.EXACT_REGISTERED_ISSUER_NAMES.values())
    # Cohort is a literal independent of the registry's membership.
    tree = ast.parse((ROOT / "financial_evidence_currency_contract.py").read_bytes())
    cohort = next(n.value for n in tree.body if isinstance(n, ast.AnnAssign) and n.target.id == "COHORT")
    assert _wire(ast.literal_eval(cohort)) == baseline["cohort"]


@pytest.mark.parametrize("role,path", [("layouts", layouts.LAYOUT_SNAPSHOT), ("issuers", layouts.ISSUER_SNAPSHOT),
    ("admissions", "config/dual_reader_admissions/r0001.json")])
@pytest.mark.parametrize("case", ["duplicate", "schema", "extra", "type", "entry_extra", "oversize", "escape", "hash"])
def test_snapshot_rejects_invalid_bytes(tmp_path, role, path, case):
    value = json.loads((ROOT / path).read_bytes())
    if case == "schema":
        value["schema_version"] = 2
    elif case == "extra":
        value["unexpected"] = True
    elif case == "type":
        value["revision"] = True
    elif case == "entry_extra":
        group = "entity_families" if role == "issuers" else "entries"
        next(iter(value[group].values()))["unexpected"] = True
    raw = json.dumps(value).encode()
    if case == "duplicate":
        raw = raw.replace(b'{', b'{"revision":1,', 1)
    elif case == "oversize":
        raw = b" " * (1024 * 1024 + 1)
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    with pytest.raises(ValueError):
        layouts.load_registry_snapshot(role, root=tmp_path,
            relative="../escaped.json" if case == "escape" else path,
            expected_sha256_lf="0" * 64 if case == "hash" else None)


def test_cached_parse_uses_exact_hashed_bytes_and_returns_detached_values(tmp_path):
    path = tmp_path / layouts.LAYOUT_SNAPSHOT
    path.parent.mkdir(parents=True)
    raw = (ROOT / layouts.LAYOUT_SNAPSHOT).read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(raw)
    digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    first = layouts.load_registry_snapshot("layouts", root=tmp_path, expected_sha256_lf=digest)
    first["entries"].clear()
    assert layouts.load_registry_snapshot("layouts", root=tmp_path, expected_sha256_lf=digest)["entries"]
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        layouts.load_registry_snapshot("layouts", root=tmp_path, expected_sha256_lf=digest)


def test_issuer_exactness_unknown_family_and_native_fallback_remain_unchanged():
    import financial_evidence_currency_contract as currency
    baseline = json.loads(BASELINE.read_bytes())
    for ticker, names in baseline["exact_issuer_names"].items():
        for name in names:
            literal = name["literal"]
            assert layouts.exact_registered_issuer_name(ticker, literal)
            assert not layouts.exact_registered_issuer_name(ticker, literal + " ")
            assert not layouts.exact_registered_issuer_name(ticker, literal.lower())
    assert currency.ENTITY_FAMILY.get("UNKNOWN") is None
    # Owner unchanged: the same unknown-family refusal still controls native fallback.
    source = "official_financial_ocr_table_evidence.py"
    assert (ROOT / source).read_bytes().replace(b"\r\n", b"\n") == subprocess.check_output(
        ["git", "show", BASE + ":" + source], cwd=ROOT).replace(b"\r\n", b"\n")


def test_registry_source_transitions_conserve_exact_predecessors():
    from tools.verify_retention_reader_transition import historical_bytes
    for source in ("stocklookup_core/evidence/official_ocr_layout_proof.py", "financial_evidence_currency_contract.py"):
        historical = historical_bytes(ROOT, source)
        if source.startswith("stocklookup_core"):
            assert historical == subprocess.check_output(["git", "show", BASE + ":" + source], cwd=ROOT).replace(b"\r\n", b"\n")
        else:
            spec = json.loads((ROOT / "tests/fixtures/financial_evidence_currency_contract_source_transition_v1.json").read_bytes())
            assert hashlib.sha256(historical).hexdigest() == spec["prior_sha256_lf"]


_REPLAY_CHILD = r'''import hashlib, importlib, json, pathlib, sys, types, subprocess
sys.dont_write_bytecode = True
root, mode, key, landing, retained, reader, evidence, proof, completed = sys.argv[1:]
root=pathlib.Path(root);sys.path.insert(0,str(root))
if mode == "base":
    for name, relative in [("stocklookup_core.evidence.official_ocr_layout_proof", "stocklookup_core/evidence/official_ocr_layout_proof.py"),
                           ("financial_evidence_currency_contract", "financial_evidence_currency_contract.py"),
                           ("tools.run_dual_reader_transcription_admission", "tools/run_dual_reader_transcription_admission.py")]:
        parent, _, attr = name.rpartition(".")
        package=importlib.import_module(parent) if parent else None
        module=types.ModuleType(name);module.__file__=str(root/relative);sys.modules[name]=module
        if package is not None:setattr(package,attr,module)
        source=subprocess.check_output(["git","show","74017553c7a17c33a5464ec735f3700df669bbd5:"+relative],cwd=root)
        exec(compile(source,str(root/relative),"exec"),module.__dict__)
from tools import run_dual_reader_transcription_admission as runner
landing=pathlib.Path(landing);retained=pathlib.Path(retained)
spec=runner.SPECS[key]
# Only the original manifest and its exact source PDF are copied into an isolated tree.
original=landing/spec["original_subdir"];original.mkdir(parents=True,exist_ok=True)
raw=(retained/spec["original_subdir"]/runner.MANIFEST).read_bytes()
(original/runner.MANIFEST).write_bytes(raw)
record=next(r for r in json.loads(raw)["records"] if r.get("sha256")==spec["document_sha256"])
relative=record["relative_path"]
source=retained/spec["original_subdir"]/relative
p=original/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source.read_bytes())
try:
    report=runner.run(landing_root=landing,reader_root=pathlib.Path(reader),document_evidence_path=pathlib.Path(evidence),
                      ocr_layout_proof_path=pathlib.Path(proof),admission_completed_at=completed,spec=spec)
    report["landing_root"]="<ISOLATED>"
    result={"report":report}
except Exception as exc:
    result={"exception_type":type(exc).__name__,"reason":str(exc).replace(str(landing),"<ISOLATED>")}
target=landing/spec["new_subdir"]
result["output_sha256"]={str(p.relative_to(target)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob("*")) if p.is_file()}
print(json.dumps(result,ensure_ascii=True,sort_keys=True))
'''


def retained_parity_report(retained: Path, reader: Path):
    """Explicit offline script entry; never writes to retained inputs or certifies synthetic data."""
    from stocklookup_core.evidence.dual_reader_transcription import PROOF_DIR
    entries = {}
    for key, spec in runner.SPECS.items():
        target = retained / spec["new_subdir"]
        sealed = target / PROOF_DIR / spec["page_key"] / "agreement.proof.json"
        evidence = target / "document_level_evidence.json"
        missing = [str(p.relative_to(retained)) for p in (sealed, evidence) if not p.is_file()]
        required = [reader / spec["image"], reader / spec["render_meta"], *(reader / r[1] for r in spec["readings"])]
        missing += [str(p.relative_to(reader)) for p in required if not p.is_file()]
        if missing:
            entries[key] = {"status": "REAL_REPLAY_NOT_CERTIFIED", "reason": "Required retained inputs or original completion instant unavailable", "missing": missing}
            continue
        completed = json.loads(sealed.read_bytes())["admission_completed_at"]
        ocr = target / json.loads(evidence.read_bytes())["ocr_layout_proof"]["relative_path"]
        if not ocr.is_file():
            entries[key] = {"status": "REAL_REPLAY_NOT_CERTIFIED", "reason": "Retained OCR proof unavailable", "missing": [str(ocr.relative_to(retained))]}
            continue
        original_manifest = retained / spec["original_subdir"] / runner.MANIFEST
        record = next(item for item in json.loads(original_manifest.read_bytes())["records"]
                      if item.get("sha256") == spec["document_sha256"])
        input_paths = {"original_manifest": original_manifest,
                       "document": retained / spec["original_subdir"] / record["relative_path"],
                       "original_seal": sealed, "document_evidence": evidence, "ocr_proof": ocr,
                       **{"reader_input_" + str(i): path for i, path in enumerate(required)}}
        input_hashes = {role: hashlib.sha256(path.read_bytes()).hexdigest() for role, path in input_paths.items()}
        results = []
        with tempfile.TemporaryDirectory(prefix="registry-parity-") as temp:
            for mode in ("base", "active"):
                landing = Path(temp) / mode
                process = subprocess.run([sys.executable, "-B", "-c", _REPLAY_CHILD, str(ROOT), mode, key, str(landing),
                    str(retained), str(reader), str(evidence), str(ocr), completed], cwd=ROOT, capture_output=True, text=True, encoding="utf8")
                if process.returncode:
                    results.append({"process_failure": process.stderr})
                else:
                    results.append(json.loads(process.stdout))
        inputs_unchanged = input_hashes == {role: hashlib.sha256(path.read_bytes()).hexdigest() for role, path in input_paths.items()}
        equal = results[0] == results[1] and inputs_unchanged
        dependencies = [name for name in ("pypdf", "fitz") if importlib.util.find_spec(name) is None]
        complete = equal and "report" in results[0] and not dependencies
        # A deterministic rejection is comparable, but missing dependencies are not a real admission replay.
        status = "CERTIFIED" if complete else "REAL_REPLAY_NOT_CERTIFIED"
        entries[key] = {"status": status, "reason": "All output bytes/hashes and complete report (facts, citations, admissions, rejections) equal to base" if complete else ("Replay dependencies unavailable: " + ", ".join(dependencies) if dependencies else "Replay incomplete or unequal"),
                        "missing_dependencies": dependencies, "inputs_sha256": input_hashes, "inputs_unchanged": inputs_unchanged, "original_completion_at": completed, "equal": equal, "base": results[0], "active": results[1]}
        print(key, status, flush=True)
    return {"schema_version": 1, "base_commit": BASE, "synthetic_admission_evidence": False, "specs": entries}


def test_daily_capacity_never_enumerates_or_hashes_offline_manifests(monkeypatch):
    from tools import check_owner_daily_host_preflight as preflight
    calls = []
    def git(root, *args):
        calls.append(args)
        return "config/official_financial_layouts/r0001.json\nconfig/official_financial_issuers/r0001.json\nconfig/dual_reader_admissions/r0001.json"
    monkeypatch.setattr(preflight, "_git", git)
    paths = preflight.capacity_source_paths(ROOT)
    assert ":(exclude)config/dual_reader_admissions/**" in calls[0]
    assert paths == [layouts.ISSUER_SNAPSHOT, layouts.LAYOUT_SNAPSHOT]
    # The shared loader and its import closure have no offline default, scan or import.
    shared = (ROOT / "stocklookup_core/evidence/official_ocr_layout_proof.py").read_text(encoding="utf8")
    assert "config/dual_reader_admissions" not in shared
    daily = (ROOT / "tools/run_owner_daily.py").read_text(encoding="utf8")
    assert "run_dual_reader_transcription_admission" not in daily
    assert "config/dual_reader_admissions" not in daily
    from test_daily_lazy_import_closure import daily_reachable
    assert "tools.run_dual_reader_transcription_admission" not in daily_reachable(ROOT)


@pytest.mark.parametrize("target", ["source", "archive", "manifest"])
def test_layout_source_transition_refuses_tampering(tmp_path, target):
    from tools.verify_retention_reader_transition import historical_bytes, REGISTRY_LAYOUT_TRANSITION
    source = "stocklookup_core/evidence/official_ocr_layout_proof.py"
    manifest = json.loads((ROOT / REGISTRY_LAYOUT_TRANSITION).read_bytes())
    for relative in (source, manifest["archive"], REGISTRY_LAYOUT_TRANSITION):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    relative = {"source": source, "archive": manifest["archive"], "manifest": REGISTRY_LAYOUT_TRANSITION}[target]
    path = tmp_path / relative
    if target == "manifest":
        manifest["release_authority"] = "GRANTED"
        path.write_text(json.dumps(manifest), encoding="utf8")
    else:
        path.write_bytes(path.read_bytes() + b"# tampered\n")
    with pytest.raises(ValueError, match="REGISTRY_SNAPSHOT_SOURCE_TRANSITION_"):
        historical_bytes(tmp_path, source)



def test_parity_report_covers_every_frozen_spec_without_synthetic_certification():
    baseline = json.loads(BASELINE.read_bytes())
    report = json.loads((ROOT / "tests/fixtures/registry_migration_v1/parity_report.json").read_bytes())
    assert report["base_commit"] == baseline["base_commit"]
    assert report["synthetic_admission_evidence"] is False
    assert report["specs"].keys() == baseline["specs"].keys()
    for entry in report["specs"].values():
        assert entry["status"] in {"CERTIFIED", "REAL_REPLAY_NOT_CERTIFIED"}
        if entry["status"] == "CERTIFIED":
            assert entry["equal"] and entry["inputs_unchanged"]
            assert entry["base"] == entry["active"] and not entry["missing_dependencies"]
            assert entry["original_completion_at"] and entry["inputs_sha256"]
        else:
            assert entry["reason"]
