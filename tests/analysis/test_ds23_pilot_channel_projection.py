import numpy as np

from ds23_pilot_channel_projection import (
    advance_samples, pilot_tone_frames, project_arbitrary_pilot_symbols,
    project_pilot_channel, tone_waves,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from probe_native_code_carrier import interpolate_periodic


def test_tones_reconstruct_published_template():
    for edge in ('lower', 'upper'):
        np.testing.assert_allclose(pilot_tone_frames(2_500_000, edge).sum(axis=1),
                                   qin_edge_pilot_frame(2_500_000, edge), atol=2e-7)


def test_frequency_selective_projection_removes_known_pilots_and_keeps_noise():
    fs = 2_500_000
    n = np.arange(50_000)
    epoch = 500.2
    fit = dict(CFO_hz=12345., offset_samples=.12, modulation_ppm=1.3)
    position = (n - epoch - fit['offset_samples']) * (1 + fit['modulation_ppm'] * 1e-6) * 32
    rng = np.random.default_rng(481)
    gain = rng.normal(size=8) + 1j * rng.normal(size=8)
    known = sum(c * interpolate_periodic(wave, position)
                for c, wave in zip(gain, tone_waves(fs, 'lower')))
    known *= np.exp(2j * np.pi * fit['CFO_hz'] * (n/fs - (n/fs).mean()))
    noise = .1 * (rng.normal(size=len(n)) + 1j * rng.normal(size=len(n)))
    residual, details = project_pilot_channel(known + noise + 1j, fs, 'lower', epoch, fit)
    active = abs(residual) > 0
    assert details['frames'] >= 10
    assert np.mean(abs(residual[active])**2) / np.mean(abs(noise[active])**2) > .98
    assert np.mean(abs(residual[active] - noise[active])**2) < .0003


def test_arbitrary_symbol_nuller_rejects_different_known_sequences():
    fs = 2_500_000
    n = np.arange(50_000)
    epoch = 500.
    fit = dict(CFO_hz=12345., offset_samples=0., modulation_ppm=0.)
    # Direct unfiltered template fits the per-symbol null space exactly.
    frame = pilot_tone_frames(fs, 'lower').sum(axis=1)
    samples = np.zeros(len(n), complex)
    for k in range(14):
        start = round(epoch + k*fs/750)
        if start+len(frame) <= len(n):
            samples[start:start+len(frame)] = frame
    samples *= np.exp(2j*np.pi*fit['CFO_hz']*n/fs)
    # Rounded frame starts differ fractionally from the native continuous
    # period; only the first exactly aligned frame is an exact oracle.
    residual, _ = project_arbitrary_pilot_symbols(samples, fs, 'lower', epoch, fit)
    assert np.max(abs(residual[530:3800])) < 1e-10


def test_epoch_control_fractional_advance_sign_and_amplitude():
    n = np.arange(50000)
    frequency = .1
    samples = np.exp(2j*np.pi*frequency*n)
    shifted = advance_samples(samples, 31.25)
    expected = np.exp(2j*np.pi*frequency*(n+31.25))
    np.testing.assert_allclose(shifted[5000:-5000], expected[5000:-5000], atol=1e-4)
