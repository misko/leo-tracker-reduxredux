import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPORT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location(
    "geometry_confirmation_inventory", REPORT / "build_inventory.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
validate_export_row = MODULE.validate_export_row
validate_pipeline_manifest = MODULE.validate_pipeline_manifest


def test_corrected_inventory_has_opportunity_export_contract() -> None:
    rows = json.loads((REPORT / "selected-inventory-corrected.json").read_text())
    assert len(rows) == 4
    assert {row["sample_rate_hz"] for row in rows} == {
        2_500_000,
        5_000_000,
        7_500_000,
        10_000_000,
    }
    for row in rows:
        validate_export_row(row)

    malformed = copy.deepcopy(rows[0])
    malformed.pop("ready")
    with pytest.raises(ValueError, match="ready evaluation"):
        validate_export_row(malformed)


def test_pose_manifest_has_training_bank_shape() -> None:
    manifest = json.loads((REPORT / "manifest.json").read_text())
    rows = json.loads((REPORT / "selected-inventory-corrected.json").read_text())
    validate_pipeline_manifest(manifest, {row["session_id"] for row in rows})

    malformed = copy.deepcopy(manifest)
    del malformed["sessions"][0]["pose"]["pose_authority"]["latitude_deg"]
    with pytest.raises(ValueError, match="pose row"):
        validate_pipeline_manifest(
            manifest=malformed, selected_ids={row["session_id"] for row in rows}
        )
