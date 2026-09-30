import numpy as np
from fullband_control_probe import matches, rlc_single_sdu_patterns


def test_incomplete_or_unqualified_patterns_are_not_candidates():
    bits = np.array([1, 0, 1, 0, 0, 1], dtype=bool)
    valid = np.ones(6, dtype=bool)
    count, starts = matches(bits, valid, 3, {0: 1, 2: 1})
    assert count == 4
    assert starts.tolist() == [0]
    valid[1] = False
    assert matches(bits, valid, 3, {0: 1, 2: 1})[1].size == 0
    assert matches(bits[:2], valid[:2], 3, {0: 1})[0] == 0


def test_rlc_length_entry_rejects_wrong_payload_length():

    for name, (length, fixed) in rlc_single_sdu_patterns({"PNT": (40, {0: 1})}).items():
        bits = np.zeros(length, dtype=bool)
        for offset, value in fixed.items():
            bits[offset] = value
        valid = np.ones(length, dtype=bool)
        assert matches(bits, valid, length, fixed)[1].tolist() == [0]
        header = 8 if name.startswith("RLC8_") else 20
        bits[header + 1] = ~bits[header + 1]
        assert matches(bits, valid, length, fixed)[1].tolist() == []
