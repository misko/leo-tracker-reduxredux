import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "reports/2026_09_23_train_edge_convention_audit/audit.py"
SPEC = importlib.util.spec_from_file_location("train_edge_convention_audit", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("cfo_hz", [-42_000.0, 42_000.0])
def test_glrt_preserves_injected_cfo_sign_and_value_on_both_edges(edge, cfo_hz):
    seed = cfo_hz - 1_500.0 if cfo_hz > 0 else cfo_hz + 1_500.0
    result = MODULE.synthetic_score(edge, cfo_hz, acquired_seed_hz=seed)
    assert result["tracking_cfo_hz"] == pytest.approx(cfo_hz, abs=200.0)
    assert result["residual_cfo_hz"] * (cfo_hz - seed) > 0
    assert result["margin"] > 0.5


def test_same_injected_slope_has_same_projection_on_both_edges():
    estimates = {}
    for offset in (0.0, 1.0):
        lower = MODULE.synthetic_score(
            "lower", 40_000.0, -1_800.0, time_offset_s=offset, acquired_seed_hz=40_000.0
        )
        upper = MODULE.synthetic_score(
            "upper", 40_000.0, -1_800.0, time_offset_s=offset, acquired_seed_hz=40_000.0
        )
        assert lower["tracking_cfo_hz"] == pytest.approx(upper["tracking_cfo_hz"], abs=0.01)
        estimates[offset] = lower["tracking_cfo_hz"]
    recovered_slope = estimates[1.0] - estimates[0.0]
    assert recovered_slope == pytest.approx(-1_800.0, abs=100.0)
