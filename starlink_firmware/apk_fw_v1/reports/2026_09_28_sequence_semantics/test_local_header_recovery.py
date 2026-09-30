import numpy as np
from local_header_recovery import score, select_positions


def test_excludes_fixed_coordinates_and_detects_shared_changing_bits():
    rng = np.random.default_rng(929)
    x = rng.choice([-1, 1], size=(200, 2, 12)).astype(complex)
    x[:, :, 0] = 1
    variable, threshold = select_positions(x[:100])
    assert not variable[:, 0].any()
    mask = np.broadcast_to(variable, x[100:].shape)
    matched = score(x[100:], x[100:], mask)
    shifted = score(x[100:], np.roll(x[100:], 1, axis=0), mask)
    assert matched["agreement"] == 1
    assert 0.45 < shifted["agreement"] < 0.55
    assert np.all(threshold == 1)


def test_empty_selection_is_not_evidence_and_constant_baseline_is_one():
    x = np.ones((12, 2, 3), complex)
    assert score(x, x, np.zeros(x.shape, bool))["agreement"] is None
    result = score(x, x, np.ones(x.shape, bool))
    assert result["agreement"] == result["coordinate_baseline"] == 1
