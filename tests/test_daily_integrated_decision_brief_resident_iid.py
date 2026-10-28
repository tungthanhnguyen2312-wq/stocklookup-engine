"""Current-session IID stays resident on the Daily Integrated Decision Brief path."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import canonical_daily_operation
import next_session_decision_brief as next_brief
import stocklookup_core.decision.daily_integrated_decision_brief as brief
from stocklookup_core.evidence.session_paths import fixed_session_artifact_paths
from test_daily_integrated_decision_brief import _record

SESSION = "2026-08-28"
PREVIOUS = "2026-08-27"
DECOY_SESSION = "1999-01-01"
IDENTITY = "integrated_investment_decision_product/v1:resident-fixture"
CONTRACT = "integrated_investment_decision_product/v1"


def _next_brief(**extra):
    payload = {
        "current_session": SESSION,
        "artifact_identity": "next_session_decision_brief/v2:fixture",
        "previous_qualified_session": PREVIOUS,
        "comparison_metadata": {
            "comparison_session": PREVIOUS,
            "binding": "EXACT_PREVIOUS_QUALIFIED_SESSION",
        },
    }
    payload.update(extra)
    return payload


def _product():
    return {
        "session": SESSION,
        "contract_version": CONTRACT,
        "artifact_identity": IDENTITY,
        "records": {
            "MISSING": _record("MISSING", posture="NOT_CLASSIFIED"),
            "FPT": _record("FPT", posture="HOLD"),
        },
        "coverage": {
            "universe_denominator": 2,
            "integrated_context_available": 1,
            "evidence_currency_distribution": {"CURRENT": 1, "MISSING": 1},
        },
    }


def _iid(root: Path, session: str = SESSION) -> Path:
    return fixed_session_artifact_paths(root, session)["integrated_investment_decision_product"]


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _large_iid(path: Path, *, sha: str | None = None) -> None:
    """Pretty head and tail with an invalid middle. A full json.loads cannot succeed."""
    lines = [
        "{",
        f"  \"artifact_identity\": {json.dumps(IDENTITY)},",
    ]
    if sha is not None:
        lines.append(f"  \"artifact_sha256\": {json.dumps(sha)},")
    lines.extend([
        f"  \"contract_version\": {json.dumps(CONTRACT)},",
        "  \"records\": {",
    ])
    prefix = ("\n".join(lines) + "\n").encode()
    suffix = (
        "\n  },\n"
        f"  \"session\": {json.dumps(SESSION)}\n"
        "}\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(prefix + (b"x" * (9 * 1024 * 1024)) + suffix)


def _guard_full_loads(monkeypatch) -> None:
    def guarded(real):
        def wrapped(text, *args, **kwargs):
            if isinstance(text, (str, bytes)) and len(text) > 1_000_000:
                raise AssertionError("current-session IID was deserialized in full")
            return real(text, *args, **kwargs)
        return wrapped

    monkeypatch.setattr(brief.json, "loads", guarded(brief.json.loads))
    monkeypatch.setattr(next_brief.json, "loads", guarded(next_brief.json.loads))


def test_resident_matches_disk_semantics_and_leaves_evidence_unchanged(tmp_path: Path, monkeypatch):
    product = _product()
    current = _iid(tmp_path)
    _write(current, product)
    sidecar = current.with_name("registry-sidecar.json")
    sidecar.write_bytes(b'{"immutable":true}')
    previous = _iid(tmp_path, PREVIOUS)
    _write(previous, {
        "session": DECOY_SESSION,
        "artifact_identity": "integrated_investment_decision_product/v1:decoy",
        "records": {"FPT": {"ticker": "FPT", "research_action_posture": "AVOID"}},
    })
    before = {
        current: current.read_bytes(),
        sidecar: sidecar.read_bytes(),
        previous: previous.read_bytes(),
    }
    opened: list[str] = []
    real_open = Path.open

    def tracking(self, *args, **kwargs):
        opened.append(self.as_posix())
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking)
    args = {"root": tmp_path, "session": SESSION, "next_session_brief": _next_brief()}
    from_disk = brief.build_from_session(**args)
    from_resident = brief.build_from_session(**args, integrated_decision_current=product)
    again = brief.build_from_session(**args, integrated_decision_current=product)

    assert from_disk == from_resident == again
    assert from_resident["artifact_sha256"] == from_disk["artifact_sha256"]
    assert from_resident["previous_qualified_session"] == PREVIOUS
    assert from_resident["comparison_metadata"]["comparison_session"] == PREVIOUS
    assert from_resident["opportunity_sets"]["sets"]["INSUFFICIENT_RESEARCH"]["tickers"] == ["MISSING"]
    assert from_resident["opportunity_sets"]["sets"]["HOLD_MANAGE"]["tickers"] == ["FPT"]
    assert [row["ticker"] for row in from_resident["decision_surface_index"]["rows"]] == ["FPT", "MISSING"]
    assert from_resident["decision_surface_index"]["rows"][1]["research_action_posture"] == "NOT_CLASSIFIED"
    assert from_resident["coverage"]["universe_denominator"] == 2
    assert from_resident["source_artifact_identities"]["integrated_investment_decision_product"] == IDENTITY
    assert previous.as_posix() not in opened
    assert current.read_bytes() == before[current]
    assert sidecar.read_bytes() == before[sidecar]
    assert previous.read_bytes() == before[previous]


def test_preseal_binds_the_file_before_the_resident_brief():
    source = inspect.getsource(canonical_daily_operation._build_preseal_daily_integrated_brief)
    assert source.index("_bind_resident_file(") < source.index("build_from_session(")


def test_large_current_iid_uses_resident_records_without_a_full_decode(tmp_path: Path, monkeypatch):
    current = _iid(tmp_path)
    product = _product()
    _large_iid(current)
    assert current.stat().st_size > 8 * 1024 * 1024
    with pytest.raises(json.JSONDecodeError):
        json.loads(current.read_bytes())
    _guard_full_loads(monkeypatch)
    next_brief._bind_resident_file(current, product)
    artifact = brief.build_from_session(
        root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
        integrated_decision_current=product,
    )
    assert artifact is not None
    assert artifact["opportunity_sets"]["sets"]["INSUFFICIENT_RESEARCH"]["tickers"] == ["MISSING"]
    assert artifact["decision_surface_index"]["denominator"] == 2
    assert artifact["source_artifact_identities"]["integrated_investment_decision_product"] == IDENTITY


def test_missing_current_file_stays_unmaterialized(tmp_path: Path):
    assert brief.build_from_session(
        root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
        integrated_decision_current=_product(),
    ) is None


def test_resident_and_disk_conflicts_fail_closed(tmp_path: Path):
    current = _iid(tmp_path)
    _write(current, _product())
    wrong_session = _product()
    wrong_session["session"] = PREVIOUS
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_SESSION_MISMATCH"):
        brief.build_from_session(
            root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
            integrated_decision_current=wrong_session,
        )
    wrong_contract = _product()
    wrong_contract["contract_version"] = "other/v1"
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_DELIVERY_CONTRACT_MISMATCH"):
        brief.build_from_session(
            root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
            integrated_decision_current=wrong_contract,
        )
    missing_identity = _product()
    missing_identity["artifact_identity"] = ""
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_DELIVERY_IDENTITY_MISSING"):
        brief.build_from_session(
            root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
            integrated_decision_current=missing_identity,
        )
    bad_records = _product()
    bad_records["records"] = []
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_DELIVERY_RECORDS_MISSING"):
        brief.build_from_session(
            root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
            integrated_decision_current=bad_records,
        )
    with pytest.raises(ValueError, match="NEXT_SESSION_BRIEF_SESSION_MISMATCH"):
        brief.build_from_session(
            root=tmp_path, session=SESSION,
            next_session_brief=_next_brief(current_session=PREVIOUS),
            integrated_decision_current=_product(),
        )
    conflict = _product()
    conflict["artifact_identity"] = "integrated_investment_decision_product/v1:other"
    _write(current, conflict)
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_BINDING_IDENTITY_MISMATCH"):
        next_brief._bind_resident_file(current, _product())
    foreign = _product()
    foreign["session"] = PREVIOUS
    _write(current, foreign)
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_ARTIFACT_SESSION_MISMATCH"):
        next_brief._bind_resident_file(current, _product())


def test_large_file_sha_conflict_fails_closed(tmp_path: Path, monkeypatch):
    current = _iid(tmp_path)
    _large_iid(current, sha="a" * 64)
    _guard_full_loads(monkeypatch)
    resident = _product()
    resident["artifact_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="INTEGRATED_DECISION_BINDING_IDENTITY_MISMATCH"):
        next_brief._bind_resident_file(current, resident)


def test_none_posture_is_not_dropped_from_the_issuer_set(tmp_path: Path):
    product = _product()
    product["records"]["MISSING"] = {"ticker": "MISSING", "as_of_session": SESSION, "research_action_posture": None}
    current = _iid(tmp_path)
    _write(current, product)
    before = current.read_bytes()
    with pytest.raises(TypeError):
        brief.build_from_session(
            root=tmp_path, session=SESSION, next_session_brief=_next_brief(),
            integrated_decision_current=product,
        )
    assert current.read_bytes() == before


def test_invalid_small_iid_is_not_swallowed(tmp_path: Path):
    current = _iid(tmp_path)
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        brief.build_from_session(root=tmp_path, session=SESSION, next_session_brief=_next_brief())
    with pytest.raises(ValueError):
        next_brief._bind_resident_file(current, _product())
