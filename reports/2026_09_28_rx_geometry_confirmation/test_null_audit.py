import importlib.util
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).with_name("null_audit.py")
SPEC = importlib.util.spec_from_file_location("rx_geometry_null_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
clutter_window_log_density = MODULE.clutter_window_log_density


def test_clutter_set_density_keeps_frequency_units_and_both_receivers() -> None:
    rates = np.array([2.0, 0.5])
    period = 100.0
    assert clutter_window_log_density((3, 0), rates, period) == pytest.approx(
        -2.5 + 3 * np.log(2.0 / period)
    )
