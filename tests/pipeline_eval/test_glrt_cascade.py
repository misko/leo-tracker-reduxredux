import json
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.variants import glrt_cascade as cascade


@pytest.fixture
def waveform():
    rng = np.random.default_rng(4931)
    window = 0.12 * (rng.standard_normal(200_000) + 1j * rng.standard_normal(200_000))
    template = qin_edge_pilot_frame(10_000_000, "lower")
    epoch = 700
    cfo_hz = (1 + 51 / 512) / 4.4e-6
    for frame in range(15):
        start = round(frame * 10_000_000 / 750) + epoch
        end = min(start + len(template), len(window))
        window[start:end] += template[: end - start]
    window *= np.exp(2j * np.pi * cfo_hz * np.arange(len(window)) / 10_000_000)
    return window


def test_detection_preserves_winner_on_known_pilot(waveform):
    bank = cascade.PilotSearch("lower")
    control = bank.search(waveform, gated=False)
    candidate = bank.search(waveform, gated=True)

    assert candidate.winner == control.winner
    assert candidate.winner is not None
    assert candidate.winner.epoch_sample == pytest.approx(700, abs=cascade.REFINE_SAMPLES)
    assert candidate.winner.absolute_cfo_hz == pytest.approx((1 + 51 / 512) / 4.4e-6)
    assert 0 < candidate.rolled_fft_cells < control.rolled_fft_cells
    assert candidate.exact_fft_cells == control.exact_fft_cells


def test_phase_randomized_negative_rejects_in_both_arms(waveform):
    bank = cascade.PilotSearch("lower")
    null = cascade.phase_randomized_null(waveform)
    control = bank.search(null, gated=False)
    candidate = bank.search(null, gated=True)

    np.testing.assert_allclose(
        abs(np.fft.fft(waveform)),
        abs(np.fft.fft(null)),
        atol=1e-9,
        rtol=1e-9,
    )
    assert control.winner is None
    assert candidate.winner is None
    assert candidate.rolled_fft_cells < control.rolled_fft_cells


def test_run_reports_paired_windows_and_null(monkeypatch, tmp_path, waveform):
    from tools.pipeline_eval.variants import iq_stream

    samples = np.zeros((200_000, 2, 2), dtype="<i2")
    samples[:, 0, :] = 1_000 * np.stack((waveform.real, waveform.imag), axis=-1)
    windows = tuple(
        SimpleNamespace(
            sequence=sequence,
            samples=samples,
            receiver_ids=(0, 1),
            sample_rate_hz=10_000_000,
            target={"edge": "lower"},
            iq_sha256=f"test-window-{sequence}",
        )
        for sequence in (0, 1)
    )
    monkeypatch.setattr(iq_stream, "load_windows", lambda case, sequences: windows)
    monkeypatch.setattr(cascade, "REPEATS", 1)

    result = cascade.run({"panel": "DS26"}, tmp_path)

    assert result["status"] == "ok"
    metrics = result["metrics"]
    assert metrics["windows"] == 4
    assert metrics["control_positive"] == metrics["candidate_positive"] == 2
    assert metrics["control_negative"] == 2
    assert metrics["false_promotions"] == metrics["missed_detections"] == 0
    assert metrics["changed_winners"] == metrics["changed_cfo"] == 0
    assert metrics["null_candidate_positive"] == 0
    assert metrics["null_windows"] == 1
    detail = json.loads((tmp_path / "waveform-comparison.json").read_bytes())
    assert {item["iq_sha256"] for item in detail["real"]} == {
        "test-window-0",
        "test-window-1",
    }


def test_missing_roof_recording_is_explicit(tmp_path):
    reply = cascade.run({"id": "missing", "panel": "DS29"}, tmp_path)

    assert reply["status"] == "unavailable"
    assert reply["reason"]
