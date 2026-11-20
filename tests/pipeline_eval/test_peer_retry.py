from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import peer_retry_support as support
from tools.pipeline_eval.qualification.peer_retry_results import schedule_bounds
from tools.pipeline_eval.variants import peer_retry


def candidate(epoch, cfo):
    return dict(
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0,
        fractional_tracking_cfo_hz=cfo,
    )


def test_support_uses_one_proposal_and_uses_both_periodicities():
    target = candidate(support.FRAME - 1, 1200)
    close = candidate(0, 1200 + support.ALIAS_HZ + 500)
    result = support.compare(target, [close])
    assert result["epoch_2"]
    assert result["alias_2_1000"]
    assert not result["literal_2_1000"]
    separated = support.compare(target, [candidate(0, 50_000), candidate(40, 1200)])
    assert separated["epoch_2"]
    assert not separated["alias_2_1000"]


@dataclass(frozen=True)
class Geometry:
    fallback_anchor_symbols: tuple


@dataclass(frozen=True)
class Acquisition:
    anchor_symbols: tuple


@pytest.mark.parametrize(
    "mode, expected_anchors",
    [
        ("conditional", [12, 12, 22]),
        ("primary12", [12, 12]),
        ("complement8", [12, 12, 8]),
    ],
)
def test_the_original_peer_gate_controls_the_only_changed_attempt(mode, expected_anchors):
    primary = tuple(range(2, 26, 2))
    wide = tuple(range(2, 46, 2))
    grid = SimpleNamespace(_retain_score_map_peaks=lambda: ((0.5, 74, 80_000),))

    def acquisition(*_args):
        grid._retain_score_map_peaks()
        return SimpleNamespace(
            candidates=[SimpleNamespace(rank=0, refined_epoch_sample=74, absolute_cfo_hz=80_000)]
        )

    def evaluate(probe, configuration, calibration, *, acquisition_config, receiver_id):
        detector.acquire_symbolwise()
        assert probe == receiver_id
        return SimpleNamespace(
            has_fractional_detection=lambda _: receiver_id == 0,
            candidates=tuple(acquisition_config.anchor_symbols),
        )

    detector = SimpleNamespace(_evaluate_probe=evaluate, acquire_symbolwise=acquisition)
    configuration = SimpleNamespace(glrt64_margin_gate=0.025)
    calibration = SimpleNamespace(absolute_cfo_hz=lambda hz: hz)

    def dwell(samples, supplied, *, edge, search_geometry):
        for rx in (0, 1):
            detector._evaluate_probe(
                samples[rx],
                supplied,
                calibration,
                acquisition_config=Acquisition(primary),
                receiver_id=rx,
            )
        if search_geometry.fallback_anchor_symbols:
            detector._evaluate_probe(
                samples[1],
                supplied,
                calibration,
                acquisition_config=Acquisition(search_geometry.fallback_anchor_symbols),
                receiver_id=1,
            )

    analysis = SimpleNamespace(analyze_glrt64_dwell=dwell)
    with peer_retry.route(analysis, detector, grid, mode, trace=True) as attempts:
        analysis.analyze_glrt64_dwell(
            (0, 1), configuration, edge="upper", search_geometry=Geometry(wide)
        )
    assert [len(entry["anchors"]) for entry in attempts] == expected_anchors
    assert [entry["receiver"] for entry in attempts] == [0, 1, 1][: len(expected_anchors)]
    assert [entry["gate"] for entry in attempts[:2]] == [True, False]
    assert [entry["anchors"] for entry in attempts[:2]] == [primary, primary]
    assert attempts[0]["coarse"] == ((0.5, 74, 80_000),)
    assert attempts[1]["acquired"] == ((0, 74, 80_000),)
    if mode == "complement8":
        assert not set(primary) & set(attempts[2]["anchors"])
        assert set(attempts[2]["anchors"]) <= set(wide)
    assert analysis.analyze_glrt64_dwell is dwell
    assert detector._evaluate_probe is evaluate


def test_schedule_keeps_independent_expectation_and_teacher_ceiling_distinct():
    rows = [
        dict(mode="complement8", retry=True, original_positive=number < 5, matched=number == 0)
        for number in range(8)
    ]
    metrics = schedule_bounds(rows)
    assert metrics["expected_matched_probes_if_independent"] == 2
    assert metrics["target_informed_best_case_probes"] == 3
    assert metrics["full_retry_fraction_for_90_percent_retention"] == 0.875
    assert metrics["timed"] is False
