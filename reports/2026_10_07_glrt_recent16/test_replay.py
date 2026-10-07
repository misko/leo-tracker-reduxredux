"""Variable-dwell scheduling and archive coverage must not omit later probes."""

import pytest
from replay import expected_probes, validate_probe_inventory


@pytest.mark.parametrize("rate", [2_500_000, 10_000_000])
@pytest.mark.parametrize("dwell", [120, 240, 360])
def test_every_scheduled_receiver_probe_has_nonoverlapping_confirmation(rate, dwell):
    expected = expected_probes(rate * dwell // 1000, rate)
    assert len(expected) == 2 * (dwell // 120)
    for start in expected.values():
        assert start + 20 <= start + 40
        assert start + 60 <= dwell
    probes = [{"receiver_id": rx, "probe_index": index} for rx, index in expected]
    assert validate_probe_inventory(probes, rate * dwell // 1000, rate) == expected
    with pytest.raises(ValueError, match="inventory"):
        validate_probe_inventory(probes[:-1], rate * dwell // 1000, rate)
    with pytest.raises(ValueError, match="inventory"):
        validate_probe_inventory(probes + probes[:1], rate * dwell // 1000, rate)


def test_reject_noncontract_duration_instead_of_silently_truncating():
    with pytest.raises(ValueError, match="duration"):
        expected_probes(200_001, 2_500_000)
