from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import paired_doppler as physical
from tools.pipeline_eval.variants import paired_doppler_geometry as fit


def capture(*, staggered=False, same_epoch=False):
    probes = []
    for i in range(120):
        t = i * 0.2
        a = (13_000 - 350 * t, 200)
        b = (-20_000 - 480 * t, 200 if same_epoch else 700)
        choices = ([a, b][i % 2],) if staggered else (a, b)
        probes.append(
            dict(
                receiver_id=0,
                channel=2,
                actual_rf_hz=11.3e9,
                probe_start_ms=0,
                valid_start_counter=i * 2_000_000,
                candidates=[
                    dict(
                        candidate_rank=k,
                        fractional_margin=0.5,
                        passed_fractional_margin_gate=True,
                        fractional_tracking_cfo_hz=f,
                        integer_epoch_sample=e,
                        fractional_epoch_offset_samples=0.05,
                    )
                    for k, (f, e) in enumerate(choices)
                ],
            )
        )
    return SimpleNamespace(probes=probes, first_counter=0, sample_rate_hz=10_000_000, probe_ms=20)


def test_simultaneous_two_source_capture_retains_distinct_true_witnesses():
    result = physical.scope(capture())
    assert result["persistent_pairs"] == 1
    assert result["pair_cfo_witnesses"] >= 100
    assert result["simultaneous_distinct_rf_path_windows"] == 0
    assert not result["c_identifiable"]
    pair = result["pairs"][0]["witnesses"]
    assert all(a != b for _, _, _, _, a, b in pair)


@pytest.mark.parametrize("kwargs", [{"staggered": True}, {"same_epoch": True}])
def test_near_time_and_non_distinct_frame_candidates_do_not_become_pairs(kwargs):
    result = physical.scope(capture(**kwargs))
    assert result["linked_arcs"] == 2
    assert result["persistent_pairs"] == 0


def test_same_rf_pair_cancels_arbitrary_clock_and_c_but_distinct_rf_has_a_design():
    t = np.linspace(0, 23, 16)
    a, b = -2700 * t, -1800 * t + 36_000
    arbitrary = 90_000 + 7500 * np.cos(t)
    clean, same = physical.observables(a, b, 11.1e9, 11.1e9)
    noisy, equal = physical.observables(
        a + arbitrary + 88_000, b + arbitrary + 88_000, 11.1e9, 11.1e9
    )
    np.testing.assert_allclose(clean, noisy)
    assert same == equal == 0
    _, cross = physical.observables(a, b, 11.1e9, 11.35e9)
    assert cross == pytest.approx(-0.25)


def test_held_pair_shape_cannot_change_prefix_phase_or_clock_fit():
    t = np.linspace(-1, 1, 16)
    h = np.stack((1200 * t * t, 1200 * t**3), axis=1)[None]
    r = (h @ np.array([1.5, -2.8])) + 123_000
    e, _, phase, _, cost = fit.profile(r, h, 10)
    changed = r.copy()
    changed[:, 10:] += 2500
    held, _, repeated, _, actual = fit.profile(changed, h, 10)
    np.testing.assert_allclose(phase, repeated)
    np.testing.assert_allclose(phase, [[1.5, -2.8]], atol=0.2)
    np.testing.assert_allclose(e[:, :10], held[:, :10])
    np.testing.assert_allclose(e[:, 10:] + 2500, held[:, 10:])
    np.testing.assert_allclose(cost, actual)
