from types import SimpleNamespace

import numpy as np
import pytest
from compact_position_grid import position_receipt, validate_selection


def test_selection_rejects_catalogue_remapping_and_preserves_fixed_probability():
    data = SimpleNamespace(numbers=np.array([123, 456]))
    selection = {"satellite_indices": [1], "catalog_numbers": [456],
                 "detection_probability": .8 / 13, "fit": {"parameters": [0.] * 8}}
    indices, parameters, probability = validate_selection(selection, data)
    np.testing.assert_array_equal(indices, [1])
    assert parameters.shape == (8,)
    assert probability == .8 / 13
    selection["catalog_numbers"] = [123]
    with pytest.raises(ValueError, match="expanded bank"):
        validate_selection(selection, data)


def test_best_lower_loss_is_retained_but_failed_convergence_is_not_hidden():
    point = {"label": "N-50m", "position_km": [1., 2.]}
    receipt = position_receipt(point, [
        {"objective": 20., "success": True}, {"objective": 19., "success": False}])
    assert receipt["best_attempt_index"] == 1
    assert not receipt["ranking_resolved"]
    assert position_receipt(point, [{"objective": None, "success": False}])["best"] is None
