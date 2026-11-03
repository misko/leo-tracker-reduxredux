import numpy as np

from group_summed_viterbi_backfill import recover_group_track


class Arrays:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


def test_group_summed_recovery_retains_split_probability_groups():
    times = np.repeat(np.arange(6, dtype=float), 2)
    groups = np.repeat(np.arange(6), 2)
    posterior = np.tile([[0.48, 0.01], [0.47, 0.01]], (6, 1))
    residual = np.column_stack(
        [np.tile([20.0, -25.0], 6), np.zeros(len(times), dtype=float)]
    )
    arrays = Arrays(
        {
            "catalog_numbers": np.array([10, 20]),
            "times_s": times,
            "group": groups,
            "receiver": np.zeros(len(times), dtype=int),
            "channel": np.ones(len(times), dtype=int),
            "posterior": posterior,
            "residual_hz": residual,
        }
    )
    proposal = {
        "track_index": 0,
        "groups": set(range(6)),
        "group_count": 6,
        "start_s": 0.0,
        "end_s": 5.0,
        "duration_s": 5.0,
        "channels": [1],
    }
    result = recover_group_track(
        arrays,
        column=0,
        receiver=0,
        initial_proposals=[proposal],
        owners={group: {10} for group in range(6)},
    )
    assert result["status"] == "recovered"
    assert result["selected_group_count"] == 6
    assert result["selected_seed_owned_count"] == 6
    assert result["selected_unallocated_count"] == 0
    assert result["viterbi_changed_count"] == 0
