import importlib.util
from pathlib import Path

import numpy as np


PATH = Path(__file__).parents[2] / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/capture-audit/audit_capture.py"
SPEC = importlib.util.spec_from_file_location("capture_audit", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_counter_word_match_preserves_row_coordinate_and_offset():
    start = 10**11
    values = np.zeros((20, 2, 2), dtype="<i2")
    values[7].reshape(4).view("<u8")[0] = start + 7 + 2
    rows, offsets = MODULE.counter_word_matches(values, start)
    assert rows.tolist() == [7]
    assert offsets.tolist() == [2]


def test_intervals_are_half_open_and_coalesced():
    assert MODULE.intervals([2, 3, 8]) == [[2, 4], [8, 9]]
