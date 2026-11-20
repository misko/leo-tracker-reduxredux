import json

import numpy as np
import pytest

from tools.pipeline_eval.variants import track_reduce


def _track(times, values, channel=1, rf_hz=11.8e9):
    return dict(times=list(times), values=list(values), rf_hz=rf_hz, channel=channel, receiver=1)


def test_reduction_preserves_samples_and_bounds_every_reconstructed_interval():
    times = np.array([0, 0.2, 0.8, 2, 3, 4, 5, 6, 7, 8, 9, 9.5, 10, 11, 12, 13, 14])
    values = 3000 * times - 10 * times**2
    track = _track(times[::-1], values[::-1])
    reduced, metrics = track_reduce._reduce(dict(duration_s=100, tracks=[track]))
    result = reduced["tracks"][0]
    indices = np.searchsorted(times, result["times"])
    error = np.abs(values - np.interp(times, result["times"], result["values"]))

    np.testing.assert_array_equal(np.asarray(result["times"]), times[indices])
    np.testing.assert_array_equal(np.asarray(result["values"]), values[indices])
    assert result["times"][0] == times[0] and result["times"][-1] == times[-1]
    assert dict(result, times=None, values=None) == dict(track, times=None, values=None)
    assert 4 <= len(indices) < 12
    assert error.max() <= 45.0
    assert metrics["max_reconstruction_error_hz"] == pytest.approx(error.max())
    assert metrics["original_rows_with_solver_cap"] == 12
    assert metrics["reduced_rows_with_solver_cap"] == len(indices)


def test_time_bound_keeps_long_gap_and_splits_observed_intervals():
    times = np.r_[0:15, 36:51]
    track = _track(times, 5000 * times)
    reduced, metrics = track_reduce._reduce(dict(duration_s=100, tracks=[track]))
    kept = np.array(reduced["tracks"][0]["times"])

    assert len(kept) < 12
    assert {0.0, 14.0, 36.0, 50.0} <= set(kept)
    interleaving = np.diff(np.searchsorted(times, kept)) > 1
    assert np.max(np.diff(kept)[interleaving]) <= 10.0
    assert metrics["max_reconstructed_span_s"] == np.max(np.diff(kept)[interleaving])


def test_keeps_original_when_bound_or_track_selection_requires_it():
    times = np.arange(20) / 10
    noisy = _track(times, 3000 * (np.arange(20) % 2))
    sorted_times = np.arange(40) / 10
    tied = _track(sorted_times, 5000 * sorted_times, channel=2)
    tied_other = _track(sorted_times, -5000 * sorted_times, channel=3)
    malformed = dict(tied, values=[1])
    observation = dict(duration_s=100, tracks=[noisy, tied, tied_other, malformed])
    reduced, metrics = track_reduce._reduce(observation)

    assert reduced == observation
    assert metrics["tracks_reduced"] == 0
    assert metrics["original_rows_with_solver_cap"] == metrics["reduced_rows_with_solver_cap"]


def test_fixed_rf_coefficient_has_no_effect_on_retained_geometry():
    coefficient = 100_000.0
    times = np.arange(27) / 4
    tracks = [_track(times, 1000 * times + 10 * times**2, rf_hz=10.7e9)]
    second_times = times * 1.1
    tracks.append(_track(second_times, 810 * second_times, rf_hz=12.7e9))
    basis = [track["rf_hz"] / 1e9 - 11.5 for track in tracks]
    biased = [
        dict(track, values=[hz + 300 + coefficient * x for hz in track["values"]])
        for track, x in zip(tracks, basis, strict=True)
    ]
    offsets = [track["values"][0] for track in biased]
    fitted_c = (offsets[1] - offsets[0]) / (basis[1] - basis[0])
    adjusted = [
        dict(track, values=[hz - fitted_c * x for hz in track["values"]])
        for track, x in zip(biased, basis, strict=True)
    ]

    c0, c0_metrics = track_reduce._reduce(dict(duration_s=100, tracks=biased))
    fitted, fitted_metrics = track_reduce._reduce(dict(duration_s=100, tracks=adjusted))

    assert fitted_c == pytest.approx(coefficient)
    assert c0_metrics["tracks_reduced"] == fitted_metrics["tracks_reduced"] == 2
    assert [track["times"] for track in c0["tracks"]] == [
        track["times"] for track in fitted["tracks"]
    ]
    assert c0_metrics["max_reconstruction_error_hz"] == pytest.approx(
        fitted_metrics["max_reconstruction_error_hz"]
    )


def test_reports_measured_control_and_only_publishes_passed_candidate(tmp_path, monkeypatch):
    observation_path = tmp_path / "observation.json"
    catalog_path = tmp_path / "orbit.tle"
    times = list(range(20))
    observation = dict(
        duration_s=50,
        anchor_utc_ns=7,
        cutoff_utc_ns=8,
        catalog_timestamp_ns=7,
        tracks=[_track(times, [1000 * t for t in times])],
    )
    observation_path.write_text(json.dumps(observation))
    catalog_path.write_bytes(b"TLE")
    regions = [dict(id="r", center=[-10, 15])]
    actual = []

    def solve(passed_observation, offered_regions, catalog):
        assert offered_regions == regions and catalog == b"TLE"
        assert dict(passed_observation, tracks=[]) == dict(observation, tracks=[])
        actual.append(passed_observation["tracks"][0]["times"])
        fix = passed_observation["tracks"][0]["times"] == times
        return dict(
            status="fix" if fix else "withheld",
            region_id="r" if fix else None,
            reason="accepted" if fix else "inconsistent_position",
            latlon=[-10, 15] if fix else None,
            best_latlon=[-10, 15],
            diagnostics=dict(work=dict(tiles=1, grid_fits=2), stage_seconds={"input": 0.0}),
        )

    monkeypatch.setattr(track_reduce.receiver, "solve", solve)
    case = dict(observation_path=observation_path, catalog_path=catalog_path, regions=regions)
    result = track_reduce.run(case, tmp_path)

    assert len(actual) == 2 and actual[0] == times
    assert 4 <= len(actual[1]) < len(actual[0])
    assert result["status"] == "withheld"
    assert result["reason"] == "inconsistent_position"
    assert result["arms"]["c0"]["latlon"] is None
    assert result["arms"]["c0"]["forced_latlon"] == [-10, 15]
    assert result["control_arms"]["c0"]["latlon"] == [-10, 15]
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    assert result["metrics"]["control_grid_fits"] == result["metrics"]["candidate_grid_fits"] == 2
    assert result["metrics"]["control_s"] > 0
    assert result["metrics"]["candidate_s"] >= result["metrics"]["reduction_s"] > 0
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_missing_catalog_is_explicitly_unavailable(tmp_path):
    result = track_reduce.run({"observation_path": tmp_path / "tracks.json"}, tmp_path)
    assert result["status"] == "unavailable" and result["reason"]
