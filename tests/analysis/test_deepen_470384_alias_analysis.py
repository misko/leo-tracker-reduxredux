from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_PATH = Path("tools/deepen_470384_alias_analysis.py")
_SPEC = importlib.util.spec_from_file_location("deepen_470384_alias_analysis", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _linear(*, slope: float, intercept: float, start: float, end: float) -> dict[str, object]:
    return {
        "coefficients_hz": [slope, intercept],
        "reference_time_s": 0.0,
        "start_s": start,
        "end_s": end,
    }


def test_slope_pair_facts_reports_chord_and_shared_interval() -> None:
    result = _MODULE.slope_pair_facts(
        _linear(slope=-7_200.0, intercept=10.0, start=1.0, end=5.0),
        _linear(slope=-7_125.0, intercept=20.0, start=2.0, end=6.0),
    )

    assert result["overlap_start_s"] == 2.0
    assert result["overlap_end_s"] == 5.0
    assert result["lower"]["chord_hz_s"] == pytest.approx(-7_200.0)
    assert result["upper"]["chord_hz_s"] == pytest.approx(-7_125.0)
    assert result["upper_minus_lower"]["maximum_absolute_hz_s"] == pytest.approx(75.0)


def test_slope_pair_facts_rejects_disjoint_models() -> None:
    with pytest.raises(ValueError, match="do not overlap"):
        _MODULE.slope_pair_facts(
            _linear(slope=1.0, intercept=0.0, start=0.0, end=1.0),
            _linear(slope=1.0, intercept=0.0, start=2.0, end=3.0),
        )


def test_pearson_interval_contains_a_moderate_observed_correlation() -> None:
    result = _MODULE.pearson_with_fisher_interval(
        np.arange(10, dtype=float),
        np.asarray([0, 1, 2, 5, 3, 4, 8, 6, 9, 7], dtype=float),
    )

    assert result["sample_count"] == 10
    assert result["fisher_95_low"] < result["pearson_r"] < result["fisher_95_high"]


def test_bulk_product_path_confines_analysis_uris(tmp_path: Path) -> None:
    assert _MODULE._bulk_product_path(
        tmp_path, "bulk://analysis/session/run/product.json"
    ) == tmp_path / "analysis/session/run/product.json"
    with pytest.raises(ValueError, match="non-analysis"):
        _MODULE._bulk_product_path(tmp_path, "bulk://recordings/session")
    with pytest.raises(ValueError, match="unsafe"):
        _MODULE._bulk_product_path(tmp_path, "bulk://analysis/../recordings/session")


def test_zero_event_upper_bound_decreases_with_more_trials() -> None:
    assert _MODULE._zero_event_upper_95(472) < _MODULE._zero_event_upper_95(118)
    assert _MODULE._zero_event_upper_95(472) == pytest.approx(0.006326791445588897)
