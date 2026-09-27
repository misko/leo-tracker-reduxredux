from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys


HERE = Path(__file__).resolve().parent


def load_runner():
    name = "native_candidates_evaluation_test_module"
    sys.path[:0] = [
        str(HERE.parents[2] / "src"),
        str(HERE),
        str(HERE.parent / "tg11"),
        str(HERE.parent / "native_tradeoff"),
    ]
    spec = importlib.util.spec_from_file_location(name, HERE / "run_evaluation.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Nested:
    value: float


@dataclass(frozen=True)
class RecordedObservation:
    receiver: int
    probe_index: int
    margin: float
    status: int


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
        "visit_index": 2,
        "sequence_index": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_jsonable_hash_and_rotation_are_deterministic() -> None:
    runner = load_runner()
    assert runner.jsonable({"x": Nested(1.5), "y": (1, 2)}) == {
        "x": {"value": 1.5}, "y": [1, 2]
    }
    assert runner.stable_hash({"b": 2, "a": 1}) == runner.stable_hash({"a": 1, "b": 2})
    orders = [runner.rotated_methods("controls", index) for index in range(3)]
    assert {order[0] for order in orders} == set(runner.METHODS["controls"])
    try:
        runner.jsonable(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite value entered a receipt")


def test_fixed_membership_is_development_only_and_disjoint() -> None:
    runner = load_runner()
    groups = {stage: runner.cases_for_stage(stage) for stage in runner.STAGES}
    assert {stage: len(cases) for stage, cases in groups.items()} == {
        "controls": 42, "diagnostic": 26, "real": 64
    }
    all_cases = tuple(case for cases in groups.values() for case in cases)
    assert len({case.id for case in all_cases}) == 132
    assert all(case.split == "development" for case in all_cases)
    for session in {case.session for case in groups["real"]}:
        counters = [
            case.source_counter for case in groups["real"] if case.session == session
        ]
        assert counters == sorted(counters)


def test_native_call_processes_each_receiver_once() -> None:
    runner = load_runner()
    calls = []

    class Detector:
        def process(self, raw, key, **kwargs):
            calls.append((raw, key, kwargs))
            return SimpleNamespace(active=False, route="blind_forced", pair=None)

    values = object()
    result = runner.native_call(
        Detector(), values, fake_case(), force_discovery=True
    )
    assert len(result) == len(calls) == 2
    assert [call[1].receiver for call in calls] == [0, 1]
    assert all(call[2] == {
        "start_counter": 100,
        "visit_index": 2,
        "force_discovery": True,
    } for call in calls)


def test_predecessor_integrity_is_required_but_quality_is_not_a_gate(
    tmp_path, monkeypatch
) -> None:
    runner = load_runner()
    lock = {
        "stages": {
            "controls": {"case_ids": ["a", "b"]},
            "diagnostic": {"case_ids": ["c"]},
        }
    }
    path = tmp_path / "results.controls.json"
    lock_path = tmp_path / "source_lock.json"
    lock_path.write_text(json.dumps(lock))
    monkeypatch.setattr(runner, "SOURCE_LOCK", lock_path)
    monkeypatch.setattr(
        runner,
        "result_path",
        lambda stage: path if stage == "controls" else tmp_path / f"results.{stage}.json",
    )
    payload = {
        "status": "complete",
        "complete": True,
        "source_lock": lock,
        "source_lock_sha256": runner.digest(lock_path),
        "source_lock_stable": True,
        "rows": [{}, {}],
        "summary": {"quality_failures": 99},
    }
    path.write_text(json.dumps(payload))
    prior = runner.predecessor_receipts("diagnostic", lock)
    assert prior[0]["quality_was_not_a_stage_gate"] is True
    payload["complete"] = False
    path.write_text(json.dumps(payload))
    try:
        runner.predecessor_receipts("diagnostic", lock)
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete predecessor was accepted")


def _assessment(reference, active, matched, outcome, policy=None):
    return {
        "reference_active": reference,
        "candidate_active": active,
        "matched_reference": matched,
        "lost_reference": reference and not matched,
        "additional_or_mismatched": active and not matched,
        "physical_outcome": outcome,
        "activity_policy_passed": policy,
    }


def _decision(route):
    return {
        "route": route,
        "screened_probe_count": 11,
        "guided_probe_count": 0,
        "blind_probe_count": 11,
        "proposal_count": 2,
        "scoring_count": 11,
    }


def test_summary_keeps_each_candidate_quality_cost_and_route_separate() -> None:
    runner = load_runner()
    timings = {
        "application": {"process_cpu_ms": 100.0, "wall_ms": 101.0},
        "native_k1_blind": {"process_cpu_ms": 10.0, "wall_ms": 11.0},
        "native_k2_blind": {"process_cpu_ms": 12.5, "wall_ms": 13.0},
        "native_k2_tracked": {"process_cpu_ms": 5.0, "wall_ms": 6.0},
    }
    row = {
        "rate_hz": 2_500_000,
        "timings": timings,
        "native_assessments": {
            method: [_assessment(True, method != "native_k2_tracked",
                                 method != "native_k2_tracked", "recorded_unknown")]
            for method in runner.NATIVE_METHODS
        },
        "visit_assessments": {
            method: {
                "reference_active": True,
                "candidate_active": method != "native_k2_tracked",
                "matched_reference": method != "native_k2_tracked",
                "lost_reference_visit": method == "native_k2_tracked",
                "additional_or_mismatched_visit": False,
            }
            for method in runner.NATIVE_METHODS
        },
        "outputs": {
            method: [_decision("guided" if method == "native_k2_tracked" else "blind_forced")]
            for method in runner.NATIVE_METHODS
        },
        "candidate_comparisons": [{
            "k1_k2_same_activity": True,
            "k2_associates_to_k1": True,
            "k2_tracked_same_activity": False,
            "k2_tracked_associates_to_blind": False,
        }],
    }
    summary = runner.summarize("real", [row])
    rate = summary["by_rate"]["2500000"]
    assert rate["methods"]["native_k1_blind"]["aggregate_cpu_speedup_vs_application"] == 10.0
    assert rate["methods"]["native_k2_blind"]["aggregate_cpu_speedup_vs_application"] == 8.0
    assert rate["methods"]["native_k2_tracked"]["aggregate_cpu_speedup_vs_application"] == 20.0
    assert rate["quality"]["native_k2_tracked"]["lost_reference_receivers"] == 1
    assert summary["route_counts"]["native_k2_tracked:guided"] == 1


def test_source_inventory_pins_local_backend_common_sources_and_both_builds() -> None:
    runner = load_runner()
    files = runner.source_files()
    assert Path(runner.leo.__file__).resolve() == runner.ROOT / "src/leo/__init__.py"
    assert str(Path(runner.acquisition._native_acquisition.__file__).resolve()) in files
    assert str((runner.TRADEOFF / "native_tradeoff_detector.py").resolve()) in files
    for budget in (1, 2):
        assert str((runner.HERE / f"libtg11_candidates_k{budget}.so").resolve()) in files
        assert str((runner.HERE / f"libtg11_candidates_k{budget}.so.build.json").resolve()) in files
    assert runner.acquisition._folded_anchor_score_grid_backend() != "python"


def test_recording_engine_captures_references_and_serializes_after_call() -> None:
    runner = load_runner()
    screen = SimpleNamespace(
        receiver=0,
        windows=(SimpleNamespace(probe_index=0, score=1.0),),
        selected_projection=1,
        projection_contrast=(1.0, 2.0),
        fold_cpu_ms=1.0,
        correlation_cpu_ms=2.0,
        total_cpu_ms=3.0,
        total_wall_ms=4.0,
    )
    observation = RecordedObservation(0, 0, 0.2, 0)

    class Engine:
        def screen(self, raw, *, receiver):
            return screen

        def blind(self, raw, *, receiver, screen):
            return (observation,)

        def guided(self, raw, **kwargs):
            return observation

    recorder = runner.RecordingEngine(Engine())
    returned_screen = recorder.screen(object(), receiver=0)
    returned_blind = recorder.blind(object(), receiver=0, screen=returned_screen)
    returned_guided = recorder.guided(
        object(), receiver=0, probe_index=0,
        predicted_local_epoch_sample=3.5, scoring_cfo_hz=4.0,
        expected_physical_cfo_hz=5.0,
    )
    assert recorder.events[0][1] is screen
    assert recorder.events[1][2] is returned_blind
    assert recorder.events[2][-1] is returned_guided
    serialized = recorder.serialize()
    assert [event["kind"] for event in serialized] == ["screen", "blind", "guided"]
    assert serialized[1]["observations"][0]["margin"] == 0.2
    recorder.reset()
    assert recorder.events == []
