import numpy as np
import pytest
from correlate_metadata import association, attribute_distance, bh_adjust, representatives
from signal_metadata import compatible_track, summarize


def test_binding_requires_receiver_rf_and_visit():
    track = dict(receiver_id=0, channel=4, rf_hz=11.69e9, visits=[10, 12])
    probe = dict(receiver_id=0, channel=4, actual_rf_hz=11.69e9, visit_index=10)
    assert compatible_track(track, probe)
    for key, wrong in [
        ("receiver_id", 1),
        ("channel", 3),
        ("actual_rf_hz", 11.46e9),
        ("visit_index", 11),
    ]:
        assert not compatible_track(track, {**probe, key: wrong})
    assert summarize([None, np.nan]) is None
    assert summarize([0, 2, None]) == 1


def test_circular_azimuth_and_categorical_ids():
    assert attribute_distance([359, 1], "circular")[0, 1] == 2
    assert attribute_distance([1, 500], "category")[0, 1] == 1
    assert attribute_distance([1, 500], "numeric")[0, 1] == 499


def test_session_selection_never_duplicates_a_session():
    rows = [
        dict(signal="S02", session="a", accepted=10),
        dict(signal="S01", session="a", accepted=10),
        dict(signal="S03", session="b", accepted=15),
    ]
    assert [r["signal"] for r in representatives(rows)] == ["S01", "S03"]


def test_label_permutations_are_reproducible_and_no_variation_is_missing():
    matrix = attribute_distance([0, 1, 3, 7, 12, 20], "numeric")
    rho, p = association(matrix, matrix, repetitions=199)
    assert rho == pytest.approx(1)
    assert 0 < p < 0.05
    assert (rho, p) == association(matrix, matrix, repetitions=199)
    assert association(matrix, np.zeros_like(matrix)) == (None, None)


def test_bh_preserves_input_order_and_matches_known_example():
    assert bh_adjust([0.04, 0.01, 0.03]) == pytest.approx([0.04, 0.03, 0.04])
    assert bh_adjust([]) == []
