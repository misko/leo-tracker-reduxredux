import importlib.util
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("single_track_cross_dwell_phase", MODULE_PATH)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def test_circular_helpers_handle_wrap_boundary() -> None:
    phase = np.radians([179.0, -179.0])
    assert ANALYSIS.circular_r(phase) > 0.999
    assert abs(abs(np.degrees(ANALYSIS.circular_mean(phase))) - 180.0) < 1e-9
    assert np.allclose(
        np.degrees(ANALYSIS.wrap_rad(np.radians([181.0, -181.0]))), [-179.0, 179.0]
    )


def test_exact_dual_rx_track_selection_is_frozen() -> None:
    assert len(ANALYSIS.EXACT_SHARED_VISITS) == 47
    assert ANALYSIS.EXACT_SHARED_VISITS[0] == 637
    assert ANALYSIS.EXACT_SHARED_VISITS[-1] == 820
    assert len(set(ANALYSIS.EXACT_SHARED_VISITS)) == len(ANALYSIS.EXACT_SHARED_VISITS)


def test_alias_branch_resolution_selects_nearest_symbol_rate_copy() -> None:
    reference = 674_853.3580860491
    raw = 447_883.60401852545
    resolved = ANALYSIS.branch_resolve(raw, reference)
    assert abs(resolved - reference) < 500.0
