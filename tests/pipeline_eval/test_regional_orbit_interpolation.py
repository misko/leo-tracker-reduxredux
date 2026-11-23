from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def interpolation(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import regional_orbit_interpolation

    return regional_orbit_interpolation


def curve(times):
    position = np.broadcast_to((times ** 3 / 2)[None, :, None], (2, len(times), 3)).copy()
    velocity = np.broadcast_to((1.5 * times ** 2)[None, :, None], position.shape).copy()
    return position, velocity, np.ones(2, dtype=bool)


def test_plan_pays_midpoints_and_preserves_the_exact_final_knot(interpolation):
    support, sentinels, paid = interpolation.lattice(np.arange(-11., 9.))
    assert support.tolist() == [0, 8, 16, 19]
    assert sentinels.tolist() == [4, 12, 17]
    assert paid.tolist() == [0, 4, 8, 12, 16, 17, 19]
    assert interpolation.lattice(np.array([1., 2., 4.])) is None


def test_hermite_recovers_cubic_and_its_velocity_on_short_tail(interpolation):
    support = np.array([-2., 6., 8.])
    times = np.arange(-2., 9.)
    p, v, _ = curve(support)
    candidate_p, candidate_v = interpolation.hermite(support, p, v, times)
    actual_p, actual_v, _ = curve(times)
    np.testing.assert_allclose(candidate_p, actual_p, rtol=0, atol=1e-13)
    np.testing.assert_allclose(candidate_v, actual_v, rtol=0, atol=1e-13)
    for original, reconstructed in ((p, candidate_p), (v, candidate_v)):
        np.testing.assert_array_equal(reconstructed[:, [0, 8, 10]].view(np.uint64), original.view(np.uint64))
    with pytest.raises(ValueError, match="within"):
        interpolation.hermite(support, p, v, np.array([9.]))


@pytest.mark.parametrize("error, reason", [(None, None), ("drift", "sentinel_tolerance"),
                                          ("bad_state", "unusable_sampled_orbit"),
                                          ("invalid_time", "incompatible_lattice")])
def test_guard_charges_only_paid_times_or_exact_fallback(interpolation, error, reason):
    calls = []

    def exact(_catalogue, origin, times):
        assert origin == 1234
        calls.append(times.tolist())
        p, v, good = curve(times)
        if len(times) == 5 and error == "drift":
            p[:, 1] += .01
        if len(times) == 5 and error == "bad_state":
            good[1] = False
        return p, v, good

    times = np.arange(12.)
    if error == "invalid_time":
        times[1] = .25
    candidate = interpolation.CoarseBank(exact)
    for actual, expected in zip(candidate([1, 2], 1234, times), curve(times), strict=True):
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-13)
    assert candidate.audit["fallback"] == reason
    if error == "invalid_time":
        assert calls == [times.tolist()]
    else:
        assert calls[0] == [0., 4., 8., 9., 11.]
        assert calls[1:] == ([times.tolist()] if reason else [])
    assert ("full_fallback_cpu_ns" in candidate.audit) == bool(reason)


def test_score_audit_counts_changed_sign_and_owner_even_with_matching_terminal_scores(interpolation):
    base = dict(side="inside", xy_km=[0., 0.], owners={"t": 12345}, score=.3, receiver_scores={"1": .3})
    changed = dict(base, owners={"t": None})
    f, t = np.array([1., 2.]), np.array([.3, .7])
    result = interpolation.lattice_error([(base, (f, np.array([1, 1]), t))],
                                         [(changed, (f, np.array([-1, 1]), t))])
    assert result == dict(frequency_hz=0., tangent_hz_per_s=0., score=0., horizon_signs=1,
                          owner_votes=1, points=1, track_votes=1, orbit_time_cells=2)
