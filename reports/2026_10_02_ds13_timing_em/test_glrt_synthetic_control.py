import numpy as np
from finite_set_likelihood import DEFAULT_ALIAS_HZ, prepare_finite_set_likelihood
from glrt_synthetic_control import simulate_peaks


def test_synthetic_generation_is_seeded_and_preserves_duplicate_peak_count():
    prepared = prepare_finite_set_likelihood([0., DEFAULT_ALIAS_HZ, 1000.], [0, 0, 1])
    predicted = np.array([[25.], [25.], [25.]])
    association = np.array([[.9], [.1]])
    first, injected = simulate_peaks(prepared, predicted, association, seed=101)
    second, repeated = simulate_peaks(prepared, predicted, association, seed=101)
    np.testing.assert_array_equal(first, second)
    assert first[0] == first[1]
    assert injected == repeated == [{"peak_index": 0, "satellite_column": 0}]
    assert prepare_finite_set_likelihood(first, [0, 0, 1]).unique_peak_count == 2
