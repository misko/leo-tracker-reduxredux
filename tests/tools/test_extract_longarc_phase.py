import numpy as np
import pytest

from tools.research.extract_longarc_phase import frame_opportunities


@pytest.mark.parametrize("rate", [2500000, 10000000, 15000000])
@pytest.mark.parametrize("epoch_s", [0.0, 0.00031, 0.0179])
def test_opportunities_are_complete_adjacent_frames_inside_whole_groups(rate, epoch_s):
    rows = frame_opportunities(round(rate * 0.12), rate, round(epoch_s * rate))
    assert len(rows) == 24
    assert len({start for _, start in rows}) == 24
    content = round(302 * rate * 4.4e-6)
    for group in range(6):
        starts = [start for g, start in rows if g == group]
        assert len(starts) == 4
        assert np.all(abs(np.diff(starts) - rate / 750) < 1)
        assert min(starts) - 1 >= round(group * 0.02 * rate)
        assert max(starts) + content + 1 <= round((group + 1) * 0.02 * rate)
