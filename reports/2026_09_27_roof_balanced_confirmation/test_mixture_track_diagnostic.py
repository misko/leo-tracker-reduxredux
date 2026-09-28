from types import SimpleNamespace
import math
import time

import numpy as np
import pytest

from mixture_track_diagnostic import (
    TrackDiagnosticEvaluator, posterior_summary, runner)
from paired_reception_evaluator import PairedEvaluator


def fixture():
    origin = (37.8, -122.4)
    receiver = np.asarray(runner.base.point(*origin).ecef_km)
    banks, blocks, reception = {}, [], {}
    for track_id, times in ((11, [0., .2, .5, .8]),
                            (22, [0., 1., 2., 3.])):
        track = SimpleNamespace(
            track_id=track_id, times_s=np.asarray(times),
            measured_hz=np.array([0., 10., 20., 30.]),
            training_mask=np.array([True, True, False, False]))
        positions = np.stack([np.tile(receiver + shift, (4, 1))
            for shift in ([100., 300., 200.], [-100., -300., 200.])])[:, None]
        banks[track_id] = SimpleNamespace(source=track, position_km=positions)
        # Prediction order deliberately differs from bank storage order.
        for candidate, predicted in ((200, [0., 9., 18., 27.]),
                                     (100, [0., 11., 22., 33.])):
            blocks.append(SimpleNamespace(
                track_id=track_id, candidate_ids=np.array([candidate]),
                predictions_hz=np.asarray(predicted, float)[None, None, :],
                visible=np.array([True])))
        reception[track_id] = [dict(
            observation_index=index, matched=True,
            detection_logit_east0=.2, detection_east_slope=1.,
            ratio_mean_east0=.1, ratio_east_slope=.5,
            log_margin_ratio_rx1_rx0=.3) for index in (2, 3)]
    variants = {"old": (reception, .2), "clone": (reception, .2)}
    return origin, banks, blocks, reception, variants


def evaluator(kind):
    origin, banks, blocks, reception, variants = fixture()
    value = kind.__new__(kind)
    value.banks = banks
    value.index = {track_id: {100: 0, 200: 1} for track_id in banks}
    value.origin = origin
    value.predictions = lambda east, north: blocks
    value.parameters = {"scale_hz": 100., "degrees_of_freedom": 2.}
    value.cache = {}; value.started = time.monotonic()
    value.reception = reception; value.ratio_variance = .2
    value.variants = variants
    return value


def test_aggregate_matches_paired_with_reordered_candidates_and_weights():
    paired = evaluator(PairedEvaluator)
    diagnostic = evaluator(TrackDiagnosticEvaluator)
    expected = paired.evaluate(0., 0.)
    actual = diagnostic.evaluate(0., 0.)
    assert actual["weight_seconds"] == expected["weight_seconds"] == 5
    assert actual["variant_scores"].keys() == expected["variant_scores"].keys()
    for name in actual["variant_scores"]:
        assert actual["variant_scores"][name] == pytest.approx(
            expected["variant_scores"][name], abs=1e-12)
    assert [row["weight_seconds"] for row in actual["tracks"]] == [1, 4]
    assert all(row["reserve_observations"] == 2 for row in actual["tracks"])
    assert all(row["candidate_ids"] == [200, 100] for row in actual["tracks"])
    for variant, aggregate in actual["variant_scores"].items():
        for arm, score in aggregate.items():
            reconstructed = sum(
                row["weight_seconds"] * row["variants"][variant]["scores"][arm]
                for row in actual["tracks"]) / actual["weight_seconds"]
            assert reconstructed == pytest.approx(score, abs=1e-12)
    assert diagnostic.evaluate(0., 0.) is actual


def test_old_variant_matches_original_evaluator():
    original = evaluator(runner.frozen.original.RobustBranchEvaluator)
    diagnostic = evaluator(TrackDiagnosticEvaluator)
    expected = original.evaluate(0., 0.)
    actual = diagnostic.evaluate(0., 0.)
    assert actual["variant_scores"]["old"] == pytest.approx(
        expected["scores"], abs=1e-12)


def test_posteriors_normalize_and_clone_variants_match():
    result = evaluator(TrackDiagnosticEvaluator).evaluate(0., 0.)
    for track in result["tracks"]:
        summary = track["training_prior"]
        assert sum(summary["probabilities"]) == pytest.approx(1.)
        assert math.exp(summary["entropy_nats"]) == pytest.approx(
            summary["effective_candidates"])
        old = track["variants"]["old"]
        clone = track["variants"]["clone"]
        assert old == clone
        assert sum(np.exp(old["frequency_posterior_log_weights"])) == pytest.approx(1.)
        assert sum(np.exp(old["joint_posterior_log_weights"])) == pytest.approx(1.)
        scores = old["scores"]
        assert old["detection_score_increment"] == pytest.approx(
            scores["D_plus_detection"] - scores["D"])
        assert old["conditional_ratio_score_increment"] == pytest.approx(
            scores["D_plus_geometry"] - scores["D_plus_detection"])


def test_posterior_fixture_distinguishes_prior_frequency_and_joint_identity():
    ids = [10, 20]
    prior = posterior_summary(ids, [math.log(.9), math.log(.1)])
    frequency = posterior_summary(ids, [math.log(.9) - 5., math.log(.1)])
    joint = posterior_summary(ids, [math.log(.9) - 5., math.log(.1) - 10.])
    assert prior["map_candidate_id"] == 10
    assert frequency["map_candidate_id"] == 20
    assert joint["map_candidate_id"] == 10
    for summary in (prior, frequency, joint):
        assert sum(summary["probabilities"]) == pytest.approx(1.)


def test_single_candidate_summary_is_strict_json_finite():
    summary = posterior_summary([7], [-1000.])
    assert summary["map_candidate_id"] == 7
    assert summary["top_log_weight_margin"] is None


def test_posterior_rejects_duplicate_ids_or_nonfinite_evidence():
    with pytest.raises(ValueError):
        posterior_summary([1, 1], [0., 0.])
    with pytest.raises(ValueError):
        posterior_summary([1, 2], [0., float("nan")])
