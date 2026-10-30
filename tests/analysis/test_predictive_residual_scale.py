import numpy as np
import pytest
from diagnose_predictive_residual_scale import scale_rows


def test_fixed_time_groups_expose_scatter_hidden_by_equal_uncertainty():
    rows = scale_rows(np.arange(8), [-100,100,-100,100,-10,10,-10,10], np.full(8, 50))
    a, b = rows[:2]
    assert a['group'] == 'first_half' and b['group'] == 'second_half'
    assert a['points'] == b['points'] == 4
    assert a['residual_scatter_hz']/b['residual_scatter_hz'] == pytest.approx(10)
    assert a['median_radio_sigma_hz'] == b['median_radio_sigma_hz']
    assert rows[2]['points'] == 8


def test_invalid_noise_scales_are_rejected():
    with pytest.raises(ValueError):
        scale_rows(np.arange(4), np.zeros(4), [1, 1, 0, 1])
