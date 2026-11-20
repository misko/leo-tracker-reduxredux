import csv
from collections import Counter
from shutil import copyfile
from types import SimpleNamespace
from zipfile import ZipFile

import numpy as np
import pytest

from tools.pipeline_eval.qualification import multi_session_results as results
from tools.pipeline_eval.qualification import multi_session_stage as stage
from tools.pipeline_eval.qualification import receiver_core_pack as pack
from tools.pipeline_eval.variants import multi_session as model
from tools.pipeline_eval.variants import trackless_likelihood as rate


def test_zero_slope_reproduces_the_existing_anonymous_mixture():
    predicted = np.array([[-60.0, 20.0], [0.0, 95.0]])
    weight = np.array([[0.8, 0.0], [1.0, 0.5]])
    observations = np.array([[1.0, 3.0], [13.2, 0.0]])
    keep = np.array([[True, True], [True, False]])
    sigma = np.array([100.0, 130.0])
    support = np.array([60_000.0, 80_000.0])
    expected = rate.mixture(predicted, weight, observations, keep, sigma, support)[0]
    measured = model.rate_advantage(
        predicted, weight, observations, keep, sigma, support, np.zeros(len(sigma))
    )
    np.testing.assert_allclose(measured, expected, atol=1e-12, rtol=0)


def test_same_lane_wrapped_difference_cancels_fixed_calibration_and_constant_lo():
    def row(time, cfo, offset):
        return dict(
            receiver_id=3,
            channel=2,
            actual_rf_hz=11e9,
            valid_start_counter=int(time * 10000),
            candidates=[
                dict(
                    fractional_margin=0.4,
                    candidate_rank=1,
                    fractional_tracking_cfo_hz=cfo + offset,
                    passed_fractional_margin_gate=True,
                )
            ],
        )

    original = [row(0.24, 1200, 0), row(2.24, -3400, 0)]
    offset = [row(0.24, 1200, rate.PERIOD + 800), row(2.24, -3400, rate.PERIOD + 800)]
    a, b = (
        rate.slices(
            SimpleNamespace(probes=rows, probe_ms=20, first_counter=0, sample_rate_hz=10000)
        )
        for rows in (original, offset)
    )
    np.testing.assert_allclose(a[0].rates, b[0].rates, atol=1e-10, rtol=0)


def test_clock_posterior_uses_train_and_does_not_share_slope_between_sessions():
    train_early, train_late = np.array([[40.0, 0.0, 0.0]]), np.array([[0.0, 0.0, 40.0]])
    held_early, held_late = np.array([[10.0, 0.0, 0.0]]), np.array([[0.0, 0.0, 12.0]])
    early = model.marginal(train_early, held_early)
    late = model.marginal(train_late, held_late)
    incorrectly_shared = model.marginal(train_early + train_late, held_early + held_late)
    assert early[0] + late[0] > incorrectly_shared[0] + 30
    assert early[1] == pytest.approx(10.0)
    assert late[1] == pytest.approx(12.0)


def fixture_rows():
    center = [0.0, 0.0]
    sites, _ = model.design(center)
    cells = list(sites)

    def session(group, training_winner, held_winner):
        train, held = np.zeros(len(cells)), np.zeros(len(cells))
        train[cells.index(training_winner)] = 5
        held[cells.index(held_winner)] = 2
        return dict(
            group=group,
            status="ok",
            tile=dict(center=center, width_km=25),
            profile=dict(
                cells=cells, train=[train, train], held=[held, held], train_epochs=1, held_epochs=1
            ),
        )

    return [session("early", (0, 0), (0, 0)), session("late", (10, 0), (50, 0))]


def test_forward_choice_is_frozen_and_includes_a_later_exterior_rival():
    rows = fixture_rows()
    decisions = {(r["offer"], r["method"]): r["result"] for r in results.stationary(rows)}
    a = decisions["containing", "early_group"]
    b = decisions["containing", "late_group"]
    assert a["metrics"]["selected_offset_km"] == [0, 0]
    assert a["metrics"]["later_held"]["lead"] == -2
    assert a["metrics"]["later_held"]["winner_outside"] is True
    assert b["metrics"]["selected_offset_km"] == [10, 0]
    assert b["metrics"]["early_held"]["lead"] == -2
    assert a["arms"]["c0"] == a["arms"]["fitted_c"]
    assert decisions["near_missing", "center"]["metrics"]["selected_offset_km"] == [20, 0]
    assert decisions["containing", "all_sessions"]["status"] == "withheld"


def test_failed_session_stays_a_failed_single_comparison():
    early, late = fixture_rows()
    late.update(status="timed_out", profile=None)
    decisions = {(r["offer"], r["method"]): r["result"] for r in results.stationary([early, late])}
    assert decisions["containing", "session_2"]["status"] == "unavailable"
    assert decisions["containing", "session_2"]["arms"]["c0"]["forced_latlon"] is None
    assert decisions["containing", "all_sessions"]["status"] == "withheld"


def test_stationary_stage_export_round_trips_the_existing_support_figure(tmp_path):
    source = results.trial.OUT
    evidence = tmp_path / "evidence"
    report = evidence / "multi-session"
    report.mkdir(parents=True)
    for name in (
        "score-lock.json",
        "scores.csv",
        results.DECISIONS,
        results.DECISION_LOCK,
        results.trial.LOCK,
        results.trial.PLAN,
        results.trial.PROFILES,
        stage.IMAGE,
        stage.PDF,
    ):
        copyfile(source / name, report / name)

    stage.export(report)
    for name in (stage.TABLE, stage.DESCRIPTOR, stage.STAGE_SEAL):
        assert (report / name).read_bytes() == (source / name).read_bytes()
    with (report / stage.TABLE).open(newline="") as stream:
        points = list(csv.DictReader(stream))
    assert len(points) == 45
    assert Counter(point["held_group"] for point in points) == {"all": 36, "late": 9}
    assert {point["acquisition"] for point in points if point["held_group"] == "late"} == {
        "1",
        "2",
        "3",
    }
    assert all(point["mean_held_log_score_lead"] for point in points)

    destination = tmp_path / "pack"
    (entry,) = pack.build(evidence, out=destination)
    assert entry.panel_id == "stationary-support"
    with ZipFile(destination / pack.ZIP) as book:
        for name in (stage.TABLE, stage.IMAGE, stage.PDF):
            assert book.read(f"stage-charts/{name}") == (report / name).read_bytes()
