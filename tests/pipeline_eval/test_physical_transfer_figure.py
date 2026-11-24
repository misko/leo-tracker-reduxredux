import pytest

from reports.ALGO08.v3.physical_transfer_figure import gates


def test_paired_median_and_total_charge_the_actual_recording_lengths():
    assert gates([(1, .2), (3, 2.4)]) == pytest.approx(dict(median_fraction=.5, summed_fraction=.65))
    with pytest.raises(ValueError):
        gates([(0, 2)])
