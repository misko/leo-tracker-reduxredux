import numpy as np
from orbit_backfill_prototype import (
    build_initial_inventory,
    recover_track,
)


class Arrays:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


def test_initial_inventory_tracks_all_owners_but_only_selected_proposals():
    seed = {
        "rough": {
            "assignments": [
                {
                    "accepted": True,
                    "rows": [0, 1],
                    "catalog_number": 10,
                    "receiver": 0,
                    "track_index": 2,
                },
                {
                    "accepted": True,
                    "rows": [2],
                    "catalog_number": 20,
                    "receiver": 1,
                    "track_index": 3,
                },
            ]
        }
    }
    owners, proposals = build_initial_inventory(
        seed,
        raw_group=np.array([4, 5, 6]),
        raw_times=np.array([1.0, 2.0, 3.0]),
        raw_channel=np.array([1, 2, 3]),
        selected_catalogs=[10],
    )
    assert owners == {4: {10}, 5: {10}, 6: {20}}
    assert set(proposals) == {(10, 0)}
    assert proposals[(10, 0)][0]["groups"] == {4, 5}


def synthetic_arrays():
    times = np.array([0.0, 1.0, 2.0, 3.0, 7.5, 8.0])
    posterior = np.column_stack([np.full(len(times), 0.92), np.full(len(times), 0.01)])
    residual = np.column_stack([np.full(len(times), 50.0), np.zeros(len(times))])
    return Arrays(
        {
            "catalog_numbers": np.array([10, 20]),
            "times_s": times,
            "group": np.arange(len(times)),
            "receiver": np.zeros(len(times), dtype=int),
            "posterior": posterior,
            "residual_hz": residual,
        }
    )


def proposal(groups):
    return {
        "track_index": 0,
        "groups": set(groups),
        "group_count": len(groups),
        "start_s": 0.0,
        "end_s": 1.0,
        "duration_s": 1.0,
        "channels": [1],
    }


def test_recovery_adds_unallocated_groups_and_never_steals_contested_group():
    arrays = synthetic_arrays()
    owners = {0: {10}, 1: {10}, 2: {20}}
    result = recover_track(
        arrays,
        0,
        0,
        [proposal({0, 1})],
        owners,
        minimum_seed_groups=2,
    )
    assert result["status"] == "recovered"
    assert result["selected_groups"] == [0, 1, 3]
    assert result["selected_seed_owned_count"] == 2
    assert result["selected_unallocated_count"] == 1
    assert result["tight_contested_row_count"] == 1


def test_recovery_requires_seed_anchoring():
    arrays = synthetic_arrays()
    result = recover_track(arrays, 0, 0, [proposal({50, 51})], owners={})
    assert result["status"] == "no-seed-anchored-tight-segment"
    assert len(result["selected_rows"]) == 0
