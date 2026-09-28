from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import leo.scanner.detector as detector
from leo.scanner import ScannerConfiguration, current_low_band_targets

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds7_sparse_methods", HERE / "methods_sparse.py")
assert SPEC is not None and SPEC.loader is not None
sparse = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sparse
SPEC.loader.exec_module(sparse)


def _configuration() -> ScannerConfiguration:
    return ScannerConfiguration(
        receiver_ids=(0, 1),
        maximum_acquisition_candidates=8,
        targets=current_low_band_targets()[:1],
    )


def _iq(configuration: ScannerConfiguration) -> np.ndarray:
    values = np.empty(
        (configuration.dwell_samples, len(configuration.receiver_ids)),
        dtype=np.complex128,
    )
    indexes = np.arange(configuration.dwell_samples)
    for column, receiver in enumerate(configuration.receiver_ids):
        values[:, column] = indexes + 1j * receiver
    return values


def _context(configuration: ScannerConfiguration) -> dict[str, object]:
    return {
        "session_id": "s",
        "visit_index": 7,
        "sample_start_counter": 1_000,
        "rate_hz": configuration.sample_rate_hz,
        "target_index": 0,
    }


def _fake_functions(configuration, passing, *, calls=None, cfo_offset=None):
    stride = configuration.probe_stride_samples

    def acquire(probe, _rate, calibration, *, config, **_kwargs):
        probe_index = round(float(probe[0].real)) // stride
        receiver = int(calibration.receiver_id)
        if calls is not None:
            calls.append((receiver, probe_index, config.retained_candidate_count))
        return SimpleNamespace(
            candidates=tuple(
                SimpleNamespace(
                    rank=rank,
                    refined_epoch_sample=rank,
                    absolute_cfo_hz=100_000.0 + receiver * 20_000.0 + rank,
                )
                for rank in range(config.retained_candidate_count)
            )
        )

    def score(probe, _rate, *, acquired_cfo_hz, **_kwargs):
        probe_index = round(float(probe[0].real)) // stride
        receiver = round(float(probe[0].imag))
        rank = round(acquired_cfo_hz) % 10
        passed = (receiver, probe_index) in passing
        tracking = 200_000.0 + receiver * 20_000.0
        if cfo_offset is not None:
            tracking += cfo_offset(receiver, probe_index, rank)
        margin = 0.08 + rank * 0.001 if passed else -0.02
        return SimpleNamespace(
            residual_cfo_hz=tracking - acquired_cfo_hz,
            tracking_cfo_hz=tracking,
            exact_score=margin + 0.1,
            control_score=0.1,
            margin=margin,
        )

    return acquire, score


@pytest.mark.parametrize(
    ("passing", "cfo_offset"),
    (
        (set(), None),
        ({(0, 0), (0, 2)}, None),
        (
            {(0, 0), (0, 2)},
            lambda receiver, index, _rank: 8_000.001 if receiver == 0 and index == 2 else 0.0,
        ),
    ),
)
def test_actually_executed_full_schedule_matches_repository_fold(
    monkeypatch, passing, cfo_offset
) -> None:
    configuration = _configuration()
    acquire, score = _fake_functions(
        configuration,
        passing,
        cfo_offset=cfo_offset,
    )
    monkeypatch.setattr(sparse, "acquire_symbolwise", acquire)
    monkeypatch.setattr(sparse, "conditioned_glrt64_score", score)
    monkeypatch.setattr(detector, "acquire_symbolwise", acquire)
    monkeypatch.setattr(detector, "conditioned_glrt64_score", score)
    values = _iq(configuration)

    expected = detector.analyze_glrt64_dwell(values, configuration, edge="lower")
    actual = sparse.make_method("optimized_full").analyze(
        values,
        configuration,
        "lower",
        _context(configuration),
    )

    assert actual.analysis == expected
    assert actual.diagnostics["route"] == "complete_schedule"
    assert actual.diagnostics["acquisition_calls"] == 22
    assert actual.diagnostics["glrt_candidate_calls"] == 176


@pytest.mark.parametrize(
    ("name", "indices", "budget"),
    (
        ("windows6", [0, 2, 4, 6, 8, 10], 8),
        ("windows4", [0, 3, 6, 9], 8),
        ("windows3", [0, 5, 10], 8),
        ("windows6_candidates2", [0, 2, 4, 6, 8, 10], 2),
        ("windows4_candidates2", [0, 3, 6, 9], 2),
        ("candidates4", list(range(11)), 4),
        ("candidates6", list(range(11)), 6),
    ),
)
def test_fixed_methods_execute_only_declared_work(monkeypatch, name, indices, budget) -> None:
    configuration = _configuration()
    calls = []
    acquire, score = _fake_functions(configuration, set(), calls=calls)
    monkeypatch.setattr(sparse, "acquire_symbolwise", acquire)
    monkeypatch.setattr(sparse, "conditioned_glrt64_score", score)

    result = sparse.make_method(name).analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(configuration),
    )

    expected_calls = [
        (receiver, index, budget)
        for index in indices
        for receiver in configuration.receiver_ids
    ]
    assert calls == expected_calls
    assert result.diagnostics["acquisition_calls"] == len(expected_calls)
    assert result.diagnostics["glrt_candidate_calls"] == len(expected_calls) * budget
    assert result.diagnostics["processed_probe_indices_by_receiver"] == {
        "0": indices,
        "1": indices,
    }
    assert [
        (response.probe_index, response.receiver_id) for response in result.analysis.probes
    ] == [(index, receiver) for index in indices for receiver in (0, 1)]


