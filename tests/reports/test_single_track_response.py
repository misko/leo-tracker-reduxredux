"""Synthetic checks for training-only per-tone response normalization."""
import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/improvements/response/analyze_response.py"
spec = importlib.util.spec_from_file_location("single_track_response", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def fixture(delay=170e-9, phase=.7):
    frequency = np.arange(8) * 234375.0
    frames = 12
    common = np.exp(1j * np.linspace(-.2, .3, frames))[:, None]
    receiver_phase = np.exp(1j * (phase - 2*np.pi*frequency*delay))[None, :]
    h0 = np.ones((frames, 8), complex)
    h1 = common * receiver_phase
    return frequency, np.stack([h0, h1], axis=1)


def test_injected_delay_is_removed_without_removing_frame_phase():
    _, channel = fixture()
    train = np.arange(len(channel)) < 3
    result = M.apply_response(channel, M.fit_training_response(channel, train))
    expected = np.angle(np.exp(1j*np.linspace(-.2, .3, len(channel))), deg=True)
    offset = np.angle(np.exp(1j*np.radians(result["normalized_phase_deg"] - expected)), deg=True)
    assert np.ptp(offset) < 1e-10
    np.testing.assert_allclose(result["tone_agreement"], 1, atol=1e-12)


def test_held_frames_cannot_leak_into_calibration():
    _, channel = fixture()
    train = np.arange(len(channel)) < 3
    first = M.fit_training_response(channel, train)
    changed = channel.copy()
    changed[~train, 1] *= np.exp(1j * np.arange(8))
    second = M.fit_training_response(changed, train)
    np.testing.assert_array_equal(first["response"], second["response"])
    np.testing.assert_array_equal(first["tone_mean"], second["tone_mean"])


def test_common_receiver_phase_is_retained_as_a_gauge():
    _, channel = fixture()
    train = np.arange(len(channel)) < 3
    shifted = channel.copy()
    shifted[:, 1] *= np.exp(1j * .43)
    base_cal = M.fit_training_response(channel, train)
    shifted_cal = M.fit_training_response(shifted, train)
    np.testing.assert_allclose(base_cal["response"], shifted_cal["response"], atol=1e-14)
    base = M.apply_response(channel, base_cal)["normalized_phase_deg"]
    moved = M.apply_response(shifted, shifted_cal)["normalized_phase_deg"]
    delta = np.angle(np.exp(1j * np.radians(moved - base)), deg=True)
    np.testing.assert_allclose(delta, np.degrees(.43), atol=1e-12)


def test_delay_audit_reports_tone_spacing_ambiguity():
    frequency, channel = fixture(delay=310e-9)
    z = np.sum(np.conj(channel[:3, 0]) * channel[:3, 1], axis=0)
    audit = M.delay_audit(z, frequency)
    assert abs(audit["principal_delay_s"] - 310e-9) < 1e-14
    assert abs(audit["alias_period_s"] - 1/234375) < 1e-14
    aliases = np.asarray(audit["nearby_alias_delays_s"])
    np.testing.assert_allclose(np.diff(aliases), audit["alias_period_s"])
