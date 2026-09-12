"""Bounded RX-only Ethernet experiment using PPU public capture APIs.

Separate diagnostic schema; existing ladder contracts are unchanged. IQ is
consumed and discarded. Every delivered block's source counters are retained.
"""

import argparse
import dataclasses
import json
import math
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from pluto_plus.hardware.base import restore_settings_exact
from pluto_plus.hardware.iio import IioRadioDevice
from pluto_plus.hardware.preflight import verify_metadata_runtime
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.rf_profile import RxLayoutExpectation
from pluto_plus.tandem import TandemMode, TandemSessionRequestV1

SERIAL = "104000bac4950008230026001b440a003a"
URI = "ip:192.168.1.17"
FRAME = 1_000_000


def summarize(frames, rate):
    """Coverage excludes unobserved edges; run lengths never bridge a gap."""
    if not frames:
        raise ValueError("no delivered frames")
    runs = []
    start = previous = None
    samples = internal_missing = 0
    for frame in frames:
        first, end = frame["first"], frame["end"]
        if end <= first:
            raise ValueError("nonpositive block")
        if previous is not None:
            gap = first - previous
            if gap < 0 or gap != frame["missing_before"]:
                raise ValueError("source counters do not close")
            internal_missing += gap
            if gap:
                runs.append({"first": start, "end": previous, "samples": previous - start})
                start = first
        else:
            start = first
        samples += end - first
        previous = end
    runs.append({"first": start, "end": previous, "samples": previous - start})
    span = frames[-1]["end"] - frames[0]["first"]
    if samples + internal_missing != span:
        raise ValueError("sample coverage does not close")
    return {
        "received_samples": samples,
        "internal_missing_samples": internal_missing,
        "prefix_missing_samples": frames[0]["missing_before"],
        "source_span_seconds": span / rate,
        "source_coverage_fraction": samples / span,
        "gap_count": len(runs) - 1,
        "overflow_frames": sum(bool(f["overflow"]) for f in frames),
        "longest_contiguous_samples": max(r["samples"] for r in runs),
        "longest_contiguous_seconds": max(r["samples"] for r in runs) / rate,
        "initial_contiguous_seconds": runs[0]["samples"] / rate,
        "runs": runs,
    }


