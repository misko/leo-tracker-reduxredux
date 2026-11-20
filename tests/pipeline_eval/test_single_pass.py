from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration
from leo.scanner import fast_scan_detector
from tools.pipeline_eval.qualification import single_pass_results, single_pass_trial
from tools.pipeline_eval.variants import single_pass


@pytest.mark.parametrize(
    ("mode", "attempt_plan", "published"),
    [
        ("conditional", [(0, 12, True), (1, 12, False), (1, 22, True)], [12, 22]),
        ("primary12", [(0, 12, True), (1, 12, False)], [12, 12]),
        ("wide22", [(0, 22, False), (1, 22, True)], [22, 22]),
    ],
)
def test_single_pass_runs_through_capture_dwell(monkeypatch, mode, attempt_plan, published):
    def evaluate(probe, config, calibration, *, acquisition_config, edge, receiver_id, probe_index):
        count = len(acquisition_config.anchor_symbols)
        positive = (receiver_id, count) in ((0, 12), (1, 22))
        candidate = SimpleNamespace(
            fractional_epoch_status="complete",
            fractional_margin=0.03 if positive else 0.01,
            margin=0.0,
            epoch_sample=count,
        )
        return fast_scan_detector._ProbeEvaluation(candidates=(candidate,), hits=())

    monkeypatch.setattr(fast_scan_detector, "_evaluate_probe", evaluate)
    analysis = SimpleNamespace(analyze_glrt64_dwell=fast_scan_detector.analyze_glrt64_dwell)
    geometry = fast_scan_detector.Glrt64SearchGeometry(
        tuple(ReceiverFrequencyCalibration(str(rx), 0.0, "a" * 64) for rx in (0, 1)),
        -800_000.0,
        800_000.0,
        tuple(range(2, 302, 14)),
    )
    setting = SimpleNamespace(
        dwell_samples=2,
        receiver_ids=(0, 1),
        probe_samples=2,
        maximum_acquisition_candidates=8,
        scheduled_probe_count=1,
        probe_stride_samples=2,
        probe_stride_ms=20,
        glrt64_margin_gate=0.025,
        probe_ms=20,
    )
    with single_pass.route(analysis, fast_scan_detector, mode) as attempts:
        result = analysis.analyze_glrt64_dwell(
            np.ones((2, 2), dtype=np.complex64), setting, edge="lower", search_geometry=geometry
        )
    assert attempts == attempt_plan
    assert [p.candidates[0].epoch_sample for p in result.probes] == published
    assert fast_scan_detector._evaluate_probe is evaluate
    assert analysis.analyze_glrt64_dwell is fast_scan_detector.analyze_glrt64_dwell


def probe(positive):
    return {"candidates": [{"passed_fractional_margin_gate": positive}]}


def test_archive_gate_only_does_not_identify_successful_retry_receiver():
    rows = [
        (i, [probe(a), probe(b)])
        for i, (a, b) in enumerate(
            [(False, False), (False, True), (True, False), (True, True), (True, True)]
        )
    ]
    bounds = single_pass_trial.archive_bounds(rows)["retry_bounds"]
    assert bounds == {
        "visit_min": 2,
        "visit_max": 4,
        "rx0_min": 1,
        "rx0_max": 3,
        "rx1_min": 1,
        "rx1_max": 3,
    }
    identified = single_pass_trial.archive_bounds(rows, {0: 0, 1: 1, 2: 1, 3: 1, 4: 0})
    assert identified["retry_bounds"] == {
        "visit_min": 3,
        "visit_max": 3,
        "rx0_min": 1,
        "rx0_max": 2,
        "rx1_min": 1,
        "rx1_max": 2,
    }
    with pytest.raises(ValueError, match="retry bounds"):
        single_pass_trial.archive_bounds(rows, {0: 1, 1: 1, 2: 1, 3: 1, 4: 0})


def test_held_sample_depends_only_on_recording_and_valid_visit_ids():
    visits = list(range(100))
    withheld = {5, 7, 80}
    selected = single_pass_trial.choose("example", visits, withheld)
    assert selected == single_pass_trial.choose("example", reversed(visits), withheld)
    assert len(selected) == single_pass_trial.COUNT
    assert set(selected).isdisjoint(withheld)


def test_compare_aliases_without_hiding_promoted_negatives_or_winner_changes():
    near = dict(
        candidate_rank=0,
        integer_epoch_sample=100,
        fractional_epoch_offset_samples=0.0,
        fractional_tracking_cfo_hz=1000.0,
        fractional_margin=0.3,
        passed_fractional_margin_gate=True,
    )
    aliased = dict(near, fractional_tracking_cfo_hz=1000.0 + 1 / 4.4e-6)
    other = dict(near, integer_epoch_sample=200, candidate_rank=1, fractional_margin=0.4)
    result = single_pass_results.assess([near], [aliased, other], [])
    assert result["held_teacher_any_folded"]
    assert not result["held_teacher_any_literal"]
    assert not result["held_teacher_winning_folded"]
    assert single_pass_results.assess([], [other], [])["teacher_negative_new_positive"]
