import numpy as np
from early_redundancy import learn_pairs, measure


def test_learn_copy_complement_excludes_constant():
    a = np.tile([-1, 1], 12)
    rules = learn_pairs(np.column_stack([a, a, -a, np.ones(24)]))
    assert [(r["i"], r["j"], r["parity"]) for r in rules] == [
        (0, 1, 0), (0, 2, 1), (1, 2, 1)]


def test_parity_and_bias_distinguished():
    a = np.tile([0, 1], 12)
    result = measure(np.column_stack([a, a]), 0)
    assert result["agreement"] == 1
    assert result["independent_baseline"] == .5
    constant = measure(np.zeros((24, 2)), 0)
    assert constant["agreement"] == constant["independent_baseline"] == 1
