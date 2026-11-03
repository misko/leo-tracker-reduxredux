from __future__ import annotations

import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/native_adaptive_ds9_export.py"
COMPARISON = ROOT / "reports/2026_09_30_arm_ds9_native_comparison"
REPORT = ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9"


def load_tool():
    specification = importlib.util.spec_from_file_location("native_adaptive_ds9_export", TOOL)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_published_arm_ordinary_matches_control_for_all_repetitions() -> None:
    evidence = load_tool().compare_arm_panel(COMPARISON)

    assert evidence["passed"] is True
    assert evidence["calls"] == 800
    assert evidence["candidate_entries_across_repetitions"] == 2_980
    assert evidence["refinement_skipped_entries_across_repetitions"] == 2_980
    assert evidence["mismatches"] == []


def test_portable_manifest_checks_every_member_hash(tmp_path: Path) -> None:
    panel_path = COMPARISON / "panel.json"
    archive_path = COMPARISON / "local/inputs.tar"
    manifest = load_tool().portable_manifest(panel_path, archive_path)

    assert manifest["case_count"] == 80
    assert manifest["profile"] == {"dwell_ms": 120, "probe_ms": 20, "probe_stride_ms": 120}
    assert len(manifest["cases"]) == 80

    broken = tmp_path / "broken.tar"
    with tarfile.open(broken, "w") as archive:
        payload = tmp_path / "lower-exact.c128"
        payload.write_bytes(b"wrong")
        archive.add(payload, arcname=payload.name)
    with pytest.raises(ValueError, match="hash mismatch|missing"):
        load_tool().portable_manifest(panel_path, broken)


def test_location_artifacts_distinguish_selection_from_complete_source() -> None:
    selection = json.loads((REPORT / "location-selection/manifest.json").read_text())
    source = json.loads((REPORT / "location-source-inventory/source-inventory.json").read_text())

    assert selection["selection_complete"] is True
    assert selection["complete_scan"] is False
    assert selection["selected_visit_indices"] == [276, 830, 1384, 1938]
    assert source["capture_visit_inventory_complete"] is True
    assert source["visit_count"] == 2_215
    assert source["sample_rate_hz"] == 7_500_000
    assert source["valid_visit_ms"] == 120
    assert source["uncompressed_bytes"] == 15_948_000_000
    assert source["raw_ci16_exported"] is False


def test_location_templates_are_frozen_public_qin_outputs() -> None:
    manifest = json.loads((REPORT / "location-templates/manifest.json").read_text())
    templates = {row["role"]: row for row in manifest["templates"]}

    assert templates["exact"]["sha256"] == (
        "8e9f4eaca4a999a3f74b4a74cda5d0b01193941bf5e74a4623ec5a984f8a6f0a"
    )
    assert templates["control"]["sha256"] == (
        "84b2ae110c3d03f882d1aa410c11eeb2b64a7618b14d491d453f330ee6c70484"
    )
    assert templates["exact"]["shape"] == [10_000]
    assert templates["control"]["symbol_roll"] == 17
