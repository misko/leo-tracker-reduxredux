from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "ds2_successor_geometry", HERE / "execute_geometry.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def valid_plan() -> dict:
    return {
        "schema": "ds2-successor-geometry-cone-plan/v1",
        "reference_coordinate_present": False,
        "reference_used_for_inference": False,
        "fitted_cone_families": sorted(MODULE.EXPECTED_FAMILIES),
        "receiver_slot_mappings": [[0, 1], [1, 0]],
        "sessions": [
            {
                "session_id": f"scan-{index}",
                "capture_binding_digest": "sha256:capture",
                "fixture_digest": "sha256:fixture",
            }
            for index in range(3)
        ],
    }


def test_plan_requires_both_mapping_symmetries() -> None:
    plan = valid_plan()
    plan["receiver_slot_mappings"] = [[0, 1]]
    with pytest.raises(ValueError, match="both RX-to-slot"):
        MODULE.validate_plan(plan)


def test_plan_rejects_reference_bearing_inference() -> None:
    plan = valid_plan()
    plan["reference_coordinate_present"] = True
    with pytest.raises(ValueError, match="reference coordinate"):
        MODULE.validate_plan(plan)


def test_plan_admits_three_explicitly_bound_sessions() -> None:
    assert MODULE.validate_plan(valid_plan()) == ("scan-0", "scan-1", "scan-2")
