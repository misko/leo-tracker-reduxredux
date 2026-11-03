import numpy as np
import pytest

from ds23_fft_grid_origin import search_origin, correction, corrected_track_values
from ds23_fft_bias_diagnostic import interpolation_bias
from leo.analysis.starlink.templates import edge_frequencies_hz


def response():
    actual = np.linspace(-250, 250, 1001)
    return dict(step_hz=500., actual_offset_hz=actual,
                reported_offset_hz=actual+15*np.sin(2*np.pi*actual/500))


def test_source_derived_search_origin():
    for edge in ('lower', 'upper'):
        assert max(abs(edge_frequencies_hz(edge))) == 820312.5
    assert search_origin(2500000) == 312.5
    assert search_origin(10000000) == 0.
    for center in (-1500., -500., 500., 1500.):
        assert search_origin(2500000, center) == 312.5
    with pytest.raises(ValueError):
        search_origin(1000000)


def test_inverse_origin_recovers_known_frequencies():
    curve = response()
    truth = np.arange(-100350, 100350, 37.)
    bias = interpolation_bias(truth, curve, 312.5)
    measured = truth+bias
    assert np.max(abs(measured+correction(measured, curve, 312.5)-truth)) < 1e-8
    assert np.sqrt(np.mean((measured+correction(measured, curve, 0)-truth)**2)) > 5


def test_correction_uses_native_not_alias_lifted_frequency():
    native = np.array([-100136., -54321., 100.])
    period = 1/4.4e-6
    values = native+np.array([period, -2*period, 0.])
    track = dict(receiver=1, channel=2, values=values, observation_ids=['a', 'b', 'c'])
    obs = {oid:dict(measured_cfo_hz=f) for oid, f in zip(track['observation_ids'], native)}
    kwargs = dict(observations_by_id=obs, responses={'2500000/lower':response()},
                  edges={(1, 2):'lower'}, sample_rate_hz=2500000,
                  qualified_groups=['fast/2500000/lower'], recording_format='fast')
    result = corrected_track_values(track, **kwargs)
    expected = correction(native, response(), 312.5)
    np.testing.assert_allclose(result[:2]-values[:2], expected[:2], atol=1e-9)
    assert result[2] == values[2]
    assert not np.isclose(expected[0], correction(values[0], response(), 312.5))
    kwargs['qualified_groups'] = []
    np.testing.assert_array_equal(corrected_track_values(track, **kwargs), values)
