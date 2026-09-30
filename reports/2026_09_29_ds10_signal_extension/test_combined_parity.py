import numpy as np
from combined_parity import evaluate


def test_parity_gate_does_not_select_success_and_handles_empty():
    values = np.array([[2, 2, -2], [2, 2, 2], [-2, 2, 2], [.1, .1, .1]])
    result = evaluate(values, 0, 1)
    assert result["count"] == 3
    assert result["agreement"] == 2 / 3
    assert evaluate(values, 1, 3)["count"] == 0
