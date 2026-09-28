from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink import ReceiverFrequencyCalibration, SymbolwiseAcquisitionConfig
from leo.scanner import ScannerConfiguration, current_low_band_targets
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.models import Glrt64FirstDetection

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds7_benchmark_methods", HERE / "methods.py")
assert SPEC is not None and SPEC.loader is not None
methods = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = methods
SPEC.loader.exec_module(methods)


def _configuration(*, dwell_ms: int = 20, receivers: tuple[int, ...] = (0,)):
    return ScannerConfiguration(
        dwell_ms=dwell_ms,
        receiver_ids=receivers,
        targets=current_low_band_targets()[:1],
    )


def _context(*, visit: int = 0, counter: int = 1_000, session: str = "s"):
    return {
        "session_id": session,
        "visit_index": visit,
        "sample_start_counter": counter,
        "rate_hz": 2_500_000,
        "target_index": 0,
    }


def _iq(configuration: ScannerConfiguration) -> np.ndarray:
    return np.zeros(
        (configuration.dwell_samples, len(configuration.receiver_ids)),
        dtype=np.complex64,
    )


def _analysis(*, confirmed: bool, receiver_id: int = 0, cfo: float = 100_000.0):
    first = None
    responses = []
    for probe_index, start_ms in ((0, 0), (2, 20)):
        passed = confirmed
        candidate = Glrt64CandidateResponse(
            candidate_rank=0,
            epoch_sample=37,
            acquired_cfo_hz=cfo,
            residual_cfo_hz=0.0,
            tracking_cfo_hz=cfo + probe_index * 1_000.0,
            exact_score=0.1,
            control_score=0.01,
            margin=0.09,
            passed_margin_gate=passed,
        )
        responses.append(
            Glrt64ProbeResponse(
                receiver_id=receiver_id,
                probe_index=probe_index,
                probe_start_ms=start_ms,
                candidates=(candidate,),
            )
        )
    if confirmed:
        first = Glrt64FirstDetection(
            receiver_id=receiver_id,
            probe_index=0,
            probe_start_ms=0,
            candidate_rank=0,
            epoch_sample=37,
            acquired_cfo_hz=cfo,
            residual_cfo_hz=0.0,
            tracking_cfo_hz=cfo,
            exact_score=0.1,
            control_score=0.01,
            margin=0.09,
        )
    return DwellGlrt64Analysis(
        first=first,
        decision_best_margin=0.09 if confirmed else None,
        full_best_margin=0.09 if confirmed else None,
        reason="synthetic",
        probes=tuple(responses),
    )


def test_factory_loads_frozen_original_and_rejects_unknown_name() -> None:
    original = methods.make_method("original")
    assert original.name == "original"
    assert original._acquire.__module__ == "_ds7_original_acquisition"
    assert original._score.__module__ == "_ds7_original_pilot_methods"
    with pytest.raises(ValueError, match="original, optimized"):
        methods.make_method("unknown")


@pytest.mark.parametrize("name", ("optimized", "candidates2"))
def test_blind_methods_return_complete_analysis_and_diagnostics(monkeypatch, name: str) -> None:
    configuration = _configuration()
    observed = []

    def run(_iq, effective, _edge, acquire, score):
        observed.append((effective, acquire, score))
        return _analysis(confirmed=False)

    monkeypatch.setattr(methods, "_run_detector", run)
    method = methods.make_method(name)
    result = method.analyze(_iq(configuration), configuration, "lower", _context())

    assert result.analysis.reason == "synthetic"
    assert result.diagnostics["route"] == "full_blind"
    assert result.diagnostics["detector_calls"] == 1
    expected_budget = 2 if name == "candidates2" else configuration.maximum_acquisition_candidates
    assert observed[0][0].maximum_acquisition_candidates == expected_budget
    assert result.diagnostics["acquisition_candidate_budget"] == expected_budget
    assert result.diagnostics["approximate"] is (name == "candidates2")


