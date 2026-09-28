import numpy as np
from local_reference_parity import measure


def test_fixed_signs_have_no_parity_evidence_above_baseline():
    x = np.ones((20, 3), dtype=np.uint8)
    result = measure(x, 1)
    assert result["agreement"] == result["independent_baseline"] == 1
    assert result["varying_constituents"] == 0


def test_balanced_changing_parity_has_chance_baseline():
    x = np.array([[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=np.uint8)
    result = measure(x, 0)
    assert result["agreement"] == 1 and result["independent_baseline"] == 0.5
    assert result["varying_constituents"] == 3
    assert measure(x[:0], 0)["agreement"] is None
