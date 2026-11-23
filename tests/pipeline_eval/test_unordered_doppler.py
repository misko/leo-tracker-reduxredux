import numpy as np

from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.retained_track_likelihood import PERIOD
from reports.ALGO08.v3 import unordered_doppler as scout


def arc(key, receiver, rf, times, values=None):
    times = np.asarray(times, float)
    return scout.Arc(
        key, receiver, 2, rf, times, times[:6],
        np.zeros(6) if values is None else values, np.full(6, 40.),
    )


def test_stereo_pair_requires_same_rf_and_shared_actual_times():
    arcs = [
        arc("left", 1, 11.5e9, range(6)),
        arc("synchronous", 2, 11.5e9, range(4, 10)),
        arc("disjoint", 2, 11.5e9, range(5, 11)),
        arc("other-rf", 2, 11.4e9, range(6)),
    ]
    assert scout.eligible_pairs(arcs) == [(0, 1)]


def test_archived_list_tracks_take_the_original_curvature_gate_and_point_noise():
    from leo.analysis.localization_v3.tracks import active_curvature

    times = list(range(0, 60, 10))
    track = dict(key="saved", receiver=1, channel=2, rf_hz=11.5e9, times=times,
                 values=[float(2 * t**2) for t in times], observation_ids=list("abcdef"))
    noise = dict(extra_parameter_BIC_gain=1.,
                 per_observation_noise_sigma_hz=dict(zip("abcdef", range(40, 46), strict=True)))
    (sampled,) = scout.sample_arcs([track], noise, active_curvature)
    np.testing.assert_array_equal(sampled.sample_times, times)
    np.testing.assert_array_equal(sampled.noise, np.arange(40, 46))


def test_partial_assignment_can_leave_unused_tracks_and_beats_greedy_matching():
    candidates = {(0, 3): -5., (0, 4): -4., (1, 3): -4., (2, 4): 0.}
    assert scout.match(candidates) == [(0, 4), (1, 3)]
    assert scout.match({}) == []


def test_joint_owner_requires_one_feasible_phase_and_keeps_independent_signed_aliases():
    base = np.array([1000., -500., 2000., 700., 1000., 1600.])
    arcs = [arc("left", 1, 11.5e9, range(6), base - PERIOD),
            arc("right", 2, 11.5e9, range(6), base + PERIOD)]
    bank = np.stack([base, np.zeros(6)])
    seen, delta = np.ones((2, 6)), np.zeros((2, 6))
    rows = [scout.terms(item, bank, seen, delta, np.arange(6)) for item in arcs]
    prior, labels = np.ones(2), np.array([101, 202])
    costs, separate = scout.independent(arcs, rows, prior, labels, PERIOD)
    gain, merged, pairs = scout.joint(
        arcs, rows, [(0, 1)], prior, labels, PERIOD, costs, separate,
    )
    assert gain > 0
    assert pairs == [(0, 1)]
    assert [(item["norad"], item["alias"]) for item in merged] == [(101, 1), (101, -1)]

    changed = scout.Terms(
        rows[1].energy, rows[1].cross, rows[1].information,
        np.zeros(2, dtype=bool), rows[1].mean_residual, rows[1].mean_tangent,
    )
    rows[1] = changed
    costs, separate = scout.independent(arcs, rows, prior, labels, PERIOD)
    assert scout.joint(arcs, rows, [(0, 1)], prior, labels, PERIOD, costs, separate) == (
        0., separate, [],
    )


def test_stencil_uses_the_prespecified_region_under_translation():
    region = SearchRegion((47., 16.))
    points = list(scout.stencil(region))
    assert len(points) == 33
    assert len({tuple(p["xy_km"]) for p in points}) == 33
    assert sum(p["side"] == "inside" for p in points) == 17
    assert sum(p["side"] == "exterior" for p in points) == 16
