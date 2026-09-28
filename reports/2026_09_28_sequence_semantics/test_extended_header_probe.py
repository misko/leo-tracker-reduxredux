import pytest
from extended_header_probe import frame_split


def test_region_matched_split_is_disjoint_and_excludes_short_regions():
    rows = [
        dict(frame_index=i, binary_like_intervals=[[2, 7 if i == 1 else 10]]) for i in range(10)
    ]
    discovery, evaluation, unused = frame_split(rows, 9)
    assert discovery == [0, 2, 3, 4]
    assert evaluation == [5, 6, 7, 8]
    assert unused == [9]
    with pytest.raises(ValueError):
        frame_split(rows, 11)
