import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "panel_controller", Path(__file__).with_name("controller.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def plan():
    return {
        "captures": [
            {
                "dataset_id": dataset,
                "unit_id": f"{dataset}-{i:03d}",
                "session_id": f"{dataset}-session-{i}",
                "error_m": i,
            }
            for dataset in ("DS8", "DS9")
            for i in range(1, 9)
        ]
    }


def test_exact_continuation_preserves_order_and_does_not_refit_preflight():
    original = plan()
    assert [r["unit_id"] for r in module.units(original, "DS9")] == [
        f"DS9-{i:03d}" for i in range(2, 9)
    ]
    assert len(original["captures"]) == 16


def test_rejects_missing_reordered_or_duplicate_members():
    changed = plan()
    changed["captures"][0], changed["captures"][1] = changed["captures"][1], changed["captures"][0]
    with pytest.raises(ValueError, match="membership/order"):
        module.units(changed, "DS8")
    changed = plan()
    changed["captures"][1]["session_id"] = changed["captures"][0]["session_id"]
    with pytest.raises(ValueError, match="duplicate"):
        module.units(changed, "DS8")
