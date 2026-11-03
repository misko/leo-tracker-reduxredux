import numpy as np

from report_ds23_dbg01_iteration_001 import polynomial_segments


def test_graph_legendre_curve_is_folded_to_native_CFO_and_breaks_at_membership_gap():
    # Quadratic Legendre P2(0)=-1/2, whereas ordinary powers would give zero.
    times = np.arange(5.)
    coefficients = [100., 7., 40.]
    canonical = np.polynomial.legendre.legval((times-2.)/2., coefficients)
    shift = 2/4.4e-6
    track = dict(times=times, values=canonical, observation_ids=list('abcde'),
                 pieces=[dict(start_s=0., end_s=4., reference_time_s=2.,
                              time_scale_s=2., coefficients_hz=coefficients)])
    by_id = {key: dict(time_s=t, measured_cfo_hz=y+shift)
             for key, t, y in zip(track['observation_ids'], times, canonical, strict=True)}
    segments = polynomial_segments(track, [0, 1, 3, 4], by_id)
    assert len(segments) == 2
    for grid, native_curve in segments:
        np.testing.assert_allclose(native_curve-shift,
            np.polynomial.legendre.legval((grid-2.)/2., coefficients), atol=1e-8)
    assert polynomial_segments(track, [], by_id) == []
