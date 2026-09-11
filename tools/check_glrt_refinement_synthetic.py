#!/usr/bin/env python3
"""Known-template absolute sanity check, separate from historic translations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from evaluate_scan_glrt_rms import rms, write_json
from prototype_glrt_local_joint import PROFILES, score_profiles
from replay_historic_glrt_joint import configurations
from review_scan_sample_rates import choose, delay_signal, timing_difference

from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration, acquire_symbolwise
from leo.analysis.starlink.templates import qin_edge_pilot_frame


def run(output):
    rows = []
    rng = np.random.default_rng(20260911473)
    cases = [
        (snr, float(rng.uniform(-150000, 150000)), float(rng.uniform(100e-6, 101e-6)))
        for snr in [0, 10]
        for _ in range(6)
    ]
    for fs in [2500000, 5000000]:
        template = np.asarray(qin_edge_pilot_frame(fs, "lower"))
        for index, (snr, cfo, epoch_s) in enumerate(cases):
            signal = np.zeros(fs // 50, dtype=complex)
            anchor = int(epoch_s * fs)
            fraction = epoch_s * fs - anchor
            for frame in range(15):
                start = anchor + round(frame * fs / 750)
                count = min(len(template), len(signal) - start)
                if count > 0:
                    signal[start : start + count] += template[:count]
            signal = delay_signal(signal, fs, fraction / fs)
            signal *= np.exp(2j * np.pi * cfo * np.arange(len(signal)) / fs)
            variance = np.mean(abs(signal) ** 2) / 10 ** (snr / 10)
            noise = (rng.normal(size=len(signal)) + 1j * rng.normal(size=len(signal))) * np.sqrt(
                variance / 2
            )
            iq = signal + noise
            acquisition = acquire_symbolwise(
                iq,
                fs,
                ReceiverFrequencyCalibration("synthetic", 0, "0" * 64),
                edge="lower",
                config=configurations(fs)["fine500_conditioned100"],
            )
            for profile, scored in score_profiles(iq, fs, "lower", acquisition).items():
                target = choose(scored["candidates"], epoch_s)
                rows.append(
                    {
                        "fs": fs,
                        "case": index,
                        "snr_db": snr,
                        "truth_cfo_hz": cfo,
                        "truth_epoch_s": epoch_s,
                        "profile": profile,
                        "target": target,
                        "cfo_error_hz": target["cfo_hz"] - cfo if target else None,
                        "timing_error_ns": timing_difference(target["epoch_s"], epoch_s) * 1e9
                        if target
                        else None,
                    }
                )
        print(f"Synthetic {fs} complete", flush=True)
    summary = []
    for fs in [2500000, 5000000]:
        for snr in [0, 10]:
            common = set.intersection(
                *[
                    {
                        r["case"]
                        for r in rows
                        if r["fs"] == fs
                        and r["snr_db"] == snr
                        and r["profile"] == p
                        and r["target"]
                    }
                    for p in PROFILES
                ]
            )
            for profile in PROFILES:
                group = [
                    r for r in rows if (r["fs"], r["snr_db"], r["profile"]) == (fs, snr, profile)
                ]
                good = [r for r in group if r["case"] in common]
                summary.append(
                    {
                        "fs": fs,
                        "snr_db": snr,
                        "profile": profile,
                        "attempted": len(group),
                        "recovered": sum(r["target"] is not None for r in group),
                        "common": len(good),
                        "cfo_rms_hz": rms([r["cfo_error_hz"] for r in good]) if good else None,
                        "timing_rms_ns": rms([r["timing_error_ns"] for r in good])
                        if good
                        else None,
                    }
                )
    write_json(
        output / "synthetic.json",
        {
            "summary": summary,
            "rows": rows,
            "limits": (
                "Matched known-pilot model with AWGN and fresh acquisition. Absolute truth "
                "is known here; this is not an absolute-accuracy calibration for real "
                "transmissions. SNR is average clean 20 ms waveform power divided by "
                "complex noise power. Twelve cases per rate, six at each SNR."
            ),
        },
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args().output)
