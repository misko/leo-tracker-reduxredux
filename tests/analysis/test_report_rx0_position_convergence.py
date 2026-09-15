import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "tools" / "report_rx0_position_convergence.py"
SPEC = importlib.util.spec_from_file_location("report_rx0_position_convergence", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_haversine_is_zero_and_handles_known_degree_scale():
    assert module.haversine_km((37.0, -122.0), (37.0, -122.0)) == 0
    assert module.haversine_km((0.0, 0.0), (1.0, 0.0)) == pytest.approx(111.195, abs=0.001)


def test_requested_horizons_are_monotonic_and_complete():
    assert module.HORIZONS == (("30m", 0.5), ("1h", 1.0), ("2h", 2.0), ("4h", 4.0), ("8h", 8.0))
