from hashlib import sha256
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))

from stereo_lane_schedule import StereoSchedule, recipe


@pytest.mark.parametrize("mode, omitted", [
    ("quarter", [(2, 1), (4, 1), (6, 0), (9, 0)]),
    ("target", [(2, 1), (3, 0), (4, 1), (6, 0), (7, 1), (9, 0)]),
])
def test_mask_preserves_stereo_anchors_balances_lanes_and_keeps_an_independent_stream(mode, omitted):
    schedule = StereoSchedule(mode)
    left, right = ("lower", 2, 11_000_000_000), ("upper", 2, 11_000_000_000)
    rows = [schedule.next(left) for _ in range(10)]
    assert [i for i, (aperture, _) in enumerate(rows) if aperture == "full"] == [0, 8]
    assert [(i, radio) for i, (_, radio) in enumerate(rows) if radio is not None] == omitted
    assert schedule.next(right) == ("full", None)
    assert schedule.next(right) == ("short_primary", None)
    assert schedule.next(right) == ("short_primary", 1)
    assert schedule.next(left) == ("short_primary", None)
    assert schedule.next(left) == ("short_primary", 1)


def test_recipe_binds_schedule_bytes_and_parent():
    parent = "sha256:" + "e"*64
    assert recipe("target", parent)["source_sha256"] == sha256((HERE / "stereo_lane_schedule.py").read_bytes()).hexdigest()
    assert recipe("target", parent)["parent_receiver"] == parent
    assert recipe("target", parent) != recipe("quarter", parent)
    with pytest.raises(ValueError, match="original canonical"):
        recipe("target", "e"*64)
