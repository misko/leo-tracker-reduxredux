"""Measure pilot-band support from the pinned receiver assets without processing a recording."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.signal import firwin


RATE = 10_000_000
FFT_LENGTH = 1 << 17
PINS = {
    "lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
    "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c",
}


def measure(assets):
    frequencies = np.fft.fftfreq(FFT_LENGTH, 1 / RATE)
    narrow = np.abs(frequencies) <= RATE / 16
    fir8 = np.abs(np.fft.fft(firwin(161, 1 / 8, window=("kaiser", 5.)), FFT_LENGTH)) ** 2
    tone_hz = (np.arange(8) - 3.5) * 234_375
    reference_tones = np.abs(tone_hz) <= RATE / 16
    cases = {}
    for edge, pin in PINS.items():
        data = (assets / f"{edge}.f32").read_bytes()
        if hashlib.sha256(data).hexdigest() != pin:
            raise ValueError(f"pilot asset changed for {edge}")
        fields = np.frombuffer(data, dtype="<f4")
        pilot = fields[:2 * 13333].view("<c8")[88:88 + 128 * 44].astype(np.complex128)
        fir4 = np.abs(np.fft.fft(fields[4 * 13333:4 * 13333 + 81], FFT_LENGTH)) ** 2
        time = np.arange(len(pilot)) / RATE
        rows = []
        for carrier in (-800000, -625000, -400000, 0, 400000, 625000, 800000):
            spectrum = np.abs(np.fft.fft(pilot * np.exp(2j * np.pi * carrier * time), FFT_LENGTH)) ** 2
            quarter = spectrum * fir4
            tone_inside = np.abs(tone_hz + carrier) <= RATE / 16
            legal = np.count_nonzero(tone_inside)
            shared = np.count_nonzero(tone_inside & reference_tones)
            rows.append(dict(signed_cfo_hz=carrier, tone_centers_inside=int(legal),
                             tone_centers_shared_with_unshifted_reference=int(shared),
                             baseline_energy_below_half_rate_nyquist=float(quarter[narrow].sum() / quarter.sum()),
                             proposed_prefilter_energy_relative_to_baseline=float((spectrum * fir8).sum() / quarter.sum())))
        cases[edge] = rows
    return dict(native_rate_hz=RATE, pilot_tone_centers_hz=tone_hz.tolist(),
                scout_rates_hz=dict(frozen=RATE // 4, proposed=RATE // 8),
                nominal_phase_bins=dict(frozen=round(RATE / 4 / 750), proposed=round(RATE / 8 / 750)),
                edge_assets_sha256=PINS, fft_points=FFT_LENGTH, cases=cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.assets), indent=2))
