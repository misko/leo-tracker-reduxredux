from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent


def load_runner():
    name = "native_tradeoff_evaluation_runner"
    sys.path[:0] = [str(HERE.parents[2] / "src"), str(HERE.parent / "tg11"), str(HERE)]
    spec = importlib.util.spec_from_file_location(name, HERE / "run_evaluation.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Nested:
    value: float


def fake_case(**updates):
    values = {
        "id": "case",
        "session": "session",
        "channel": 1,
        "edge": "lower",
        "rate": 2_500_000,
        "tuning_identity": "tuning",
        "calibration_identity": "calibration",
        "source_counter": 100,
        "visit_index": None,
        "sequence_index": 3,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_jsonable_and_hash_are_structural_and_finite() -> None:
    runner = load_runner()
    assert runner.jsonable({"item": Nested(1.25), "tuple": (1, 2)}) == {
        "item": {"value": 1.25}, "tuple": [1, 2]
    }
    assert runner.stable_hash({"b": 2, "a": 1}) == runner.stable_hash({"a": 1, "b": 2})
    try:
        runner.jsonable(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite receipt value was accepted")


def test_native_call_processes_both_receivers_once_and_uses_sequence_index() -> None:
    runner = load_runner()
    calls = []

    class Detector:
        def process(self, raw, key, **kwargs):
            calls.append((raw, key, kwargs))
            return SimpleNamespace(active=False, route="blind_forced", pair=None)

    raw = object()
    result = runner.native_call(Detector(), raw, fake_case(), force_discovery=True)
    assert len(result) == len(calls) == 2
    assert [call[1].receiver for call in calls] == [0, 1]
    assert all(call[2] == {
        "start_counter": 100, "visit_index": 3, "force_discovery": True
    } for call in calls)


def test_stage_membership_is_fixed_and_excludes_reserved_data() -> None:
    runner = load_runner()
    controls = runner.cases_for_stage("controls")
    diagnostic = runner.cases_for_stage("diagnostic")
    real = runner.cases_for_stage("real")
    assert (len(controls), len(diagnostic), len(real)) == (42, 26, 64)
    assert all(case.split == "development" for case in controls + diagnostic + real)
    assert len({case.id for case in controls + diagnostic + real}) == 132
    for session in {case.session for case in real}:
        counters = [case.source_counter for case in real if case.session == session]
        assert counters == sorted(counters)


def assessment(reference: bool, active: bool, matched: bool, outcome: str) -> dict:
    return {
        "reference_active": reference,
        "candidate_active": active,
        "matched_reference": matched,
        "lost_reference": reference and not matched,
        "additional_or_mismatched": active and not matched,
        "physical_outcome": outcome,
        "activity_policy_passed": None,
    }


def test_summary_separates_cpu_speed_quality_routes_and_miss_band() -> None:
    runner = load_runner()
    rows = []
    def decision(route):
        return {
            "route": route, "screened_probe_count": 11,
            "guided_probe_count": 0, "blind_probe_count": 11,
            "proposal_count": 2, "scoring_count": 11,
        }

    for index in range(2):
        rows.append({
            "rate_hz": 2_500_000,
            "cohort": "recorded_real_prefix",
            "timings": {
                "application": {"process_cpu_ms": 100.0, "wall_ms": 101.0},
                "native_blind": {"process_cpu_ms": 10.0, "wall_ms": 11.0},
                "native_tracked": {"process_cpu_ms": 5.0, "wall_ms": 6.0},
            },
            "native_assessments": {
                "native_blind": [assessment(True, True, True, "recorded_unknown_active")],
                "native_tracked": [assessment(True, index == 0, index == 0,
                                                        "recorded_unknown_inactive")],
            },
            "outputs": {
                "native_blind": [decision("blind_forced")],
                "native_tracked": [decision("guided" if index else "blind_cold")],
            },
            "visit_assessments": {
                "native_blind": {"reference_active": True, "candidate_active": True,
                                   "matched_reference": True, "lost_reference_visit": False,
                                   "additional_or_mismatched_visit": False},
                "native_tracked": {"reference_active": True,
                                     "candidate_active": index == 0,
                                     "matched_reference": index == 0,
                                     "lost_reference_visit": index != 0,
                                     "additional_or_mismatched_visit": False},
            },
            "native_method_comparison": [{
                "same_activity": index == 0,
                "tracked_associates_to_blind": index == 0,
            }],
        })
    summary = runner.summarize("real", rows)
    by_rate = summary["by_rate"]["2500000"]
    assert by_rate["methods"]["native_blind"]["aggregate_cpu_speedup_vs_application"] == 10.0
    assert by_rate["methods"]["native_tracked"]["aggregate_cpu_speedup_vs_application"] == 20.0
    assert by_rate["quality"]["native_blind"]["miss_band"] == "0%"
    assert by_rate["quality"]["native_tracked"]["miss_band"] == ">5%"
    assert summary["route_counts"] == {
        "native_blind:blind_forced": 2,
        "native_tracked:blind_cold": 1,
        "native_tracked:guided": 1,
    }


def test_source_inventory_pins_current_scanner_backend_and_native_receipt() -> None:
    runner = load_runner()
    files = runner.source_files()
    backend = Path(runner.acquisition._native_acquisition.__file__).resolve()
    assert str(backend) in files
    assert str((runner.TG11 / "libtg11.so").resolve()) in files
    assert runner.acquisition._folded_anchor_score_grid_backend() != "python"
