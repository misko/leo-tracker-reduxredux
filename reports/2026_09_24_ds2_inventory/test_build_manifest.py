from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module():
    path = Path(__file__).parent / "build_manifest.py"
    spec = importlib.util.spec_from_file_location("ds2_inventory_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def capture(**overrides):
    value = {
        "utc_qualified": True,
        "terminal_state": "completed",
        "source_span_attested": True,
        "nominal_duration_seconds": 300,
        "retained_visits": 1,
    }
    value.update(overrides)
    return value


def test_inclusion_requires_raw_conditions_and_does_not_infer_geometry():
    m = module()
    result = m.inclusion(
        capture(),
        {"receiver_ids": [0, 1], "state": "completed", "track_count": 4},
    )
    assert result["raw_capture_eligible"] is True
    assert result["analysis_ready"] is True
    assert result["geometry_aware_model_eligible"] is False
    assert result["geometry_status"] == "unavailable_from_public_inventory_api"


def test_inclusion_explains_missing_dual_receiver_status():
    m = module()
    result = m.inclusion(capture(), {"receiver_ids": [0], "state": "not_started"})
    assert result["raw_capture_eligible"] is False
    assert "dual_rx_declared_by_analysis" in result["exclusion_reasons"]
    assert "no_public_completed_track_count" in result["exclusion_reasons"]


def test_cutoff_parser_normalizes_z():
    m = module()
    assert m.as_utc("2026-09-24T15:43:30Z").isoformat() == "2026-09-24T15:43:30+00:00"
