"""Check archival IF extraction and matched search without requiring a network source."""

import json

import numpy as np
import pytest

from tools.pipeline_eval.qualification import austin_waveform as wave


def test_exact_edge_translation_rejects_a_would_be_decimation_alias():
    sky = 12_075_117_197.1668
    offset = wave.EDGE_HZ["upper"] - sky
    t = np.arange(250_000) / wave.ADC_RATE
    wanted = 83_000
    unwanted = 7_063_000
    value = 2_000 * np.exp(2j * np.pi * (offset + wanted) * t)
    value += 2_000 * np.exp(2j * np.pi * (offset + unwanted) * t)
    raw = np.rint(np.column_stack((value.real, value.imag))).astype("<i2")
    recovered = wave.extract_edge(raw, sky, "upper")
    assert len(recovered) == 10_000
    magnitude = np.abs(np.fft.fft(recovered))

    def center(f):
        return round(len(recovered) * f / wave.RATE) % len(recovered)

    assert magnitude.argmax() == center(wanted)
    assert magnitude[center(wanted)] > 10_000 * magnitude[center(unwanted)]
    with pytest.raises(ValueError, match="beyond the primary RF span"):
        wave.extract_edge(raw, sky - 15e6, "upper")


def test_spectrum_null_and_native_template_controls_keep_shape_and_energy():
    rng = np.random.default_rng(83)
    z = (rng.normal(size=2_048) + 1j * rng.normal(size=2_048)).astype(np.complex64)
    other = wave.phase_null(z, 231)
    np.testing.assert_allclose(
        np.abs(np.fft.fft(other)), np.abs(np.fft.fft(z)), rtol=2e-6, atol=2e-5
    )
    assert abs(np.vdot(z, other) / np.vdot(z, z)) < 0.1
    bank = wave.templates_at("lower")
    exact = bank["exact"][0]
    np.testing.assert_array_equal(exact, bank["roll17"][1])
    for template in bank["shuffled"]:
        assert template.shape == exact.shape and template.dtype == np.dtype("<c16")
        assert np.linalg.norm(template) == pytest.approx(np.linalg.norm(exact))
        assert not np.array_equal(template, exact)


def test_authored_reference_requires_whole_frame_and_exact_scan_scores_folded_phase():
    mark = {
        "sliceInfo.json": json.dumps(
            {"frameSet": {"index": [31, 32], "toa_s": [0.001, 0.0498], "nWhole": 1}}
        )
    }
    known = wave.ordered_frames(mark)
    assert known == [(31, 0.001)]
    candidate = dict(
        epoch=10_008,
        acquired_cfo_hz=9001,
        fractional_epoch=dict(
            status="complete",
            offset_samples=0.5,
            margin=0.04,
            exact_score=0.08,
            control_score=0.04,
            tracking_cfo_hz=9002,
        ),
    )
    rows = [
        dict(
            edge="lower",
            panel="physical",
            template="exact",
            start_ms=0,
            cpu_s=1.0,
            native={"rows": [{"candidates": [candidate]}]},
        )
    ]
    receipt = wave.detector_score(rows, known, {})[0]
    assert receipt["passed"] and receipt["matches_relative_phase"]
    assert receipt["relative_phase_residual_samples"] == pytest.approx(8.5)


def test_conditioned_frame_uses_same_search_for_all_code_orders():
    edge = "upper"
    template = wave.templates_at(edge)["exact"][0]
    wave_iq = np.zeros(25_000, dtype=np.complex64)
    start = 8_000
    t = np.arange(len(template)) / wave.RATE
    wave_iq[start : start + len(template)] = template * np.exp(2j * np.pi * 11_000 * t)
    rows = wave.frame_scores(wave_iq, [(1, start / wave.RATE)], edge)
    assert len(rows) == 3 and len({r["template_hypotheses"] for r in rows}) == 1
    assert rows[0]["score"] > 0.99
    assert rows[0]["timing_offset_samples"] == 0
    assert abs(rows[0]["mixer_relative_hz"] - 11_000) < 155
    assert all(r["score"] < 0.1 for r in rows[1:])
