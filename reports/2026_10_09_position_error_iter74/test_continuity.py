import numpy as np
from continuity import describe


def test_coherent_track_and_clutter_are_distinguished():
    a = describe(np.tile([0.8, 0], (5, 1)))
    assert a["map_satellite_switches"] == 0 and a["map_signal_pairs"] == 4
    assert a["soft_same_given_signal"] == 1 and a["dominant_satellite_share"] == 1
    b = describe(np.zeros((5, 2)))
    assert b["map_signal_pairs"] == 0 and b["soft_same_given_signal"] is None
    assert b["dominant_satellite_share"] is None


def test_alternating_identity_has_no_adjacent_agreement():
    a = describe(np.array([[0.9, 0], [0, 0.9], [0.9, 0], [0, 0.9]]))
    assert a["map_satellite_switches"] == 3 and a["map_signal_pairs"] == 3
    assert a["soft_same_given_signal"] == 0 and a["dominant_satellite_share"] == 0.5


def test_satellite_column_permutation_does_not_change_statistics():
    p = np.array([[0.4, 0.5], [0.3, 0.6], [0.1, 0.2], [0.7, 0.2]])
    a, b = describe(p), describe(p[:, ::-1])
    assert a.keys() == b.keys()
    np.testing.assert_allclose(list(a.values()), list(b.values()), atol=1e-14, rtol=0)
