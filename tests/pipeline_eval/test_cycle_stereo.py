from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from cycle_stereo import keep_slot


def test_causal_cycle_schedule_keeps_anchors_and_whole_donor_sets():
    assert all(keep_slot(i) for i in range(0, 80, 8))
    for cycle in range(10):
        kept = [keep_slot(cycle*8 + slot) for slot in range(1, 8)]
        assert kept == [cycle % 3 != 2] * 7
