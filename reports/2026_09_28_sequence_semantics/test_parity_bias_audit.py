import numpy as np
from parity_bias_audit import agreement_audit


def test_independent_biased_bits_have_high_agreement_without_excess():
    first, second = np.meshgrid(np.arange(10) == 0, np.arange(10) == 0)
    result = agreement_audit(np.column_stack([first.ravel(), second.ravel()]))
    assert abs(result["observed_agreement"] - 0.82) < 1e-12
    assert abs(result["agreement_excess"]) < 1e-12


def test_equal_balanced_bits_have_excess_agreement():
    result = agreement_audit(np.array([[0, 0], [1, 1]]))
    assert result["observed_agreement"] == 1
    assert result["independent_marginal_agreement"] == 0.5
    assert result["agreement_excess"] == 0.5
