import numpy as np
import pytest

from reports.ALGO08.v3.polar_projection_trial import relocated_offer, rotate_bank


def test_spin_rotates_position_and_velocity_while_retaining_signed_times():
    bank = dict(time_s=np.array([8.]), position_km=np.array([[[1., 2., 3.]]]),
                velocity_km_s=np.array([[[4., 5., 6.]]]))
    rotated = rotate_bank(bank, 90.)
    assert rotated["time_s"] is bank["time_s"]
    assert np.allclose(rotated["position_km"], [[[-2., 1., 3.]]])
    assert np.allclose(rotated["velocity_km_s"], [[[-5., 4., 6.]]])
    assert np.array_equal(bank["velocity_km_s"], [[[4., 5., 6.]]])
    assert rotate_bank(bank, 0.) is bank


@pytest.mark.parametrize("east, screen_east, target, expected", [(15, 15.5, 179.8, -179.7),
                                                                  (-15, -15.5, -179.8, 179.7)])
def test_relocating_an_offer_wraps_the_existing_screen_translation(east, screen_east, target, expected):
    source = dict(center=(37., east), screen_center=(38., screen_east), width_km=25.)
    moved, _ = relocated_offer(source, target)
    assert moved["center"] == (37., target)
    assert moved["screen_center"] == pytest.approx((38., expected))
    assert moved["width_km"] == source["width_km"]


def test_opposite_screen_is_legal_but_a_seam_crossing_offered_square_is_rejected():
    from leo.contracts.algo08_region import Algo08Region

    original = dict(center=(37.906, -122.545), screen_center=(37.5, -122.0), width_km=25.0)
    moved, _ = relocated_offer(original, 179.8)
    accepted = Algo08Region.parse(moved)
    assert accepted.center[1] > 0 > accepted.screen_center[1]
    crossing, _ = relocated_offer(original, 179.98)
    with pytest.raises(ValueError, match="longitude seam"):
        Algo08Region.parse(crossing)
