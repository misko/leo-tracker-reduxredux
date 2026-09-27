from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_guided_boundary_run_evaluation", HERE / "run_evaluation.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _point(excess: float = 0.0):
    scoring = 100_000.0
    return {
        "case_id": "case", "rate_hz": 2_500_000, "edge": "lower",
        "receiver": 1, "category": "test", "pair_inventory_index": 3,
        "pair_role": "strongest",
        "coordinate": {
            "receiver": 1, "probe_index": 2, "local_epoch_sample": 77,
            "acquired_cfo_hz": scoring,
            "tracking_cfo_hz": scoring + runner.RESIDUAL_SUPPORT_HZ + excess,
        },
    }


def test_reference_lock_has_exactly_42_fixed_points_without_iq():
    lock, result = runner.load_reference()
    points = runner.point_membership(lock)
    assert len(points) == 42
    assert result["complete"] is True
    assert {item["category"] for item in points} == {
        "k2_blind_lost_reference", "matched_anchor"
    }


def test_control_membership_is_32_controls_plus_10_sequence_occurrences():
    cases = runner.control_cases()
    assert len(cases) == 42
    assert sum(case.sequence_id is None for case in cases) == 32
    assert sum(case.sequence_id is not None for case in cases) == 10
    assert all(case.split == "development" for case in cases)


def test_boundary_classification_uses_positive_one_microhertz_guard_only():
    assert not runner.boundary_classification(_point(-1e-7))["inside_new_guard_only"]
    assert runner.boundary_classification(_point(2e-9))["inside_new_guard_only"]
    assert runner.boundary_classification(_point(9e-7))["inside_new_guard_only"]
    assert not runner.boundary_classification(_point(2e-6))["inside_new_guard_only"]


def test_ordinary_point_requires_science_parity_but_boundary_is_report_only():
    science = {"status": 0, "margin": .2, "total_cpu_ms": 1.0, "total_wall_ms": 2.0}
    same_science = {**science, "total_cpu_ms": 99.0, "total_wall_ms": 88.0}
    ordinary = runner.compare_direct(science, same_science, _point(-10.0))
    assert ordinary["ordinary_point"]
    assert ordinary["ordinary_parity_passed"] is True
    changed = runner.compare_direct(None, science, _point(2e-9))
    assert changed["boundary_outcome_report_only"]
    assert changed["ordinary_parity_passed"] is None


def test_science_comparison_removes_only_timing_fields():
    left = {"status": 0, "nested": {"margin": .3, "total_cpu_ms": 1.0}}
    right = {"status": 0, "nested": {"margin": .3, "total_cpu_ms": 7.0}}
    assert runner.without_timings(left) == runner.without_timings(right)
    right["nested"]["margin"] = .4
    assert runner.without_timings(left) != runner.without_timings(right)


def test_direct_guided_always_calls_api_without_support_precheck():
    class Engine:
        def guided(self, raw, **kwargs):
            self.raw = raw
            self.kwargs = kwargs
            return "called"

    point = _point(10.0)
    engine = Engine()
    assert runner.direct_guided(engine, object(), point) == "called"
    assert engine.kwargs["scoring_cfo_hz"] == point["coordinate"]["acquired_cfo_hz"]
    assert engine.kwargs["expected_physical_cfo_hz"] == point["coordinate"]["tracking_cfo_hz"]


def _observation(probe, start, dwell, *, status=0, cfo=1000.0):
    return {
        "receiver": 0, "probe_index": probe, "probe_start_sample": start,
        "local_epoch_sample": dwell - start, "dwell_epoch_sample": dwell,
        "acquired_cfo_hz": cfo, "tracking_cfo_hz": cfo, "margin": .2,
        "fractional_complete": True, "supported": True, "fitted": False,
        "candidate_index": 0, "exact_score": .3, "control_score": .1,
        "support_frames": 14, "valid_bounds": True, "status": status,
        "total_cpu_ms": .1, "total_wall_ms": .1,
    }


def test_direct_pair_assessment_requires_both_full_native_points_and_identity():
    rows = []
    for member, (probe, start, dwell) in enumerate(((0, 0, 100), (2, 50_000, 50_100))):
        observation = _observation(probe, start, dwell)
        coordinate = {"probe_start_sample": start, "dwell_epoch_sample": dwell,
                      "tracking_cfo_hz": 1000.0}
        rows.append({
            "case_id": "c", "rate_hz": 2_500_000, "receiver": 0,
            "pair_inventory_index": 7, "pair_role": "strongest", "coordinate": coordinate,
            "results": {"original": observation, "guard_1e_6hz": observation},
            "assessments": {
                method: runner.assess_direct_point(observation, coordinate, 2_500_000)
                for method in ("original", "guard_1e_6hz")
            },
        })
    pairs = runner.pair_assessments(rows)
    assert len(pairs) == 1
    assert pairs[0]["methods"]["original"]["accepted"]
    rows[1]["results"]["guard_1e_6hz"] = _observation(2, 50_000, 50_100, status=2)
    rows[1]["assessments"]["guard_1e_6hz"] = runner.assess_direct_point(
        rows[1]["results"]["guard_1e_6hz"], rows[1]["coordinate"], 2_500_000
    )
    assert not runner.pair_assessments(rows)[0]["methods"]["guard_1e_6hz"]["accepted"]


def test_control_assessment_keeps_both_receivers_and_truth_policy():
    cases = runner.control_cases()
    case = cases[0]

    class Decision:
        active = False
        pair = None

    assessment = runner.assess_control((Decision(), Decision()), case)
    assert [item["receiver"] for item in assessment] == [0, 1]
    assert all("activity_policy_passed" in item for item in assessment)


def test_case_tokens_distinguish_repeated_sequence_occurrences():
    sequence = [case for case in runner.control_cases() if case.sequence_id is not None]
    tokens = [runner.case_token(case, index) for index, case in enumerate(sequence)]
    assert len({(item["occurrence_index"], item["sequence_id"], item["sequence_index"])
                for item in tokens}) == len(tokens)


def test_source_inventory_rehashes_all_79_reference_files_and_engine_lock():
    files = runner.source_files()
    reference = runner.json.loads(runner.REFERENCE_LOCK.read_text())["files"]
    assert len(reference) == 79
    assert set(reference).issubset(files)
    assert str((HERE / "ENGINE_LOCK.json").resolve()) in files
    assert str((runner.REFERENCE / "boundary_api_audit.json").resolve()) in files


def test_cli_requires_explicit_action_and_never_names_reserved_splits():
    text = (HERE / "run_evaluation.py").read_text()
    assert "add_mutually_exclusive_group(required=True)" in text
    assert 'actions.add_argument("--run"' in text
    assert '"holdout_opened": False' in text
    assert '"validation_opened": False' in text
