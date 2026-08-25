from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOL_PATH = Path(__file__).parents[2] / "tools" / "prototype_rx0_cross_receiver_anchor_replay.py"
EXPECTED_TOOL_SHA256 = "586efda332f1d4ee4329eab5ea95a8ff52e0d4d0e23c3c1b890eaa6bcff53084"
SPEC = importlib.util.spec_from_file_location(
    "prototype_rx0_cross_receiver_anchor_replay", TOOL_PATH
)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _search(time_s: float, offset: float, *, exact: float, margin: float) -> dict[str, object]:
    return {
        "anchor_time_s": time_s,
        "circular_epoch_offset_samples": offset,
        "alignment_status": "complete",
        "exact_score": exact,
        "exact_minus_control_margin": margin,
    }


def test_circular_epoch_difference_uses_shortest_750hz_branch() -> None:
    assert tool.circular_epoch_difference(2, 3332) == pytest.approx(3.3333333333335)
    assert tool.circular_epoch_difference(3332, 2) == pytest.approx(-3.3333333333335)


def test_tool_and_scientific_config_are_frozen() -> None:
    assert tool.sha256(TOOL_PATH) == EXPECTED_TOOL_SHA256
    assert tool.canonical_sha256(tool.scientific_config()) == tool.EXPECTED_CONFIG_SHA256


@pytest.mark.real_corpus
def test_inputs_and_rx1_decompressed_rows_are_frozen() -> None:
    assert tool.verify_frozen_provenance() == tool.EXPECTED_INPUT_SHA256


def test_receiver_delay_uses_only_strong_first_sixty_percent() -> None:
    searches = [
        _search(45.0, 2.0, exact=0.20, margin=0.10),
        _search(46.0, 1.0, exact=0.19, margin=0.09),
        _search(47.0, 2.0, exact=0.18, margin=0.08),
        _search(47.5, 100.0, exact=0.04, margin=0.01),
        _search(50.0, -300.0, exact=0.90, margin=0.80),
    ]

    assert tool.estimate_receiver_delay(searches) == 2.0


def test_target_binding_requires_specificity_score_and_frozen_delay() -> None:
    accepted = _search(49.0, 1.0, exact=0.15, margin=0.01)
    wrong_epoch = _search(49.0, 8.0, exact=0.15, margin=0.01)
    weak = _search(49.0, 1.0, exact=0.09, margin=0.01)
    control_wins = _search(49.0, 1.0, exact=0.15, margin=-0.01)

    assert tool.target_bound(accepted, receiver_delay_samples=0.0)
    assert not tool.target_bound(wrong_epoch, receiver_delay_samples=0.0)
    assert not tool.target_bound(weak, receiver_delay_samples=0.0)
    assert not tool.target_bound(control_wins, receiver_delay_samples=0.0)


def test_line_fit_and_frozen_prediction_are_exact_for_a_line() -> None:
    rows = [
        {
            "reference_time_s": tool.COMMON_START_S + time_s,
            "even_absolute_cfo_hz": 500_000.0 - 3_500.0 * time_s,
            "primary_absolute_cfo_hz": 700_000.0 - 3_600.0 * time_s,
        }
        for time_s in (1.0, 2.0, 3.0, 5.0)
    ]

    model = tool.fit_line(rows[:3])

    assert model["slope_hz_s"] == pytest.approx(-3_500.0)
    assert model["residual_rms_hz"] == pytest.approx(0.0, abs=1e-8)
    assert tool.prediction_rms(rows[3:], model) == pytest.approx(0.0, abs=1e-8)

    primary = tool.fit_line(rows[:3], cfo_key="primary_absolute_cfo_hz")
    assert primary["slope_hz_s"] == pytest.approx(-3_600.0)
    assert tool.prediction_rms(
        rows[3:], primary, cfo_key="primary_absolute_cfo_hz"
    ) == pytest.approx(0.0, abs=1e-8)


def test_frame_ledger_preserves_primary_contract_rejection_reasons() -> None:
    primary = SimpleNamespace(
        measurement_supported=False,
        rejection_reasons=("even_odd_disagreement_above_maximum",),
        absolute_cfo_hz=123_456.0,
        exact_coherence=0.2,
        control_coherence=0.01,
        coherence_margin=0.19,
    )
    frame = SimpleNamespace(
        frame_start_sample=10_000,
        reference_sample=11_500.0,
        outcome=SimpleNamespace(value="supported"),
        filter_accepted=True,
        rejection_reasons=(),
        split_validation=None,
        primary=primary,
    )

    row = tool._frame_document("anchor", frame)

    assert row["primary_supported"] is False
    assert row["primary_rejection_reasons"] == ["even_odd_disagreement_above_maximum"]