def test_context_and_iq_shape_are_strict(monkeypatch) -> None:
    configuration = _configuration()
    method = methods.make_method("optimized")
    monkeypatch.setattr(methods, "_run_detector", lambda *_args: _analysis(confirmed=False))
    with pytest.raises(ValueError, match="missing"):
        method.analyze(_iq(configuration), configuration, "lower", {})
    wrong_rate = {**_context(), "rate_hz": 5_000_000}
    with pytest.raises(ValueError, match="differs"):
        method.analyze(_iq(configuration), configuration, "lower", wrong_rate)
    with pytest.raises(ValueError, match="complex scanner dwell"):
        method.analyze(np.zeros((4, 1)), configuration, "lower", _context())


def test_local_cfo_uses_only_prior_confirmed_receiver_and_full_timing_grid(monkeypatch) -> None:
    configuration = _configuration(dwell_ms=40)
    method = methods.make_method("local_fallback")
    analyses = iter((_analysis(confirmed=True), _analysis(confirmed=True)))
    bounds = []

    def fake_acquire(_samples, _rate, _calibration, *, config, **_kwargs):
        bounds.append((config.residual_cfo_min_hz, config.residual_cfo_max_hz))
        return SimpleNamespace(candidates=())

    method._acquire = fake_acquire

    def run(_iq, effective, edge, acquire, _score):
        acquire(
            np.zeros(effective.probe_samples, dtype=np.complex128),
            effective.sample_rate_hz,
            ReceiverFrequencyCalibration("0", 0.0, "0" * 64),
            edge=edge,
            config=SymbolwiseAcquisitionConfig(
                maximum_probe_samples=effective.probe_samples,
                retained_candidate_count=effective.maximum_acquisition_candidates,
            ),
        )
        return next(analyses)

    monkeypatch.setattr(methods, "_run_detector", run)
    first = method.analyze(_iq(configuration), configuration, "lower", _context())
    second = method.analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(visit=1, counter=2_501_000),
    )

    assert first.diagnostics["route"] == "full_blind_no_prior"
    assert bounds[0] == (-400_000.0, 400_000.0)
    assert second.diagnostics["route"] == "local_cfo"
    assert second.diagnostics["detector_calls"] == 1
    # The latest member of the prior confirmed pair is 102 kHz.
    assert bounds[1] == (82_000.0, 122_000.0)
    assert second.diagnostics["local_seed_receiver_ids"] == [0]


def test_local_failure_reruns_whole_blind_dwell_and_returns_fallback(monkeypatch) -> None:
    configuration = _configuration(dwell_ms=40)
    method = methods.make_method("local_fallback")
    analyses = iter(
        (
            _analysis(confirmed=True),
            _analysis(confirmed=False),
            _analysis(confirmed=True, cfo=110_000.0),
        )
    )
    call_count = 0

    def run(*_args):
        nonlocal call_count
        call_count += 1
        return next(analyses)

    monkeypatch.setattr(methods, "_run_detector", run)
    method.analyze(_iq(configuration), configuration, "lower", _context())
    result = method.analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(visit=1, counter=2_501_000),
    )

    assert call_count == 3
    assert result.analysis.first is not None
    assert result.analysis.first.acquired_cfo_hz == 110_000.0
    assert result.diagnostics["route"] == "local_then_full_blind"
    assert result.diagnostics["detector_calls"] == 2
    assert result.diagnostics["missing_local_pair_receiver_ids"] == [0]


def test_local_state_expires_and_resets_when_session_changes(monkeypatch) -> None:
    configuration = _configuration(dwell_ms=40)
    method = methods.make_method("local_fallback")
    monkeypatch.setattr(
        methods,
        "_run_detector",
        lambda *_args: _analysis(confirmed=True),
    )
    method.analyze(_iq(configuration), configuration, "lower", _context())
    expired = method.analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(visit=1, counter=10_000_000),
    )
    changed = method.analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(visit=2, counter=10_100_000, session="new"),
    )
    assert expired.diagnostics["route"] == "full_blind_no_prior"
    assert changed.diagnostics["route"] == "full_blind_no_prior"
    assert changed.diagnostics["session_reset"] is True
