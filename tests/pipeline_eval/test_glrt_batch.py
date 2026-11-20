import json

import numpy as np
import pytest

from tools.pipeline_eval.reference import waveform as reference
from tools.pipeline_eval.variants import glrt_batch, iq_stream


def test_short_autocorrelation_reproduces_the_full_power_grid():
    rng = np.random.default_rng(742)
    symbols = rng.normal(size=(2, 5, 15, 64)) + 1j * rng.normal(size=(2, 5, 15, 64))
    symbols[0, 1, :4] = 0
    direct = np.sum(np.abs(np.fft.fft(symbols, n=512, axis=-1)) ** 2, axis=-2)

    np.testing.assert_allclose(glrt_batch.summed_grid_power(symbols, 512), direct, rtol=1e-14)


@pytest.mark.parametrize(("edge", "has_pilot"), [("lower", True), ("upper", False)])
def test_blind_search_keeps_peak_decision_and_cells(edge, has_pilot):
    direct = reference.PilotBank(edge)
    batched = glrt_batch.BatchedPilotBank(direct, reference)
    rng = np.random.default_rng(360)
    count = reference.PROBE_SAMPLES
    samples = 0.08 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    counter = 99_907
    if has_pilot:
        wave = reference.qin_edge_pilot_frame(reference.RATE, edge)
        epoch = 2_991
        frequency = 37_000
        for offset in np.rint(np.arange(14) * reference.RATE / 750).astype(int):
            start = offset + epoch
            stop = min(count, start + wave.size)
            angle = 2j * np.pi * frequency / reference.RATE
            samples[start:stop] += wave[: stop - start] * np.exp(angle * np.arange(start, stop))

    expected = direct.search(samples, counter)
    observed = batched.search(samples, counter)
    comparison = glrt_batch._compare(expected, observed, reference)

    assert comparison["control_passed"] == comparison["candidate_passed"] == has_pilot
    assert comparison["work_equal"]
    assert comparison["peak_equal"]
    assert comparison["wrapped_cfo_error_hz"] == 0
    assert comparison["wrapped_phase_error_us"] == 0
    assert max(comparison[key] for key in glrt_batch.ERROR_KEYS[2:]) <= glrt_batch.SCORE_TOLERANCE


def test_run_times_both_arms_on_the_same_window_inputs(monkeypatch, tmp_path):
    rng = np.random.default_rng(15)
    iq = rng.integers(-64, 65, size=(reference.PROBE_SAMPLES, 1, 2), dtype=np.int16)
    windows = tuple(
        iq_stream.IQWindow(
            sequence,
            np.roll(iq, sequence, axis=0),
            (0,),
            reference.RATE,
            {"sample_start": 13 + sequence * reference.PROBE_SAMPLES},
            "ch1-lower-lo9750000000",
            {"edge": "lower"},
            f"input-{sequence}",
        )
        for sequence in (0, 1)
    )
    monkeypatch.setattr(iq_stream, "load_windows", lambda *args, **kwargs: windows)
    monkeypatch.setattr(glrt_batch, "REPEATS", 2)

    result = glrt_batch.run({"id": "test", "panel": "Synthetic"}, tmp_path)

    assert result["status"] == "ok"
    metrics = result["metrics"]
    assert metrics["receiver_windows"] == 2
    assert metrics["complex_samples"] == 2 * reference.PROBE_SAMPLES
    assert metrics["control_negatives"] == metrics["candidate_negatives"] == 2
    assert metrics["decision_disagreements"] == metrics["peak_disagreements"] == 0
    assert metrics["work_disagreements"] == metrics["score_tolerance_violations"] == 0
    assert all(len(metrics[f"{arm}_s_repeats"]) == 2 for arm in ("control", "candidate"))
    artifact = json.loads((tmp_path / "waveform-parity.json").read_text())
    assert [scan["iq_sha256"] for scan in artifact["scans"]] == ["input-0", "input-1"]


def test_run_reports_missing_samples(tmp_path):
    result = glrt_batch.run({"id": "missing", "panel": "Synthetic"}, tmp_path)

    assert result["status"] == "unavailable"
    assert result["reason"] == "case is absent from the frozen raw IQ inventory"
