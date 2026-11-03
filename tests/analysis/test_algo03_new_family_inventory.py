from probe_algo03_new_family_inventory import unused_curves


def test_partial_ownership_and_duplicate_points_exclude_whole_curve():
    tracks=[dict(observation_ids=["a","b"]),dict(observation_ids=["c","c"]),
            dict(observation_ids=["d","e"])]
    assert unused_curves(tracks,{"a"})==[2]