def cell(radio, rate, duration, ram_slots, deadline):
    target = math.ceil(duration * rate / FRAME)
    if not 1 <= target <= 4096:
        raise ValueError("unbounded frame target")
    frames = []
    result = {
        "rate_hz": rate,
        "nominal_seconds": target * FRAME / rate,
        "requested_seconds": duration,
        "ram_slots": ram_slots,
        "frames": frames,
        "complete": False,
    }
    started = time.monotonic()
    try:
        with radio.begin_metadata_capture(
            FRAME,
            kernel_buffers=50,
            ddr_ring_bytes=ram_slots * FRAME * 4,
            ddr_ring_frames=0,
            ddr_ring_continuous=False,
            direct_async_frames=target,
            drop_backlog_on_overrun=True,
            tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
        ) as capture:
            if (
                capture.kernel_buffers != 50
                or capture.allocated_kernel_buffers != 50
                or capture.direct_async_frames != target
                or capture.direct_async_ring_extension is not bool(ram_slots)
                or capture.drop_backlog_on_overrun is not True
                or capture.ddr_ring_requested_bytes != ram_slots * FRAME * 4
                or capture.ddr_ring_admitted_bytes != ram_slots * FRAME * 4
                or capture.ddr_ring_capacity_frames != ram_slots
                or capture.ddr_ring_capture_frames
                or capture.ddr_ring_continuous
            ):
                raise RuntimeError("capture admission differs from exact requested geometry")
            result["allocated_kernel_buffers"] = capture.allocated_kernel_buffers
            reading = time.monotonic()
            for index in range(target):
                if time.monotonic() >= deadline:
                    raise TimeoutError("bounded campaign deadline reached")
                block = capture.read_block()
                if block.samples.shape != (1, FRAME):
                    raise RuntimeError("unexpected single-RX block shape")
                if block.last_sample_sequence_exclusive - block.first_sample_sequence != FRAME:
                    raise RuntimeError("block counter interval differs from IQ count")
                frames.append(
                    {
                        "index": index,
                        "read_elapsed_seconds": time.monotonic() - reading,
                        "first": block.first_sample_sequence,
                        "end": block.last_sample_sequence_exclusive,
                        "missing_before": block.missing_samples_before,
                        "overflow": bool(block.overflow_observed),
                    }
                )
            result["read_seconds"] = time.monotonic() - reading
            if ram_slots:
                status = capture.ddr_ring_status()
                result["ring_status"] = status
                if (
                    status["state"] != "complete"
                    or status["terminal_reason"] != "target_complete"
                    or status["error_code"]
                ):
                    raise RuntimeError("RAM ring did not complete cleanly")
            result["complete"] = True
    except Exception as error:
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    result["cycle_seconds"] = time.monotonic() - started
    if frames:
        result.update(summarize(frames, rate))
        result["payload_MBps_read"] = (
            len(frames) * FRAME * 4 / frames[-1]["read_elapsed_seconds"] / 1e6
        )
        result["delivery_equivalent_duty_read"] = (
            len(frames) * FRAME / rate / frames[-1]["read_elapsed_seconds"]
        )
        result["delivery_equivalent_duty_cycle"] = (
            len(frames) * FRAME / rate / result["cycle_seconds"]
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rates", default="2.5,5,10,15,20,25,30,40,50,60")
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--ram-slots", type=int, choices=(0, 50), default=0)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    rates = [round(float(x) * 1e6) for x in args.rates.split(",")]
    if not 0 < args.seconds <= 30 or not 1 <= args.repeats <= 3:
        parser.error("each cell must be at most 30 nominal seconds, at most 3 repeats")
    if not 1 <= len(rates) <= 10 or any(not 2_500_000 <= x <= 60_000_000 for x in rates):
        parser.error("bounded 2.5–60 MS/s ladder required")
    with args.output.open("x") as output, acquire_radio_lock(SERIAL):
        runtime = verify_metadata_runtime(expected_abi=3)
        radio = IioRadioDevice(
            URI, serial=SERIAL, expected_metadata_abi=3, iq_decoder="raw-complex64"
        )
        radio.configure_rx_layout(
            RxLayoutExpectation(
                live_phy_models=("ad9361",),
                scan_channels=("voltage0", "voltage1", "voltage2", "voltage3"),
                receiver_channels=(0, 1),
            )
        )
        report = {
            "schema": "ethernet_chunk_probe_v1",
            "started_utc": datetime.now(UTC).isoformat(),
            "serial": SERIAL,
            "uri": URI,
            "wire_bytes_per_complex_sample": 4,
            "samples_per_frame": FRAME,
            "kernel_buffers": 50,
            "host_runtime": dataclasses.asdict(runtime),
            "cells": [],
            "rx_only": True,
            "iq_saved": False,
            "settings_restored": False,
            "scope": (
                "Finite direct-async sessions; gaps between sessions excluded from source coverage."
            ),
        }
        original = None
        deadline = time.monotonic() + 600

        def checkpoint():
            output.seek(0)
            json.dump(report, output, indent=2, default=str)
            output.truncate()
            output.flush()

        try:
            radio.open()
            report["identity"] = radio.identity.model_dump(mode="json")
            original = radio.read_settings()
            report["original_settings"] = original.model_dump(mode="json")
            checkpoint()
            for repeat in range(args.repeats):
                for rate in rates:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("ten-minute campaign limit")
                    bandwidth = min(rate, 56_000_000)
                    request = original.model_copy(
                        update={
                            "sample_rate_hz": rate,
                            "bandwidth_hz": bandwidth,
                            "channels": (0,),
                        }
                    )
                    try:
                        actual = radio.apply_settings(request)
                        if (
                            round(actual.sample_rate_hz) != rate
                            or round(actual.bandwidth_hz) != bandwidth
                            or actual.channels != (0,)
                        ):
                            raise RuntimeError(f"RX readback differs: {actual}")
                        result = cell(radio, rate, args.seconds, args.ram_slots, deadline)
                        result["settings"] = actual.model_dump(mode="json")
                    except Exception as error:
                        result = {"rate_hz": rate, "complete": False, "error": str(error)}
                    result["repeat"] = repeat
                    report["cells"].append(result)
                    checkpoint()
                    print(
                        json.dumps(
                            {
                                k: v
                                for k, v in result.items()
                                if k not in ("frames", "runs", "settings")
                            }
                        ),
                        flush=True,
                    )
                    if not result["complete"]:
                        # Stop on an unclosed capture instead of contaminating later cells.
                        raise RuntimeError("cell failed; inspect saved evidence before any retry")
        finally:
            try:
                if original is not None:
                    report["settings_restored"] = (
                        restore_settings_exact(radio, original).restored == original
                    )
            finally:
                radio.close()
                report["finished_utc"] = datetime.now(UTC).isoformat()
                checkpoint()


if __name__ == "__main__":
    main()
