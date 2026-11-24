import numpy as np
import pytest

from reports.ALGO08.v3.offline_slope_hac import BartlettSlope, FLOOR


def test_bartlett_uses_elapsed_gaps_and_matches_index_lags_on_regular_times():
    regular = BartlettSlope(np.arange(8) / 2)
    sparse = BartlettSlope([0., .5, 1., 20., 20.5, 21., 21.5, 22.])
    assert regular.lag == sparse.lag == 2
    assert regular.bandwidth_s == sparse.bandwidth_s == 1.5
    assert regular.kernel[0, :4] == pytest.approx([1, 2/3, 1/3, 0])
    assert np.all(sparse.kernel[:3, 3:] == 0)
    assert np.linalg.eigvalsh(sparse.kernel).min() >= -1e-12


def test_removes_fitted_slope_before_covariance_and_keeps_noise_floor():
    model = BartlettSlope(np.arange(12) / 2)
    residual = 22 + 400*model.x
    result = model.statistic([residual, -residual])
    assert result["slope_hz_per_s"] == pytest.approx([400, -400])
    assert result["numerator_variance"] == pytest.approx([FLOOR**2*model.xx]*2)
    assert result["signed_z"] == pytest.approx(np.array([400, -400])*np.sqrt(model.xx)/FLOOR)


def test_matches_direct_kernel_score_product():
    model = BartlettSlope(np.arange(10))
    r = np.array([160., 280., 0., -90., 310., 900., -420., -600., 10., 90.])
    statistic = model.statistic(r)
    e = r - r.mean() - (r @ model.x)/model.xx*model.x
    score = e*model.x
    direct = len(r)/(len(r)-2)*sum(a*b*model.kernel[i, j]
                                  for i, a in enumerate(score) for j, b in enumerate(score))
    assert statistic["numerator_variance"][0] == pytest.approx(max(FLOOR**2*model.xx, direct))


@pytest.mark.parametrize("times", [[0., 1., 1., 3.], [0., 2., 1., 3.], [0., 1., 2., np.nan], [0., 1., 2.]])
def test_rejects_invalid_timing(times):
    with pytest.raises(ValueError):
        BartlettSlope(times)


def test_rejects_nonfinite_or_mismatched_residuals():
    slope = BartlettSlope([0., 1., 2., 3.])
    for invalid in ([1., 2., 3.], [1., 2., 3., np.inf], [[1., 2.], [3., 4.]]):
        with pytest.raises(ValueError):
            slope.statistic(invalid)
