from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_frequency_refinement.py"
SPEC = importlib.util.spec_from_file_location("frequency_refinement_tool", PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def test_rolling_forecast_uses_supplied_irregular_measurement_times() -> None:
    times = np.asarray((0.0, 0.7, 1.9, 3.2, 4.1, 5.8, 7.3, 8.0))
    frequencies = 120_000.0 - 4_300.0 * times

    result = tool.rolling_forecasts(times, frequencies)

    assert result["1"]["holdout_count"] == 2
    assert result["1"]["rmse_hz"] == pytest.approx(0.0, abs=1e-8)


def test_frequency_support_center_is_correlation_energy_weighted(monkeypatch) -> None:
    correlations = SimpleNamespace(
        values=np.asarray(((1.0 + 0j, 2.0 + 0j),)),
        times_s=np.asarray(((0.1, 0.2),)),
    )
    workspace = SimpleNamespace(select=lambda symbols: correlations)
    monkeypatch.setattr(
        tool,
        "_conditioned_correlation_workspace",
        lambda *args, **kwargs: workspace,
    )

    center = tool.frequency_support_center_s(
        np.ones(100, dtype=np.complex64),
        2_500_000,
        anchor=5,
        offset=0.25,
        conditioning_cfo_hz=10_000.0,
        edge="lower",
    )

    assert center == pytest.approx(0.18)


def test_rolling_forecast_rejects_shared_or_unsorted_timestamps() -> None:
    with pytest.raises(ValueError, match="invalid rolling frequency forecast inputs"):
        tool.rolling_forecasts(
            np.asarray((0.0, 1.0, 2.0, 3.0, 3.0, 5.0, 6.0, 7.0)),
            np.arange(8.0),
        )
