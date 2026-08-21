from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path("tools/summarize_470384_alias_offsets.py")
_SPEC = importlib.util.spec_from_file_location("summarize_470384_alias_offsets", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _constant_model(value_hz: float) -> dict[str, object]:
    return {
        "start_s": 10.0,
        "end_s": 12.0,
        "reference_time_s": 10.0,
        "coefficients_hz": [0.0, value_hz],
    }


def test_approximate_symbol_offset_outside_maximum_gate_is_not_accepted() -> None:
    lower = _constant_model(200_000.0)
    upper = _constant_model(200_000.0 + _MODULE.ALIAS_SPACING_HZ - 6_600.0)

    result = _MODULE.alias_pair_metrics(lower, upper)

    assert result["alias_index_delta"] == 1
    assert result["residual_rms_hz"] == pytest.approx(6_600.0)
    assert result["maximum_absolute_residual_hz"] == pytest.approx(6_600.0)
    assert result["minimum_gate_to_accept_hz"] == pytest.approx(6_600.0)
    assert result["gate_multiple_required"] == pytest.approx(2.64)
    assert result["accepted"] is False


def test_exact_symbol_offset_is_accepted_without_retuning_spacing() -> None:
    lower = _constant_model(200_000.0)
    upper = _constant_model(200_000.0 + _MODULE.ALIAS_SPACING_HZ)

    result = _MODULE.alias_pair_metrics(lower, upper)

    assert result["alias_index_delta"] == 1
    assert result["maximum_absolute_residual_hz"] < 1e-9
    assert result["accepted"] is True
