"""Test the serial decision fold against the application, including ordering."""

import sys
from pathlib import Path
from types import SimpleNamespace
from multiprocessing.shared_memory import SharedMemory

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parallel_scanner import fold_responses
import parallel_scanner
import leo.scanner.detector as detector
from leo.scanner.models import ScannerConfiguration, current_low_band_targets


@pytest.mark.parametrize("case", ["early", "late", "negative", "overlap", "cfo_edge", "cfo_out", "competing"])
def test_fold_matches_full_oracle(monkeypatch, case):
    config = ScannerConfiguration(targets=current_low_band_targets()[:1], maximum_acquisition_candidates=10)
    values = np.empty((config.dwell_samples, 2), dtype=complex)
    values[:, 0] = np.arange(config.dwell_samples)
    values[:, 1] = np.arange(config.dwell_samples) + 1j
    def acquire(probe, *args, **kwargs):
        index = round(probe[0].real) // config.probe_stride_samples
        receiver = round(probe[0].imag)
        return SimpleNamespace(candidates=tuple(SimpleNamespace(
            rank=rank, refined_epoch_sample=rank,
            absolute_cfo_hz=float(index * 100 + receiver * 10 + rank),
        ) for rank in range(2)))
    def score(probe, rate, *, acquired_cfo_hz, **kwargs):
        index = round(probe[0].real) // config.probe_stride_samples
        rank = int(acquired_cfo_hz) % 10
        chosen = {0, 2}
        if case == "late": chosen = {8, 10}
        if case == "negative": chosen = set()
        if case == "overlap": chosen = {0, 1}
        margin = (0.025 + rank * 0.02) if index in chosen else -0.02
        cfo = 100000.0
        if index == 2 and case in {"cfo_edge", "cfo_out"}:
            cfo += 8000 if case == "cfo_edge" else 8000.001
        if case == "competing": cfo += 10000 * rank
        return SimpleNamespace(margin=margin, residual_cfo_hz=cfo-acquired_cfo_hz,
                               tracking_cfo_hz=cfo, exact_score=margin+0.1, control_score=0.1)
    monkeypatch.setattr(detector, "acquire_symbolwise", acquire)
    monkeypatch.setattr(detector, "conditioned_glrt64_score", score)
    expected = detector.analyze_glrt64_dwell(values, config, edge="lower")
    assert fold_responses(expected.probes, config) == expected
    with pytest.raises(ValueError):
        fold_responses(expected.probes[::-1], config)


def test_empty_candidates_match_oracle(monkeypatch):
    config = ScannerConfiguration(targets=current_low_band_targets()[:1])
    monkeypatch.setattr(detector, "acquire_symbolwise", lambda *a, **k: SimpleNamespace(candidates=()))
    expected = detector.analyze_glrt64_dwell(np.zeros((config.dwell_samples, 2)), config, edge="lower")
    assert fold_responses(expected.probes, config) == expected


def test_worker_reads_correct_shared_probe_and_restores_coordinates(monkeypatch):
    config = ScannerConfiguration(targets=current_low_band_targets()[:1])
    values = np.empty((config.dwell_samples, 2), dtype=np.complex64)
    values[:, 0] = np.arange(config.dwell_samples)
    values[:, 1] = -np.arange(config.dwell_samples) + 3j
    shared = SharedMemory(create=True, size=values.nbytes)
    observed = []
    def analyze(probe, local, *, edge):
        observed.append((probe.copy(), local, edge))
        return SimpleNamespace(probes=(detector.Glrt64ProbeResponse(1, 0, 0, ()),))
    monkeypatch.setattr(parallel_scanner, "analyze_glrt64_dwell", analyze)
    try:
        np.ndarray(values.shape, dtype=values.dtype, buffer=shared.buf)[:] = values
        result, cpu = parallel_scanner.evaluate_probe((
            shared.name, values.shape, values.dtype.str, config, "upper", 1, 1, 7,
        ))
        expected = values[7*config.probe_stride_samples:7*config.probe_stride_samples+config.probe_samples, 1]
        assert np.array_equal(observed[0][0][:, 0], expected)
        assert observed[0][0].dtype == np.complex128
        assert observed[0][1].receiver_ids == (1,)
        assert observed[0][1].dwell_ms == 20
        assert observed[0][2] == "upper"
        assert result == detector.Glrt64ProbeResponse(1, 7, 70, ())
        assert cpu >= 0
        assert np.array_equal(np.ndarray(values.shape, dtype=values.dtype, buffer=shared.buf), values)
    finally:
        shared.close()
        shared.unlink()
