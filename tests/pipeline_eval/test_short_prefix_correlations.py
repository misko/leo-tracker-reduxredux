"""Exercise exact prefix boundaries and literal native row identity."""

import numpy as np
import pytest

from reports.ALGO08.v3.short_prefix_correlations import PREFIX, frame_geometry, same_bytes_by_frame


@pytest.mark.parametrize("epoch, offset, ninth, full_count", [
    (0, 0.375, 0, 15),
    (11_000, -0.375, -1, 14),
    (13_332, 0.0, 1, 14),
])
def test_short_workspace_covers_eight_frames_even_when_ninth_class_changes(epoch, offset, ninth, full_count):
    starts, groups, sizes = frame_geometry(epoch, offset)
    np.testing.assert_array_equal(starts[:PREFIX], [epoch+(40_000*f+1)//3 for f in range(PREFIX)])
    np.testing.assert_array_equal(groups[:PREFIX], np.zeros(PREFIX, dtype=np.intc))
    assert groups[PREFIX] == ninth and len(starts) == full_count
    assert set(sizes) == {2816 if offset == 0 else 2831}


def test_both_pilot_rows_must_match_with_native_signed_zero():
    short = np.zeros((2, 8, 64), dtype=np.complex128)
    exact = short.copy()
    exact.view(np.float64)[1, 4, 9] = -0.0
    exact[0, 5, 62] = 1j
    assert same_bytes_by_frame(short, exact) == [True, True, True, True, False, False, True, True]
