import numpy as np
from plot_used_orbits import selected_pairs, partition_rows, unassigned_alias_points
from test_review import fixture


def test_overlay_uses_assigned_satellite_column():
    data, records = fixture()
    rows, columns = selected_pairs(data, records)
    assert np.array_equal(rows, [0, 1])
    assert np.array_equal(columns, [0, 1])
    a = data["arrays"]
    a["modeled_doppler_hz"] = np.array([[100., 200.], [101., 202.]])
    a["doppler_hz"] = a["modeled_doppler_hz"] + a["residual_hz"]
    assert np.allclose(a["doppler_hz"][rows, columns] - a["modeled_doppler_hz"][rows, columns], [10., 40.])


def test_all_rows_partitioned_without_hidden_gate():
    parts = partition_rows(5, np.array([0, 2, 4]), np.array([1, 0, 1]), 1)
    assert [p.tolist() for p in parts] == [[1, 3], [2], [0, 4]]
    assert sorted(np.concatenate(parts).tolist()) == list(range(5))


def test_unassigned_keeps_alternative_aliases_without_duplicate_satellite_copies():
    a = dict(times_s=np.arange(3.), catalog_numbers=np.array([10, 20, 30]),
             alias_integer=np.array([[0, 0, 1], [2, 2, 2], [1, 2, 1]]))
    rows, cols = unassigned_alias_points(a, np.array([1]))
    keys = list(zip(rows, a["alias_integer"][rows, cols]))
    assert len(keys) == 4
    assert set(keys) == {(0, 0), (0, 1), (2, 1), (2, 2)}