def test_progressive_stops_receivers_independently_and_reuses_initial_work(monkeypatch) -> None:
    configuration = _configuration()
    calls = []
    acquire, score = _fake_functions(
        configuration,
        {(0, 0), (0, 3), (1, 1), (1, 4)},
        calls=calls,
    )
    monkeypatch.setattr(sparse, "acquire_symbolwise", acquire)
    monkeypatch.setattr(sparse, "conditioned_glrt64_score", score)

    result = sparse.make_method("progressive4").analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(configuration),
    )

    assert result.diagnostics["route"] == "progressive_fallback_confirmed"
    assert result.diagnostics["acquisition_calls"] == 11
    assert result.diagnostics["fallback_probe_indices"] == [1, 2, 4]
    assert result.diagnostics["processed_probe_indices_by_receiver"] == {
        "0": [0, 3, 6, 9],
        "1": [0, 1, 2, 3, 4, 6, 9],
    }
    assert result.diagnostics["confirmed_receiver_ids"] == [0, 1]
    keys = [(receiver, index) for receiver, index, _budget in calls]
    assert len(keys) == len(set(keys))
    assert all(receiver == 1 for receiver, index in keys[8:] if index not in (0, 3, 6, 9))
    assert [
        (response.probe_index, response.receiver_id) for response in result.analysis.probes
    ] == sorted(
        ((index, receiver) for receiver, index in keys),
        key=lambda item: (item[0], item[1]),
    )


def test_progressive_initial_confirmation_performs_no_fallback(monkeypatch) -> None:
    configuration = _configuration()
    calls = []
    acquire, score = _fake_functions(
        configuration,
        {(0, 0), (0, 3), (1, 0), (1, 3)},
        calls=calls,
    )
    monkeypatch.setattr(sparse, "acquire_symbolwise", acquire)
    monkeypatch.setattr(sparse, "conditioned_glrt64_score", score)

    result = sparse.make_method("progressive4").analyze(
        _iq(configuration),
        configuration,
        "lower",
        _context(configuration),
    )

    assert result.diagnostics["route"] == "progressive_initial"
    assert result.diagnostics["acquisition_calls"] == 8
    assert result.diagnostics["fallback_probe_indices"] == []
    assert len(calls) == 8


def test_progressive_preserves_per_receiver_pair_existence_across_varied_patterns(
    monkeypatch,
) -> None:
    configuration = _configuration()
    values = _iq(configuration)
    context = _context(configuration)
    cfo_choices = np.array((-16_001.0, -8_000.0, 0.0, 8_000.0, 16_001.0))

    for seed in range(96):
        generator = np.random.default_rng(20_260_928 + seed)
        passing = {
            (receiver, probe)
            for receiver in configuration.receiver_ids
            for probe in range(configuration.scheduled_probe_count)
            if generator.random() < 0.38
        }
        offsets = {
            (receiver, probe): float(generator.choice(cfo_choices))
            for receiver in configuration.receiver_ids
            for probe in range(configuration.scheduled_probe_count)
        }
        acquire, score = _fake_functions(
            configuration,
            passing,
            cfo_offset=(
                lambda receiver, index, _rank, offset_map=offsets: offset_map[
                    (receiver, index)
                ]
            ),
        )
        monkeypatch.setattr(sparse, "acquire_symbolwise", acquire)
        monkeypatch.setattr(sparse, "conditioned_glrt64_score", score)

        oracle = {
            receiver
            for receiver in configuration.receiver_ids
            if any(
                (receiver, first) in passing
                and (receiver, second) in passing
                and second - first >= 2
                and abs(offsets[(receiver, second)] - offsets[(receiver, first)]) <= 8_000.0
                for first in range(configuration.scheduled_probe_count)
                for second in range(first + 1, configuration.scheduled_probe_count)
            )
        }
        full = sparse.make_method("optimized_full").analyze(
            values,
            configuration,
            "lower",
            context,
        )
        progressive = sparse.make_method("progressive4").analyze(
            values,
            configuration,
            "lower",
            context,
        )

        assert set(full.diagnostics["confirmed_receiver_ids"]) == oracle
        assert set(progressive.diagnostics["confirmed_receiver_ids"]) == oracle
        assert (full.analysis.first is not None) is bool(oracle)
        assert (progressive.analysis.first is not None) is bool(oracle)
        for receiver in configuration.receiver_ids:
            processed = progressive.diagnostics["processed_probe_indices_by_receiver"][
                str(receiver)
            ]
            assert len(processed) == len(set(processed))
            if receiver not in oracle:
                assert processed == list(range(configuration.scheduled_probe_count))
            elif processed != list(range(configuration.scheduled_probe_count)):
                assert receiver in progressive.diagnostics["confirmed_receiver_ids"]


def test_unknown_method_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown sparse method"):
        sparse.make_method("future_oracle")
