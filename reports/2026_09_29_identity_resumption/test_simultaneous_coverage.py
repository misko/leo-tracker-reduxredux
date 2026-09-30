import pytest
from simultaneous_coverage import usable_pair


def test_coverage_requires_two_qualified_frames_for_each_same_raw_excerpt():
    def row(frames, digest="a"):
        return dict(visit=3, source=dict(excerpt_sha256=digest), qualified=frames)

    assert usable_pair(row([1, 3]), row([2, 4]))
    assert not usable_pair(row([1, 3]), row([2]))
    with pytest.raises(AssertionError):
        usable_pair(row([1, 3]), row([1, 3], "other"))
