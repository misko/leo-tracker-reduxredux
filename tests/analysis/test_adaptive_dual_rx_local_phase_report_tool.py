from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_local_phase.py"
    specification = importlib.util.spec_from_file_location("local_phase_report", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_renderer_labels_local_phase_without_geometry_claim(tmp_path: Path) -> None:
    module = _module()
    document = {
        "session_id": "scan-hop-test",
        "rows": [
            {
                "session_time_s": time,
                "wrapped_rx1_minus_rx0_phase_deg": phase,
                "phase_standard_error_deg": 4.0,
                "relative_frequency_hz": -560_000.0,
                "resultant_length": 0.95,
                "exact_to_control_power_ratio_floor": 8.0,
                "target_index": index,
            }
            for index, (time, phase) in enumerate(((1.0, -20.0), (2.0, 30.0)))
        ],
    }
    output = tmp_path / "phase.png"

    module.render(document, output)

    payload = output.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(payload) > 1_000


def test_extraction_visit_bound_fails_before_storage_access(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(ValueError, match="bounded to 1..20"):
        module.extract(tmp_path, tmp_path / "missing.json", maximum_visits=21, edge="both")
