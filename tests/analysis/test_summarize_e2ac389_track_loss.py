from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path("tools/summarize_e2ac389_track_loss.py")
_SPEC = importlib.util.spec_from_file_location("summarize_e2ac389_track_loss", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _gate() -> dict[str, float | int]:
    return {
        "minimum_probe_count": 20,
        "minimum_block_coverage_ratio": 0.5,
        "minimum_median_corrected_margin": 0.05,
        "maximum_harmful_block_fraction": 0.25,
        "maximum_consecutive_harmful_blocks": 2,
    }


def _row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "geometry_display_eligible": True,
        "evaluated_probe_count": 42,
        "evaluated_block_count": 2,
        "block_coverage_ratio": 1.0,
        "median_block_corrected_margin": 0.32,
        "harmful_block_count": 0,
        "maximum_consecutive_harmful_blocks": 0,
    }
    row.update(updates)
    return row


def test_directed_v3_removes_minimum_block_and_equivalence_gates_only() -> None:
    assert _MODULE.directed_v3_automatic(_row(), _gate())
    assert not _MODULE.directed_v3_automatic(_row(median_block_corrected_margin=0.001), _gate())
    assert not _MODULE.directed_v3_automatic(
        _row(evaluated_block_count=4, harmful_block_count=2), _gate()
    )
    assert not _MODULE.directed_v3_automatic(_row(maximum_consecutive_harmful_blocks=3), _gate())


def test_line_match_is_alias_aware_and_overlap_bounded() -> None:
    spacing = 2_500_000 / 11
    track = {
        "start_s": 10.0,
        "end_s": 20.0,
        "slope_hz_per_s": -5_000.0,
        "intercept_mod_alias_hz": 100_000.0,
    }
    model = {
        "model_id": "model-a",
        "start_s": 12.0,
        "end_s": 18.0,
        "reference_time_s": 0.0,
        "coefficients_hz": [-5_000.0, 100_000.0 + spacing],
    }
    branch = {
        "branch_id": "sha256:" + "a" * 64,
        "selected_model_id": "model-a",
        "models": [model],
    }
    rows = _MODULE.line_matches(track, [branch], spacing)
    assert len(rows) == 1
    assert rows[0]["overlap_s"] == 6.0
    assert rows[0]["modulo_residual_rms_hz"] < 1e-8
    assert rows[0]["median_slope_difference_hz_per_s"] < 1e-8
