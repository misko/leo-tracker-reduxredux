#!/usr/bin/env python3
"""Bounded RX-only v5 qualification; never enables TX or repeats a campaign."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from threading import Timer

from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource
from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window import ShortWindowTarget, classify_window
from leo.scanner.short_window_recording import acquisition_metadata, json_metadata
from leo.storage.continuous_window import ContinuousWindowWriter, run_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--if-hz", type=int, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-limit", type=int, default=100)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--gain-db", type=float, default=40)
    parser.add_argument("--transition-budget-ms", type=int, default=20)
    args = parser.parse_args()
    if not 0 < args.seconds <= 1800 or not 1 <= args.window_limit <= 100_000:
        raise ValueError("qualification needs explicit bounded time and visit limits")
    configuration = ContinuousWindowConfiguration(
        targets=tuple(ShortWindowTarget(f"if-{frequency}", frequency) for frequency in args.if_hz),
        gain_db=args.gain_db, transition_budget_ms=args.transition_budget_ms)
    path = run_path(args.output_root, args.run_id)
    path.mkdir(parents=True, exist_ok=False)
    writer = ContinuousWindowWriter(path, args.run_id, configuration,
        radio={"provider": "ppu-continuous-v5", "serial": args.serial, "host": args.host})
    source = PpuContinuousWindowSource(args.host, expected_serial=args.serial)
    fault = None
    receipt = None
    ack = None
    deadline = None
    count = quiet = 0
    first_start = eighth_end = previous_start = None
    maximum_spacing = 0
    started = time.monotonic()
    try:
        source.configure_once(configuration)
        print(json.dumps({"kind": "activated", "session": source.identity[0],
                          "generation": source.identity[1]}), flush=True)
        deadline = Timer(args.seconds, source.request_stop)
        deadline.daemon = True
        deadline.start()
        while True:
            try:
                window = source.next_window()
            except StopIteration:
                break
            if window.visit != count or window.target_index != count % 8:
                raise ValueError("provider order or global sequence changed")
            acquisition = window.acquisition
            powers = tuple(json_metadata(asdict(power)) for power in
                           classify_window(acquisition, configuration.power_configuration()))
            quiet += sum(power["decision"] == "quiet" for power in powers)
            metadata = acquisition_metadata(acquisition)
            metadata.update(device_session=window.session, global_visit=window.visit,
                            sweep=window.sweep, target_index=window.target_index)
            writer.append(sequence=count, target_id=window.target.target_id,
                          samples=acquisition.samples, acquisition=metadata, powers=powers)
            count += 1
            if not acquisition.complete or acquisition.quality_flags:
                raise ValueError(f"invalid support at visit {window.visit}")
            if first_start is None:
                first_start = acquisition.sample_start
            if count == 8:
                eighth_end = acquisition.sample_end
            if previous_start is not None:
                maximum_spacing = max(maximum_spacing, acquisition.sample_start-previous_start)
            previous_start = acquisition.sample_start
            if count == args.window_limit:
                ack = source.request_stop()
                print(json.dumps({"kind": "stop_ack", "status": json_metadata(asdict(ack))}), flush=True)
    except BaseException as error:
        fault = f"{type(error).__name__}: {error}"
        try:
            source.request_stop(forced=True)
        except Exception as stop_error:
            fault += f"; forced STOP: {stop_error}"
    finally:
        if deadline is not None:
            deadline.cancel()
        try:
            receipt = source.close()
            if receipt is None or receipt.terminal is None:
                fault = f"{fault or ''}; missing device terminal/restoration receipt"
            elif receipt.terminal.state.name != "COMPLETED" or receipt.terminal.error:
                fault = f"{fault or ''}; device terminal {receipt.terminal.state.name}/{receipt.terminal.error}"
        except Exception as close_error:
            fault = f"{fault or ''}; close/restoration: {close_error}"
        publication = writer.finish(stop_reason="fault" if fault else "explicit_stop", failure=fault)
    result = {"kind": "continuous_protocol_qualification", "fault": fault,
              "windows": count, "quiet_receiver_decisions": quiet,
              "wall_seconds": time.monotonic()-started, "publication": publication,
              "terminal": json_metadata(asdict(receipt.terminal)) if receipt and receipt.terminal else None,
              "host_restoration": json_metadata(asdict(receipt.restoration)) if receipt else None,
              "first_eight_complete_coverage_ms": (eighth_end-first_start)/2500
                  if eighth_end is not None and first_start is not None else None,
              "maximum_valid_start_spacing_ms": maximum_spacing/2500,
              "qualified_tracking": False}
    (path / "qualification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)
    if fault or receipt is None or receipt.terminal is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
