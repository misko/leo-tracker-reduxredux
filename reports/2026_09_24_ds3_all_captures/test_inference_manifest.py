from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "ds3_build_inference", HERE / "build_inference_manifest.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_live_frozen_manifest_binds_all_caches_without_reference() -> None:
    value = MODULE.build(
        HERE / "manifest.json", MODULE.DEFAULT_CACHE, MODULE.DS2_MANIFEST, MODULE.GEOMETRY_PLAN
    )
    assert value["dataset_name"] == "DS3"
    assert value["counts"] == {
        "sessions": 56,
        "eligible_tracks": 1443,
        "eligible_observations": 36270,
        "cohorts": 3,
        "geometry_conditional_sessions": 5,
    }
    assert value["reference_coordinate_in_manifest"] is False
    assert len(value["sessions"]) == len({row["session_id"] for row in value["sessions"]})
    assert all(row["tracking"]["status"] == "complete" for row in value["sessions"])
    assert sum("receiver_geometry" in row for row in value["sessions"]) == 5
