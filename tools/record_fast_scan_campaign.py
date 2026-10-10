"""Bounded, explicitly authorized lower/upper/lower campaign; analysis is independent."""
import dataclasses
import json
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource
from leo.contracts.continuous_window import ContinuousRunCheckpointV1
from leo.contracts.digests import canonical_digest
from leo.scanner.continuous_recording import run_continuous_recording
from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import ContinuousWindowWriter, write_checkpoint


def required_reserve(seconds, edges):
    if not edges or not 0 < seconds * len(edges) <= 1800:
        raise ValueError("a capture campaign must be positive and at most 30 minutes")
    return 2_000_000_000 + 14_000_000 * seconds * len(edges)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--qualified-runner", type=Path, required=True)
    parser.add_argument("--edges", nargs="+", choices=("lower", "upper"),
                        default=["lower", "upper", "lower"])
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--bulk-root", type=Path)
    args = parser.parse_args()
    try:
        reserve = required_reserve(args.seconds, args.edges)
    except ValueError as error:
        parser.error(str(error))
    # Reuse the previously qualified exact readback radio factory and target preparation.
    sys.path.insert(0, str(args.qualified_runner))
    import record_dual_reference as qualified
    from pluto_plus.radio_lock import acquire_radio_lock

    args.root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.root).free < reserve:
        raise RuntimeError("insufficient reserve for bounded recordings")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    with acquire_radio_lock(qualified.SERIAL):
        for index, edge in enumerate(args.edges, start=1):
            if stop.is_set():
                break
            identifier = f"{args.campaign}-{index}-{edge}"
            folder = args.root / identifier
            folder.mkdir()
            qualified.ROOT = folder
            configuration = ContinuousWindowConfiguration(
                targets=qualified.measured_targets(edge), gain_db=40, transition_budget_ms=20)
            config = json_metadata(dataclasses.asdict(configuration))
            cp = ContinuousRunCheckpointV1(run_id=identifier, configuration=config,
                configuration_sha256=canonical_digest(config), host="192.168.1.20",
                serial=qualified.SERIAL, state="starting", updated_utc_ns=time.time_ns())
            write_checkpoint(folder, cp)
            if args.bulk_root:
                from leo.storage.fast_scan import FastScanStore
                FastScanStore(args.bulk_root).update_automatic(identifier, state="recording",
                    edge=edge, captured_windows=0, started_utc_ns=time.time_ns())
            source = PpuContinuousWindowSource("192.168.1.20", expected_serial=qualified.SERIAL,
                                               radio_factory=qualified.exact_radio_factory)
            sink = ContinuousWindowWriter(folder, identifier, configuration,
                radio={"host": "192.168.1.20", "serial": qualified.SERIAL,
                       "provider": "ppu-continuous-v5", "physical_lnb_control_changed": False})
            last = [0.0]

            def progress(event, last=last, sink=sink, folder=folder, identifier=identifier):
                nonlocal cp
                if time.monotonic() - last[0] < 10:
                    return
                last[0] = time.monotonic()
                durable = sink.durable_windows
                cp = cp.model_copy(update={"state": "running",
                    "captured_windows": max(durable, sink.accepted_windows, cp.captured_windows,
                                             event.get("captured_windows", 0)),
                    "durable_windows": durable, "sealed_segments": sink.segment_index,
                    "updated_utc_ns": time.time_ns()})
                write_checkpoint(folder, cp)
                print(json.dumps({"recording": identifier, "state": cp.state,
                                  "captured_windows": cp.captured_windows}), flush=True)

            try:
                result = run_continuous_recording(source, configuration, sink,
                    stop=stop, stop_after_seconds=args.seconds, on_progress=progress,
                    queue_windows=1024,
                    queue_bytes=409600000, shutdown_timeout_seconds=60)
                cp = cp.model_copy(update={"state": "failed" if result.fault else "stopped",
                    "fault": result.fault, "captured_windows": result.captured_windows,
                    "durable_windows": sink.durable_windows, "sealed_segments": sink.segment_index,
                    "device_terminal": json_metadata(dataclasses.asdict(result.terminal))
                        if result.terminal else None,
                    "host_restoration": json_metadata(dataclasses.asdict(result.restoration))
                        if result.restoration else None,
                    "updated_utc_ns": time.time_ns()})
                write_checkpoint(folder, cp)
                print(cp.model_dump_json(), flush=True)
                if result.fault or not result.terminal or result.terminal.error:
                    raise RuntimeError(f"capture failed: {result.fault}")
            except BaseException as error:
                write_checkpoint(folder, cp.model_copy(update={"state": "failed",
                    "fault": f"{type(error).__name__}: {error}", "updated_utc_ns": time.time_ns()}))
                raise


if __name__ == "__main__":
    main()
