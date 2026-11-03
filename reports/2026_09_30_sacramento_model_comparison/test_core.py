import numpy as np
import pytest
from core import AssociationProblem, en_latlon, load_methods, training_masks

def test_association_problem_validates_shapes_and_finiteness():
    AssociationProblem(np.zeros((2, 3)), np.zeros(2), ("a", "b", "c"))
    with pytest.raises(ValueError):
        AssociationProblem(np.zeros((2, 3)), np.zeros(3), ("a", "b", "c"))
    with pytest.raises(ValueError):
        AssociationProblem(np.array([[np.nan]]), np.zeros(1), ("a",))

def test_declared_arms_match_frozen_comparison():
    methods = load_methods()
    assert set(methods) == {"C0", "C1", "C2", "G1", "M1", "M2", "M3", "M4", "M5", "M8", "M9", "G2"}
    assert methods["M5"]["family"] == "geometry"
    assert methods["M8"]["family"] == "piecewise"
    assert "not certifiable" in methods["M9"]["scope"]

def test_training_masks_require_exact_source_partition_shape():
    source = {"tracks": [
        {"track_id": "good", "measured_hz": [1, 2, 3], "training_mask": [True, False, True]},
        {"track_id": "bad", "measured_hz": [1, 2], "training_mask": [True]},
    ]}
    masks = training_masks(source)
    assert masks["good"].tolist() == [True, False, True]
    assert "bad" not in masks

def test_enu_origin_is_exact_sacramento_center():
    assert en_latlon(0.0, 0.0) == [38.5816, -121.4944]
