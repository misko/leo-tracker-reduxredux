import json
from pathlib import Path

import pytest

from run_arm import unavailable_feature_result


HERE = Path(__file__).resolve().parent


@pytest.mark.parametrize(
    ("arm", "status"),
    [
        ("M6", "not_evaluated_missing_qualified_input"),
        ("M7", "not_evaluated_failed_calibration_transfer"),
        ("M10", "not_evaluated_missing_qualified_input"),
    ],
)
def test_feature_arm_receipt_is_source_bound_and_has_no_position(arm, status):
    unit = "DS9-F001"
    result = unavailable_feature_result(unit, arm, HERE / "evidence")
    evidence = json.loads((HERE / "evidence" / f"{unit}.json").read_text())
    assert result["status"] == status
    assert result["qualified"] is False
    assert result["point_estimate"] is None
    assert result["reference_coordinate_accessed"] is False
    assert result["session_id"] == evidence["session_id"]
    assert result["manifest_sha256"] == evidence["manifest_sha256"]
    assert len(result["inputs"]) == 2
