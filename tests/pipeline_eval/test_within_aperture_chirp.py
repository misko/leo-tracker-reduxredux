from pathlib import Path
import sys

import pytest
from numpy.polynomial.legendre import Legendre

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from within_aperture_chirp import BIN_HZ, bounds, compare_bounds, exposure, ideal_power
from within_aperture_chirp_readout import local_rates


def factor(epoch, offset=.5):
    return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=offset)


def test_verifier_support_and_distinct_scout_layout():
    short = exposure(factor(20), True)
    full = exposure(factor(20), False)
    edge = exposure(factor(13332), False)
    assert (len(short.centres), len(full.centres), len(edge.centres)) == (5, 15, 14)
    assert short.centres == full.centres[:5]
    assert full.extent[0] == pytest.approx((20+.5+88)/10_000_000)
    assert full.scout_width_s == edge.scout_width_s
    assert full.scout_width_s == pytest.approx(173333/10_000_000)
    assert short.scout_width_s == pytest.approx(53333/10_000_000)
    with pytest.raises(ValueError, match="outside"):
        exposure(factor(200000), False)


@pytest.mark.parametrize("slope", [-8000., 0., 4132., 8000.])
@pytest.mark.parametrize("short", [False, True])
def test_curved_spectral_power_bound_at_multiple_residual_frequencies(slope, short):
    scope = exposure(factor(20), short)
    envelope = bounds(scope, slope)
    for f in (0., BIN_HZ/2, BIN_HZ, BIN_HZ*3, 3551., -3279., 15000., 124000.):
        assert (abs(ideal_power(scope, slope, f)-ideal_power(scope, 0., f))
                <= envelope["uniform_power_bound"] + 2e-15)
    assert 1-ideal_power(scope, slope, 0.) <= envelope["ideal_center_power_loss_bound"] + 2e-15


def test_separates_centroid_linear_offset_and_quadratic_residual():
    full = exposure(factor(20), False)
    short = exposure(factor(20), True)
    result = compare_bounds(full, short, 8000., 1200.)
    assert result["centroid_term_hz"] == pytest.approx(-8000./150, abs=.00008)
    assert result["candidate"]["uniform_power_bound"] < result["installed"]["uniform_power_bound"]
    assert result["centroid_curvature_bound_hz"] < .03
    assert result["centered_carrier_support_bound_hz"] < BIN_HZ/4
    zero = compare_bounds(full, short, 0., 0.)
    assert zero["centroid_curvature_bound_hz"] == zero["centered_carrier_support_bound_hz"] == 0.


def test_piece_derivative_units_and_edges():
    full = exposure(factor(20), False)
    short = exposure(factor(20), True)
    # p(x) = 390 + 100*x + 30*x^2, x = (t - 20)/2.
    p = Legendre((400, 100, 20))
    item = (20., (18., 22., 20., 2., p.deriv(), p.deriv(2), ()))
    slope, curvature = local_rates(item, full, short)
    assert slope == pytest.approx(50+15*(full.centroid-.01))
    assert curvature == 15.
    assert local_rates((18., item[1]), full, short) is None
