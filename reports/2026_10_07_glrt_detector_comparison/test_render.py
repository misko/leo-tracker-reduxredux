"""Check the descriptive ROC convention, including ties at the boundary."""

import numpy as np
import pytest
from render import descriptive_roc_point


def test_descriptive_roc_uses_exact_allowed_false_alarms():
    result = descriptive_roc_point(np.arange(100), [97, 99, 101])
    assert result["threshold_from_evaluation_nulls"] == 98
    assert result["false_alarms"] == 1
    assert result["detection_rate"] == pytest.approx(2 / 3)


def test_ties_never_exceed_false_alarm_budget():
    result = descriptive_roc_point(np.r_[np.arange(90), np.full(10, 99)], [98, 99, 100])
    assert result["false_alarms"] == 0
    assert result["detections"] == 1


@pytest.mark.parametrize("bad", [[], [np.nan], [[1, 2]]])
def test_roc_rejects_bad_null_data(bad):
    with pytest.raises(ValueError):
        descriptive_roc_point(bad, [0, 1])
