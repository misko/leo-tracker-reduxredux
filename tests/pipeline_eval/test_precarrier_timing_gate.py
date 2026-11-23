import math

from reports.ALGO08.v3.precarrier_timing_gate import confidence, confident, separability


def test_strict_peak_and_cutoff_ratios():
    assert confident([32, 15, 10, 9.01, 8])
    assert not confident([32, 15, 10, 9, 8])
    assert not confident([16, 15, 10, 9.01, 8])
    assert not confident([32, 15, 10, 9.01, 0])
    assert not confident([math.inf, 15, 10, 9.01, 8])
    assert confidence([18, 15, 10, 9, 8]) == 1.
    assert confidence([18, 15, 10, 9, math.nan]) == 0.


def test_retroactive_cut_charges_safe_ties():
    values = [(0.8, True, True), (1., True, False), (1., False, False), (1.1, False, False)]
    result = separability(values)
    assert result["published"]["false_escalations"] == 0
    assert result["signed_bytes"]["false_escalations"] == 1
    assert result["signed_bytes"]["max_bad"] == 1.
    assert separability([(1., False, False)])["signed_bytes"] is None
