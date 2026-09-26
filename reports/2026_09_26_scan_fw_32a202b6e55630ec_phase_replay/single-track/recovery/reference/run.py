#!/usr/bin/env python3
"""Synthetic demonstration of independent-reference phase calibration.

The reference is an explicit input.  Nothing in this module infers a hardware
reference from the satellite being measured.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


def wrap(x):
    return np.angle(np.exp(1j * x))


def circular_rmse(estimate, truth):
    return float(np.sqrt(np.mean(wrap(np.asarray(estimate) - truth) ** 2)))


def simulate(seed=32, n=2400, tones=16, delay_samples=2, reference_noise=.035,
             missing_fraction=.0):
    """Create complex cross-products with known geometry and instrumentation."""
    rng = np.random.default_rng(seed)
    dt = 1 / 750.0  # representative frame cadence, simulation only
    t = np.arange(n) * dt
    f = (np.arange(tones) - (tones - 1) / 2) * 234_375.0
    # Slow geometric phase: about 190 degrees over this short synthetic pass.
    geometry = .28 + .72 * t + .095 * t**2 + .045 * np.sin(2*np.pi*t/2.7)
    # Receiver differential phase includes a large relative CFO and drift.
    instrument = -1.1 + 2*np.pi*682_400.0*t + 2*np.pi*7.5*t**2
    response = .7*np.sin(f / 7.0e5) + 2*np.pi*f*180e-9
    injection = -.37 + 2*np.pi*f*41e-9

    def noisy(phase, sigma):
        return np.exp(1j * (phase + rng.normal(0, sigma, np.shape(phase))))

    sat = noisy(geometry[:, None] + instrument[:, None] + response[None, :], .07)
    # ref[k] sees the instrument from k-delay; prepend unavailable samples.
    ref = np.full((n, tones), np.nan + 1j*np.nan)
    if delay_samples:
        ref[delay_samples:] = noisy(
            instrument[:-delay_samples, None] + response[None, :] + injection[None, :],
            reference_noise,
        )
    else:
        ref[:] = noisy(
            instrument[:, None] + response[None, :] + injection[None, :],
            reference_noise,
        )
    if missing_fraction:
        miss = rng.random(n) < missing_fraction
        ref[miss] = np.nan + 1j*np.nan
    config = {
        "seed": seed, "frames": n, "cadence_hz": 1/dt, "tones": tones,
        "tone_spacing_hz": 234_375.0, "reference_delay_samples": delay_samples,
        "satellite_phase_noise_rad": .07, "reference_phase_noise_rad": reference_noise,
        "missing_reference_fraction": missing_fraction,
        "geometry_rad": ".28 + .72*t + .095*t^2 + .045*sin(2*pi*t/2.7)",
        "instrument_rad": "-1.1 + 2*pi*682400*t + 2*pi*7.5*t^2",
        "response_rad": ".7*sin(f/7e5) + 2*pi*f*180e-9",
        "injection_rad": "-.37 + 2*pi*f*41e-9",
    }
    return dict(t=t, frequency_hz=f, satellite=sat, reference=ref,
                injection=np.exp(1j*injection), geometry=geometry,
                delay_samples=delay_samples, dt=dt, config=config)


def recover(satellite, reference, injection_phasor, delay_samples, train_mask):
    """Calibrate using an independently observed, timestamped hardware reference.

    `delay_samples` and `injection_phasor` are calibration metadata. They are not
    estimated from geometric truth or from the satellite phase.
    """
    satellite = np.asarray(satellite, complex)
    reference = np.asarray(reference, complex)
    injection_phasor = np.asarray(injection_phasor, complex)
    train_mask = np.asarray(train_mask, bool)
    if satellite.shape != reference.shape or satellite.ndim != 2:
        raise ValueError("satellite and reference must be equal frame-by-tone arrays")
    if injection_phasor.shape != (satellite.shape[1],):
        raise ValueError("known injection path must provide one phasor per tone")
    if train_mask.shape != (satellite.shape[0],):
        raise ValueError("train mask must provide one value per frame")
    if (not np.all(np.isfinite(injection_phasor)) or
            np.any(np.abs(injection_phasor) <= 1e-12)):
        raise ValueError("known injection phasors must be finite and nonzero")
    if delay_samples < 0 or delay_samples >= satellite.shape[0]:
        raise ValueError("reference delay is unsupported")
    aligned = np.full_like(reference, np.nan + 1j*np.nan)
    if delay_samples:
        aligned[:-delay_samples] = reference[delay_samples:]
    else:
        aligned[:] = reference
    valid_tone = (np.isfinite(aligned.real) & np.isfinite(aligned.imag) &
                  np.isfinite(satellite.real) & np.isfinite(satellite.imag) &
                  (np.abs(satellite) > 1e-12) &
                  (np.abs(aligned) > 1e-12))
    valid_frame = valid_tone.all(axis=1)
    if not np.any(train_mask & valid_frame):
        raise ValueError("independent reference has no supported training frames")
    # ref/injection is the independently observed instrument + static response.
    denominator = aligned / injection_phasor[None, :]
    corrected_tones = np.full_like(satellite, np.nan + 1j*np.nan)
    np.divide(satellite, denominator, out=corrected_tones, where=valid_tone)
    corrected = np.angle(np.nansum(np.where(valid_tone, corrected_tones, 0), axis=1))
    corrected[~valid_frame] = np.nan
    uncalibrated = np.angle(np.sum(satellite, axis=1))
    return {"phase_rad": corrected, "uncalibrated_rad": uncalibrated,
            "valid": valid_frame, "train": train_mask}


def unsafe_same_satellite_subtraction(phase, degree=3):
    """Deliberately unsafe comparator: fit and remove the measured satellite."""
    phase = np.asarray(phase, float)
    valid = np.isfinite(phase)
    x = np.linspace(-1, 1, len(phase))
    out = np.full_like(phase, np.nan)
    out[valid] = np.unwrap(phase[valid]) - np.polyval(
        np.polyfit(x[valid], np.unwrap(phase[valid]), degree), x[valid])
    return wrap(out)


def experiment(seed=32, missing_fraction=.0, injection_override=None):
    d = simulate(seed=seed, missing_fraction=missing_fraction)
    split = int(.4 * len(d["t"]))
    train = np.arange(len(d["t"])) < split
    injection = d["injection"] if injection_override is None else injection_override
    result = recover(d["satellite"], d["reference"], injection,
                     d["delay_samples"], train)
    unsafe = unsafe_same_satellite_subtraction(result["phase_rad"])
    held = (~train) & result["valid"]
    truth = d["geometry"]
    def absolute_rmse(x):
        return np.degrees(circular_rmse(x[held], truth[held])) if held.any() else float("nan")
    metrics = {
        "held_frames": int(held.sum()),
        "metric_gauge": "absolute wrapped phase using known synthetic injection calibration; no truth alignment",
        "uncalibrated_rmse_deg": absolute_rmse(result["uncalibrated_rad"]),
        "independent_reference_rmse_deg": absolute_rmse(result["phase_rad"]),
        "unsafe_same_satellite_rmse_deg": absolute_rmse(unsafe),
        "true_held_excursion_deg": float(np.degrees(np.ptp(np.unwrap(truth[held])))),
        "unsafe_held_excursion_deg": float(np.degrees(np.ptp(np.unwrap(unsafe[held])))),
    }
    return d, result, unsafe, held, metrics


def main():
    out = Path(__file__).resolve().parent
    d, result, unsafe, held, metrics = experiment()
    extra = .3*d["t"]**2
    noncommon = recover(d["satellite"]*np.exp(1j*extra[:, None]),
                        d["reference"], d["injection"], d["delay_samples"],
                        result["train"])
    metrics["noncommon_drift_rmse_deg"] = float(np.degrees(circular_rmse(
        noncommon["phase_rad"][held], d["geometry"][held])))
    (out / "summary.json").write_text(json.dumps({
        "status": "synthetic_only_no_reference_asserted_for_recording",
        "split": "first 40% train, final 60% held",
        "estimator_truth_inputs": [], "simulation": d["config"], "metrics": metrics,
    }, indent=2) + "\n")
    with (out / "held.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["time_s", "truth_deg", "uncalibrated_deg", "independent_deg", "unsafe_deg"])
        for i in np.flatnonzero(held):
            w.writerow([d["t"][i], *np.degrees([d["geometry"][i], result["uncalibrated_rad"][i], result["phase_rad"][i], unsafe[i]])])
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(d["t"][held], np.degrees(np.unwrap(d["geometry"][held])), label="known geometry", lw=2)
    for values, label in [(result["phase_rad"], "independent reference"), (unsafe, "unsafe satellite subtraction")]:
        y = np.unwrap(values[held])
        ax.plot(d["t"][held], np.degrees(y), label=label, alpha=.85)
    ax.set(xlabel="time (s), held partition", ylabel="phase (degrees)", title="Synthetic independent-reference recovery")
    ax.legend(); fig.tight_layout(); fig.savefig(out / "recovery.png", dpi=150); fig.savefig(out / "recovery.svg")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
