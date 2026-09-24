from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "shared_residual_audit_tool", TOOLS / "report_adaptive_dual_rx_shared_residual_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _pair(left_hz: float, right_hz: float) -> tuple[object, object, None, int]:
    return (
        SimpleNamespace(fractional_tracking_cfo_hz=left_hz),
        SimpleNamespace(fractional_tracking_cfo_hz=right_hz),
        None,
        0,
    )


def test_track_binding_uses_alias_aware_frequency_without_phase() -> None:
    period = tool.SYMBOL_ALIAS_HZ
    pairs = [_pair(0.0, 0.0), _pair(100_000.0 + period, -200_000.0 - period)]

    index, selected = tool.select_track_pair(pairs, 100_000.0, -200_000.0)

    assert index == 1
    assert selected is pairs[1]


def test_track_binding_rejects_outside_gate() -> None:
    with pytest.raises(ValueError, match="exceeds gate"):
        tool.select_track_pair([_pair(10_000.0, 20_000.0)], 0.0, 0.0)


def test_summary_separates_two_development_visits_from_validation() -> None:
    def row(visit: int, historical: float, shared: float, shift: float) -> dict[str, object]:
        return {
            "visit_index": visit,
            "state": "evaluated",
            "historical_abs_half_difference_deg": historical,
            "shared_abs_half_difference_deg": shared,
            "abs_full_phase_shift_at_common_center_deg": shift,
        }

    summary = tool.summarize(
        [row(1354, 100.0, 10.0, 5.0), row(1428, 120.0, 20.0, 6.0), row(1394, 8.0, 4.0, 3.0)]
    )

    assert summary["development"]["evaluated_visit_count"] == 2
    assert summary["validation"]["evaluated_visit_count"] == 1
    assert summary["development"]["metrics"]["shared_abs_half_difference_deg"][
        "median"
    ] == pytest.approx(15.0)
