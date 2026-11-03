"""Report-only scientific denominator and membership checks."""

import copy
import hashlib
import json

import pytest

from evaluate_ds23_combined_recovery_full import (
    ARMS,
    METHODS,
    check_endpoint_replay,
    compare_memberships,
    independent_counts,
    measured_runtime,
    summarize_rows,
)


def test_unique_original_winners_and_partial_tracks_are_counted_separately():
    observations = [{"observation_id": key} for key in ("a", "b", "c", "d")]
    tracks = [{"key": "first", "observation_ids": ["a", "b", "c"]},
              {"key": "second", "observation_ids": ["d", "additional"]}]
    accepted = [dict(component="first", compatible=True, points=2,
                     observation_ids=["b", "c"], norad=1),
                dict(component="second", compatible=True, points=2, norad=2)]
    counts = independent_counts(accepted, tracks, observations)
    assert counts["associated_original_points"] == 3
    assert counts["associated_original_percent"] == 75
    assert counts["associated_additional_peaks"] == 1
    assert counts["associated_points"] == 4
    assert counts["associated_tracks"] == counts["associated_families"] == 2
    comparison = compare_memberships(
        {"associated_original_observation_ids": ["a", "b"]}, counts)
    assert comparison == dict(newly_associated_original_points=2,
                              no_longer_associated_original_points=1,
                              retained_original_points=1, net_associated_original_points=1)


def test_duplicate_owners_and_invented_observations_are_rejected():
    observations = [{"observation_id": "a"}]
    tracks = [{"key": "one", "observation_ids": ["a"]},
              {"key": "two", "observation_ids": ["a"]}]
    accepted = [dict(component=key, compatible=True, norad=1) for key in ("one", "two")]
    with pytest.raises(ValueError, match="multiple accepted owners"):
        independent_counts(accepted, tracks, observations)
    accepted[0]["observation_ids"] = ["invented"]
    with pytest.raises(ValueError, match="absent from its graph track"):
        independent_counts(accepted[:1], tracks, observations)
    with pytest.raises(ValueError, match="unique observations"):
        independent_counts([], tracks, observations * 2)


def test_full_population_denominator_and_point_weighted_coverage():
    rows = []
    for method in METHODS:
        for arm in ARMS:
            for total, associated, error in ((10, 10, .2), (100, 10, .8)):
                rows.append(dict(method=method, arm=arm, status="accepted",
                    position_error_km_report_only=error, original_GLRT_points=total,
                    associated_original_points=associated,
                    associated_original_percent=100 * associated / total,
                    associated_tracks=1, associated_families=1))
    result = summarize_rows(rows, population=3)["combined_recovery"]["c0"]
    assert result["position"]["failures_or_pending"] == 1
    assert result["position"]["fraction_all_recordings_below_half_km"] == 1 / 3
    assert result["association"]["mean_scan_association_percent"] == 55
    assert result["association"]["point_weighted_original_association_percent"] == 100 * 20 / 110


def test_objective_and_gates_must_replay_independently():
    saved = dict(negative_twice_elbo=100., endpoint_latlon=[1., 2.],
                 gates={"tracks": [dict(component="one", compatible=True)]},
                 linear_gates=[])
    fresh = dict(saved, linear_calibration_max_difference=0.)
    assert check_endpoint_replay(saved, fresh, "case", "c0") == 0
    changed = copy.deepcopy(fresh)
    changed["gates"]["tracks"][0]["compatible"] = False
    with pytest.raises(ValueError, match="acceptance gate replay"):
        check_endpoint_replay(saved, changed, "case", "c0")
    changed = dict(fresh, negative_twice_elbo=100.1)
    with pytest.raises(ValueError, match="objective failed"):
        check_endpoint_replay(saved, changed, "case", "c0")
    changed = dict(fresh, linear_calibration_max_difference=1e-3)
    with pytest.raises(ValueError, match="changed calibration"):
        check_endpoint_replay(saved, changed, "case", "c0")


def test_scientific_inputs_reject_a_changed_prepared_graph(tmp_path, monkeypatch):
    import evaluate_ds23_combined_recovery_full as evaluator

    original = tmp_path / "original"
    case = "DS23-test"
    names = [f"{case}/{name}" for name in (
        "tracking.json", "tracks.json", "observations.json", "bank.npz", "radio_noise.json",
        "receipt.json", "nominal_elements.json")]
    names += [f"causal_prior/{case}/{name}" for name in
              ("previous.tle", "previous_receipt.json", "receipt.json")]
    names += [f"causal_phase_history/{case}{suffix}.json" for suffix in ("", "_forecast")]
    expected = {}
    for relative in names:
        path = original / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative)
        expected[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (original / case / "preparation_receipt.json").write_text(json.dumps(dict(
        no_GPS_or_previous_results=True, all_TLEs_causal=True, files_sha256=expected,
        tracking_sha256=expected[f"{case}/tracking.json"])))
    monkeypatch.setattr(evaluator, "ORIGINAL", original)
    assert evaluator.verify_scientific_inputs(original, case)["input_sha256"] == expected
    (original / case / "tracks.json").write_text("changed graph")
    with pytest.raises(ValueError, match="original scientific input changed"):
        evaluator.verify_scientific_inputs(original, case)


def test_legacy_curved_only_record_may_omit_empty_predictive_gates():
    saved = dict(negative_twice_elbo=100., endpoint_latlon=[1., 2.],
                 gates={"tracks": [dict(component="one", compatible=True)]})
    fresh = dict(saved, linear_calibration_max_difference=0., linear_gates=[])
    assert check_endpoint_replay(saved, fresh, "case", "c0") == 0
    fresh["linear_gates"] = [dict(component="predictive", compatible=True)]
    with pytest.raises(ValueError, match="predictive acceptance gate replay changed"):
        check_endpoint_replay(saved, fresh, "case", "c0")


def test_interrupted_checkpoint_seconds_are_not_measured_runtime():
    assert measured_runtime(dict(seconds=90., recovery_pipeline_status="complete"))
    assert measured_runtime(dict(seconds=901., recovery_pipeline_status="budget_exhausted"))
    assert not measured_runtime(dict(seconds=90., recovery_pipeline_status="interrupted",
                                    seconds_is_checkpoint_lower_bound=True))
    assert not measured_runtime(dict(seconds=0., recovery_pipeline_status="interrupted_before_checkpoint",
                                    seconds_is_checkpoint_lower_bound=True))
