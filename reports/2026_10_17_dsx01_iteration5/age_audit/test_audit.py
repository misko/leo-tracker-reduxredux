from audit import element_age_hours


def test_age_uses_element_epoch_and_keeps_future_sign():
    assert element_age_hours(8_000_000_000_000, 4_400_000_000_000) == 1.
    assert element_age_hours(4_400_000_000_000, 8_000_000_000_000) == -1.


def test_integer_epoch_subtraction_preserves_small_difference():
    epoch = 1_792_167_342_609_909_833
    assert element_age_hours(epoch+1, epoch) == 1/3.6e12
