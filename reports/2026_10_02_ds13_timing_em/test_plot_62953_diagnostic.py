import numpy as np

from plot_62953_diagnostic import aggregate_groups, contiguous_group_segments


class Arrays:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


def test_group_aggregation_exposes_probability_split_across_candidate_rows():
    arrays = Arrays(
        {
            "times_s": np.array([1.0, 1.0, 2.0]),
            "group": np.array([10, 10, 11]),
            "receiver": np.array([1, 1, 1]),
            "channel": np.array([3, 3, 4]),
            "posterior": np.array(
                [
                    [0.49, 0.01],
                    [0.47, 0.01],
                    [0.91, 0.01],
                ]
            ),
            "residual_hz": np.array([[20.0, 0.0], [-30.0, 0.0], [40.0, 0.0]]),
        }
    )
    records = aggregate_groups(
        arrays,
        column=0,
        receiver=1,
        seed_groups={10},
        owners={10: {62953}},
        catalog_number=62953,
    )
    split = records[0]
    assert split["target_support"] == 0.96
    assert split["maximum_row_posterior"] == 0.49
    assert split["row_gate"] is False
    assert split["group_gate"] is True
    assert split["best_row"] == 0
    assert split["seed"] is True


def test_group_segments_split_only_at_large_time_gaps():
    records = [
        {"time_s": 0.0, "group": 1, "group_gate": True},
        {"time_s": 2.9, "group": 2, "group_gate": True},
        {"time_s": 3.0, "group": 3, "group_gate": False},
        {"time_s": 6.1, "group": 4, "group_gate": True},
    ]
    segments = contiguous_group_segments(records)
    assert [[record["group"] for record in segment] for segment in segments] == [
        [1, 2],
        [4],
    ]
