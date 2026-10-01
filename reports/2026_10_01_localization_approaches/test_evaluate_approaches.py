from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "localization_approach_evaluator", HERE / "evaluate_approaches.py"
)
assert SPEC and SPEC.loader
EVALUATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATE)


def _attempt(*, accepted: bool = True, arm: str = "A1") -> dict:
    associations = ["101", "background"] if accepted else ["101"]
    best = {
        "mean": [1.0, 2.0, 0.0, 0.0, 0.0],
        "converged": accepted,
        "associations": associations,
    }
    if arm == "B1":
        best["soft_diagnostics"] = {"responsibilities_at_mean": accepted}
    return {
        "receipt_audit": {"passed": True},
        "launch_audit": {"passed": True},
        "receipt": {
            "status": "converged_local_mode" if accepted else "unresolved",
            "planned_factors": 2,
            "best": best,
        },
        "launch": {
            "status": "complete",
            "returncode": 0,
            "within_budget": True,
            "wall_seconds": 10.0,
            "cumulative_seconds": 10.0,
        },
    }


@pytest.mark.parametrize("arm", ["A1", "B1", "C1"])
def test_acceptance_requires_audits_convergence_factor_results_and_budget(arm: str) -> None:
    good = _attempt(arm=arm)
    accepted, failures, _best = EVALUATE._acceptance(good, arm)
    assert accepted and not failures

    variants = (
        ("receipt_audit", {"passed": False}, "receipt_audit_failed"),
        ("launch_audit", {"passed": False}, "launch_audit_failed"),
        ("launch", {**good["launch"], "cumulative_seconds": 181.0}, "cumulative_budget_failed"),
    )
    for key, value, expected in variants:
        bad = {**good, key: value}
        accepted, failures, _best = EVALUATE._acceptance(bad, arm)
        assert not accepted and expected in failures


def test_soft_acceptance_requires_responsibilities_at_returned_mean() -> None:
    attempt = _attempt(arm="B1")
    attempt["receipt"]["best"]["soft_diagnostics"]["responsibilities_at_mean"] = False
    accepted, failures, _best = EVALUATE._acceptance(attempt, "B1")
    assert not accepted
    assert "converged_responsibilities_missing" in failures


def test_discovery_supports_arm_parent_and_direct_folder(tmp_path: Path) -> None:
    arm = tmp_path / "A1"
    arm.mkdir()
    (arm / "DS9-F001.launch.json").write_text(json.dumps({"arm": "A1"}))
    assert EVALUATE.discover_arm_folders(tmp_path) == {"A1": tmp_path}
    assert EVALUATE.discover_arm_folders(arm) == {"A1": arm}


def test_continuation_must_bind_unresolved_primary(tmp_path: Path) -> None:
    parent_path = tmp_path / "primary.json"
    parent_path.write_text("{}")
    primary = {
        "U": {
            "receipt_path": parent_path,
            "receipt": {"status": "unresolved"},
        }
    }
    child = {
        "U": {
            "receipt": {
                "parent": {
                    "path": str(parent_path.resolve()),
                    "sha256": EVALUATE.digest(parent_path),
                }
            }
        }
    }
    merged = EVALUATE._merge_continuation(primary, child)
    assert merged["U"]["primary"] is primary["U"]
    child["U"]["receipt"]["parent"]["sha256"] = "sha256:bad"
    with pytest.raises(ValueError, match="digest mismatch"):
        EVALUATE._merge_continuation(primary, child)


def test_evaluation_retains_64_denominator_and_failure_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    units = [{"unit_id": f"D-F{i:03d}", "session_id": f"s{i}"} for i in range(64)]
    plan_path = tmp_path / "benchmark.json"
    plan_path.write_text(json.dumps({"ordered_units": units}))
    run_root = tmp_path / "runs"
    arm = run_root / "A1"
    arm.mkdir(parents=True)
    monkeypatch.setattr(EVALUATE, "PLAN", plan_path)
    monkeypatch.setattr(EVALUATE, "discover_arm_folders", lambda _path: {"A1": arm})
    monkeypatch.setattr(
        EVALUATE,
        "_attempts",
        lambda _folder, _audit, _plan, _arm: {
            "D-F000": {
                **_attempt(),
                "receipt_path": plan_path,
                "launch_path": plan_path,
            }
        },
    )
    monkeypatch.setattr(EVALUATE, "audit_module", lambda: object())
    helper = SimpleNamespace(
        REFERENCE=(0.0, 0.0),
        latlon_from_enu=lambda east, north: (east, north),
        distance_m=lambda point, reference: 3.0,
    )
    controls = {"primary-evaluation.json": {"rows": [{"unit_id": "D-F000", "error_m": 5.0}]}}
    monkeypatch.setattr(EVALUATE, "_verify_evaluator_authority", lambda: (helper, controls))
    document = EVALUATE.evaluate(run_root)
    assert len(document["rows"]) == 64
    assert document["summaries"]["A1"]["accepted_count"] == 1
    assert document["summaries"]["A1"]["paired_error_delta_median_m"] == -2.0
    assert document["summaries"]["A1"]["failure_inclusive_ecdf"] == [
        {"error_m": 3.0, "fraction_of_64": 1 / 64}
    ]
    assert sum(row["status"] == "not_run" for row in document["rows"]) == 63
