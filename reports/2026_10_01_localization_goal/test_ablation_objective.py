import numpy as np
import pytest

from ablation_objective import retained_columns


def test_literal_parameter_removals():
    expected = {'control': [0, 1, 2, 3, 4, 5, 8], 'no_clock': [0, 1, 3, 4, 5, 8],
                'no_drift': [0, 1, 2, 5, 8], 'no_epochs': [0, 1, 2, 3, 4],
                'position_only': [0, 1]}
    for arm, keep in expected.items():
        columns, removed = retained_columns(10, [5, 8], arm)
        assert columns.tolist() == keep
        assert not set(columns) & set(removed)
        state = np.ones(10)
        state[removed] = 0
        state[columns] += 2
        assert np.all(state[removed] == 0)
    with pytest.raises(ValueError):
        retained_columns(10, [5, 8], 'unknown')
