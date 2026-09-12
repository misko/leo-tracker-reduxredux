"""Noiseless fractional-delay control isolating interpolation from track fitting."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score, refine_glrt64_epoch
from leo.analysis.starlink.pss_timing import _fractional_match_peak, pss_subband_template
from leo.analysis.starlink.templates import qin_edge_pilot_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    records = []
    for rate in (2_500_000, 25_000_000):
        # Match the scorer's frame geometry to isolate the fractional peak fit.
        # This is an estimator control, not a physical clock/time-scaling simulation.
        count = int(np.ceil(15 * rate / 750)) + 200
        pilot = np.zeros(count, dtype=complex)
        template = qin_edge_pilot_frame(rate, "lower")
        for frame in range(15):
            start = 100 + round(frame * rate / 750)
            pilot[start : start + len(template)] = template
        pilot_fft = np.fft.fft(pilot)
        pilot_freq = np.fft.fftfreq(count)
        offset = -115_195_312.5 if rate == 2_500_000 else -107_382_812.5
        pss_template = pss_subband_template(rate, slice_center_offset_hz=offset)
        pss = np.zeros(1024, dtype=complex)
        pss[400 : 400 + len(pss_template)] = pss_template
        pss_fft, pss_freq = np.fft.fft(pss), np.fft.fftfreq(len(pss))
        for fraction in np.linspace(-0.45, 0.45, 19):
            samples = np.fft.ifft(pilot_fft * np.exp(-2j * np.pi * pilot_freq * fraction))
            original = refine_glrt64_epoch(
                samples, rate, integer_epoch_sample=100, acquired_cfo_hz=0.0, edge="lower"
            )
            if original.fractional_epoch_offset_samples is None:
                raise ValueError("synthetic GLRT peak not bracketed")

            def objective(delay, samples=samples, rate=rate):
                return -conditioned_glrt64_score(
                    samples,
                    rate,
                    epoch_sample=100,
                    acquired_cfo_hz=0.0,
                    edge="lower",
                    fractional_epoch_offset_samples=delay,
                ).exact_score

            optimum = minimize_scalar(
                objective, bounds=(-0.6, 0.6), method="bounded", options={"xatol": 1e-5}
            )
            if not optimum.success or abs(optimum.x) >= 0.599:
                raise ValueError("synthetic continuous GLRT peak unsupported")
            values = np.fft.ifft(pss_fft * np.exp(-2j * np.pi * pss_freq * fraction))
            pss_offsets = {}
            for half in (8, 32):
                delay, _, _ = _fractional_match_peak(
                    values, pss_template, search_start=399, search_stop=402, half_width=half
                )
                pss_offsets[str(half)] = (delay - 400 - fraction) / rate * 1e9
            records.append(
                dict(
                    sample_rate_hz=rate,
                    true_fractional_delay_samples=float(fraction),
                    glrt_parabolic_error_ns=float(
                        (original.fractional_epoch_offset_samples - fraction) / rate * 1e9
                    ),
                    glrt_continuous_score_error_ns=float((optimum.x - fraction) / rate * 1e9),
                    pss_current_error_ns=float(pss_offsets["8"]),
                    pss_longer_kernel_error_ns=float(pss_offsets["32"]),
                )
            )
        print("completed", rate, "19 fractional phases", flush=True)
    args.output.write_text(
        json.dumps(
            dict(
                records=records,
                protocol="Noiseless, exact nominal pilot/PSS templates, "
                "Fourier-imposed fractional delays; "
                "GLRT source frame starts match scorer's round(frame*Fs/750) geometry. "
                "Not a physical clock, analog-filter, adjacent-payload "
                "or independent-radio simulation. "
                "Same exact GLRT score function used before/after continuous local optimization; "
                "PSS compares current 16-tap and diagnostic 64-tap IQ interpolation.",
            ),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
