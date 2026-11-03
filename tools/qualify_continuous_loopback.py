#!/usr/bin/env python3
"""Bounded TX2/20 dB fixture verification of the ordered continuous IQ path."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import ShortWindowTarget
from leo.scanner.short_window_recording import json_metadata


def tone_metrics(samples: np.ndarray, tone_hz: int = 100_000) -> list[dict[str, float | int]]:
    if samples.shape != (50_000, 2, 2) or samples.dtype != np.dtype("int16"):
        raise ValueError("tone qualification requires exact dual-RX CI16 windows")
    frequencies = np.fft.fftfreq(len(samples), 1 / 2_500_000)
    expected = int(np.argmin(np.abs(frequencies - tone_hz)))
    result = []
    for rx in range(2):
        values = samples[:, rx, :].astype(np.float64)
        spectrum = np.abs(np.fft.fft(values[:, 0] + 1j * values[:, 1])) ** 2
        result.append({
            "receiver": rx,
            "peak_hz": float(frequencies[int(np.argmax(spectrum))]),
            "tone_fraction": float(spectrum[expected] / spectrum.sum()) if spectrum.sum() else 0.0,
            "adc12_rail_contacts": int(np.count_nonzero((values == -2048) | (values == 2047))),
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--if-hz", type=int, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--tx-gain-db", type=float, default=-30)
    parser.add_argument("--threshold-dbfs", type=float, default=-75)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not 0 < args.seconds <= 30 or not -80 <= args.tx_gain_db <= -30:
        raise ValueError("qualification needs <=30 seconds and TX gain between -80 and -30 dB")
    configuration = ContinuousWindowConfiguration(
        targets=tuple(ShortWindowTarget(f"if-{frequency}", frequency) for frequency in args.if_hz),
        threshold_dbfs=args.threshold_dbfs, gain_db=40, transition_budget_ms=20)
    if not args.execute:
        print(json.dumps({"kind": "continuous_loopback_preview", "configuration":
            json_metadata(asdict(configuration)), "seconds": args.seconds,
            "fixture_attenuation_db": 20, "tx_gain_db": args.tx_gain_db}))
        return

    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource
    from leo.acquisition.short_window_iio import Tx2ToneOwner
    from leo.scanner.continuous_recording import run_continuous_recording
    from leo.storage.continuous_window import ContinuousWindowWriter, run_path
    from leo.storage.short_window import ShortWindowReader

    path = run_path(args.output_root, args.run_id)
    path.mkdir(parents=True, exist_ok=False)
    tone = Tx2ToneOwner(f"ip:{args.host}", args.serial, maximum_seconds=args.seconds + 20)
    source = PpuContinuousWindowSource(args.host, expected_serial=args.serial,
        before_start_hook=lambda _: tone.start(args.if_hz[0], tone_hz=100_000, gain_db=args.tx_gain_db))
    writer = ContinuousWindowWriter(path, args.run_id, configuration,
        radio={"provider": "ppu-continuous-v5", "serial": args.serial, "host": args.host})
    result = None
    try:
        tone.open()
        result = run_continuous_recording(source, configuration, writer,
                                           stop_after_seconds=args.seconds)
    finally:
        # The recording owner drains/releases RX before restoring TX attributes.
        try:
            source.close()
        finally:
            tone.close()
    diagnostics = []
    decisions = {"tone_target": {}, "other_targets": {}}
    for segment in sorted(path.glob(f"{args.run_id}-segment-*")):
        for window in ShortWindowReader(segment).windows():
            target = window.index.acquisition["target_index"]
            counts = decisions["tone_target" if target == 0 else "other_targets"]
            for power in window.index.powers:
                counts[power["decision"]] = counts.get(power["decision"], 0) + 1
            if target == 0:
                diagnostics.append({"visit": window.index.acquisition["global_visit"],
                                    "metrics": tone_metrics(window.samples)})
    receipt = {"kind": "continuous_loopback_qualification", "fixture_attenuation_db": 20,
        "tx_if_hz": args.if_hz[0], "tone_hz": 100_000, "tx_gain_db": args.tx_gain_db,
        "recording": json_metadata(asdict(result)), "tx_restoration": tone.restoration_receipt,
        "watchdog_error": tone.watchdog_error, "decisions": decisions, "tone_windows": diagnostics,
        "all_56_transitions_qualified": False, "starlink_confirmation": False}
    (path / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({**receipt, "tone_windows": len(diagnostics)}))
    if result.fault or tone.watchdog_error or not diagnostics:
        raise SystemExit(1)
    if any(metric["peak_hz"] != 100_000 or metric["adc12_rail_contacts"]
           for item in diagnostics for metric in item["metrics"]):
        raise SystemExit("unexpected tone peak or ADC12 clipping")


if __name__ == "__main__":
    main()
