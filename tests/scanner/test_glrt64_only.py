from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import leo.scanner.detector as detector_module
from leo.analysis.starlink.pilot_methods import PilotMethod, conditioned_glrt64_score
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame
from leo.scanner import ScannerConfiguration, current_low_band_targets


def test_glrt64_only_score_separates_exact_qin_pilot_from_control() -> None:
    rate = 2_500_000
    epoch = 37
    cfo = 42_000.0
    samples = np.zeros(50_000, dtype=np.complex128)
    template = qin_edge_pilot_frame(rate, "lower")
    frame = 0
    while True:
        start = epoch + round(frame * rate / FRAME_RATE_HZ)
        if start + len(template) > len(samples):
            break
        indexes = np.arange(start, start + len(template))
        samples[start : start + len(template)] += template * np.exp(
            2j * np.pi * cfo * indexes / rate
        )
        frame += 1

    result = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=cfo,
        edge="lower",
    )

    assert result.method is PilotMethod.GLRT64
    assert result.margin > 0.5
    assert abs(result.residual_cfo_hz) < 1.0


def test_conditioned_glrt64_uses_selected_edge() -> None:
    rate = 2_500_000
    template = qin_edge_pilot_frame(rate, "upper")
    samples = np.tile(template, 2)[:50_000]

    upper = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=0,
        acquired_cfo_hz=0.0,
        edge="upper",
    )
    lower = conditioned_glrt64_score(
        samples,
        rate,
        epoch_sample=0,
        acquired_cfo_hz=0.0,
        edge="lower",
    )

    assert upper.margin > lower.margin


def test_scanner_acquisition_uses_standard_basin_retention_policy(monkeypatch) -> None:
    configuration = ScannerConfiguration(
        receiver_ids=(0,),
        maximum_acquisition_candidates=10,
        targets=current_low_band_targets()[:1],
    )
    samples = np.zeros((configuration.dwell_samples, 1), dtype=np.complex128)
    observed = []

    def acquire(_probe, *_args, config, **_kwargs):
        observed.append(config)
        return SimpleNamespace(candidates=())

    monkeypatch.setattr(detector_module, "acquire_symbolwise", acquire)

    result = detector_module.analyze_glrt64_dwell(samples, configuration, edge="lower")

    assert result.first is None
    assert len(observed) == configuration.scheduled_probe_count
    assert all(item.retained_candidate_count == 10 for item in observed)
    assert all(item.candidate_cfo_separation_hz == 10_000.0 for item in observed)
    assert all(item.candidate_epoch_separation_samples == 5 for item in observed)


def _detect_with_probe_scores(monkeypatch, margins, frequencies, *, full=False):
    configuration = ScannerConfiguration(
        receiver_ids=(0,),
        targets=current_low_band_targets()[:1],
    )
    samples = np.arange(configuration.dwell_samples, dtype=np.float64)[:, None].astype(
        np.complex128
    )

    def acquire(probe, *_args, **_kwargs):
        probe_index = round(float(probe[0].real)) // configuration.probe_stride_samples
        candidate = SimpleNamespace(
            rank=0,
            refined_epoch_sample=0,
            absolute_cfo_hz=float(frequencies.get(probe_index, 100_000.0)),
        )
        return SimpleNamespace(candidates=(candidate,))

    def score(_probe, _rate, *, acquired_cfo_hz, **_kwargs):
        probe_index = round(float(_probe[0].real)) // configuration.probe_stride_samples
        margin = float(margins.get(probe_index, 0.0))
        return SimpleNamespace(
            margin=margin,
            residual_cfo_hz=0.0,
            tracking_cfo_hz=acquired_cfo_hz,
            exact_score=0.1 + margin,
            control_score=0.1,
        )

    monkeypatch.setattr(detector_module, "acquire_symbolwise", acquire)
    monkeypatch.setattr(detector_module, "conditioned_glrt64_score", score)
    function = detector_module.analyze_glrt64_dwell if full else detector_module.detect_first_glrt64
    return function(samples, configuration, edge="lower")


def test_scanner_confirms_two_non_overlapping_cfo_consistent_hits(monkeypatch) -> None:
    result = _detect_with_probe_scores(
        monkeypatch,
        margins={0: 0.08, 2: 0.09},
        frequencies={0: 100_000.0, 2: 106_000.0},
    )

    assert result.first is not None
    assert result.first.probe_index == 0
    assert result.first.probe_start_ms == 0
    assert result.best_margin == 0.09
    assert "non-overlapping" in result.reason


def test_scanner_rejects_an_isolated_margin_crossing(monkeypatch) -> None:
    result = _detect_with_probe_scores(
        monkeypatch,
        margins={3: 0.2},
        frequencies={3: 100_000.0},
    )

    assert result.first is None
    assert result.best_margin == 0.2
    assert "all 7 overlapping" in result.reason


def test_scanner_rejects_hits_that_only_overlap(monkeypatch) -> None:
    result = _detect_with_probe_scores(
        monkeypatch,
        margins={0: 0.08, 1: 0.09},
        frequencies={0: 100_000.0, 1: 101_000.0},
    )

    assert result.first is None


def test_scanner_rejects_non_overlapping_hits_on_different_cfo_branches(monkeypatch) -> None:
    result = _detect_with_probe_scores(
        monkeypatch,
        margins={0: 0.08, 2: 0.09},
        frequencies={0: 100_000.0, 2: 109_000.0},
    )

    assert result.first is None


def test_full_response_preserves_legacy_decision_point_and_finishes_schedule(monkeypatch) -> None:
    result = _detect_with_probe_scores(
        monkeypatch,
        margins={0: 0.08, 2: 0.09, 6: 0.5},
        frequencies={0: 100_000.0, 2: 106_000.0, 6: 200_000.0},
        full=True,
    )

    assert result.first is not None
    assert result.first.probe_index == 0
    assert result.decision_best_margin == 0.09
    assert result.full_best_margin == 0.5
    assert len(result.probes) == 7
