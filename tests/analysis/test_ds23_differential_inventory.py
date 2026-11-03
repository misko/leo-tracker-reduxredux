import numpy as np
from inventory_ds23_active_differential_pairs import matching_curve
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_piece_support_and_integer_carrier_alias_are_preserved():
    track=dict(residual_rms_hz=10.,pieces=[dict(start_s=1.,end_s=5.,reference_time_s=3.,time_scale_s=2.,coefficients_hz=[100.,20.])])
    result=matching_curve(track,4.,110.+2*PERIOD)
    assert result is not None and abs(result['error_hz'])<1e-9
    assert matching_curve(track,6.,130.) is None
    assert matching_curve(track,4.,500.) is None


def test_ownership_gate_does_not_inflate_with_a_noisy_polynomial():
    track=dict(residual_rms_hz=1000.,pieces=[dict(start_s=1.,end_s=5.,reference_time_s=3.,time_scale_s=2.,coefficients_hz=[100.])])
    assert matching_curve(track,3.,550.)['limit_hz']==450.
    assert matching_curve(track,3.,551.) is None


def test_differential_information_gain_matches_dense_conditioning():
    from ds23_differential_information import covariance_gain
    rng=np.random.default_rng(841);a=rng.normal(size=(7,7));c=np.linalg.inv(a.T@a+np.eye(7));h=rng.normal(size=7)
    result=covariance_gain(c,h,.3)
    expected=np.linalg.inv(np.linalg.inv(c)+np.outer(h,h)/.09)
    np.testing.assert_allclose(result['covariance'],expected,atol=1e-12)
    assert abs(result['gain_km2']-np.trace((c-expected)[:2,:2]))<1e-12


def test_same_receiver_query_cancels_radio_and_preserves_fragment_slots():
    from types import SimpleNamespace
    from ds23_differential_information import difference_query
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    width=projected_receiver_basis(np.array([100.])).shape[1]
    for fitted in [False,True]:
        p=SimpleNamespace(scan=SimpleNamespace(tracks=[dict(receiver=2,channel=7),dict(receiver=2,channel=7)]),
            members=[0,1],hardware=np.zeros((2,8+int(fitted))),smooth=np.zeros((2,2*width)),
            labels=[11,22],rows=[dict(candidate_index=11),dict(candidate_index=22)],fitted_c=fitted)
        view=difference_query(p,[0,1],100.,12e9)
        np.testing.assert_array_equal(view.hardware[0],view.hardware[1])
        np.testing.assert_array_equal(view.smooth[0],view.smooth[1])
        np.testing.assert_array_equal(view.constants,1000*np.eye(2))
        np.testing.assert_array_equal(view.flat_labels,[0,1])
