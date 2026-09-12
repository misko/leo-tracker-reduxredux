"""RX0 throughput in AD9361/1R1T, with continuity explicitly unobservable.

The global source counter verifies running sample cadence, not per-buffer
timestamps. It cannot locate gaps or prove contiguous IQ lengths.
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

SERIAL = "104000bac4950008230026001b440a003a"


def counter_cadence(first, last, elapsed, nominal_rate):
    """A bounded global clock check, without assigning timestamps to IQ."""
    if not 0 <= first < 1 << 32 or not 0 <= last < 1 << 32:
        raise ValueError("invalid 32-bit counter")
    if elapsed <= 0 or nominal_rate <= 0 or elapsed * nominal_rate >= 1 << 32:
        raise ValueError("counter bracket cannot exclude a full wrap")
    advance = (last - first) % (1 << 32)
    return advance, advance / elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rates", default="2.5,5,10,15,20,25,30,40,50,60")
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    rates = [round(float(value) * 1e6) for value in args.rates.split(",")]
    if not 1 <= len(rates) <= 10 or any(not 2_500_000 <= value <= 60_000_000 for value in rates):
        parser.error("only a bounded 2.5–60 MS/s ladder is admitted")
    if not 0 < args.seconds <= 10 or not 1 <= args.repeats <= 3:
        parser.error("maximum ten nominal seconds per cell, three repeats")
    frame = 1_000_000
    with args.output.open("x") as output, acquire_radio_lock(SERIAL):
        runtime = verify_metadata_runtime(3)
        radio = IioRadioDevice(
            "ip:192.168.1.17", serial=SERIAL, expected_metadata_abi=3, iq_decoder="raw-complex64"
        )
        radio.configure_rx_layout(
            RxLayoutExpectation(
                live_phy_models=("ad9361",),
                scan_channels=("voltage0", "voltage1"),
                receiver_channels=(0,),
            )
        )
        report = dict(
            schema="ethernet_raw_probe_v1",
            serial=SERIAL,
            started_utc=datetime.now(UTC).isoformat(),
            cells=[],
            host_runtime=dataclasses.asdict(runtime),
            settings_restored=False,
            sample_count_per_buffer=frame,
            kernel_buffers=4,
            requested_kernel_queue_bytes=frame * 4 * 4,
            rx_only=True,
            iq_saved=False,
            continuity="unobservable; global counter snapshots are not IQ block timestamps",
        )
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
            for repeat in range(args.repeats):
                for rate in rates:
                    result = dict(
                        rate_hz=rate,
                        repeat=repeat,
                        complete=False,
                        longest_contiguous_seconds=None,
                        source_coverage_fraction=None,
                    )
                    try:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("bounded campaign deadline")
                        bandwidth = min(rate, 56_000_000)
                        actual = radio.apply_settings(
                            original.model_copy(
                                update={
                                    "sample_rate_hz": rate,
                                    "bandwidth_hz": bandwidth,
                                    "channels": (0,),
                                }
                            )
                        )
                        if (
                            round(actual.sample_rate_hz) != rate
                            or round(actual.bandwidth_hz) != bandwidth
                        ):
                            raise RuntimeError("sample rate / RF bandwidth readback differs")
                        result["settings"] = actual.model_dump(mode="json")
                        result["source_locked_rate"] = dataclasses.asdict(
                            radio.configure_source_locked_rx_rate(rate)
                        )
                        radio.configure_kernel_buffers(4)
                        result["kernel_buffer_basis"] = radio.kernel_buffer_configuration_basis
                        # Exclude two startup reads, then measure a bounded steady stream.
                        for _ in range(2):
                            block = radio.read_block(frame)
                            if block.samples.shape != (1, frame):
                                raise RuntimeError("wrong warmup IQ shape")
                        frames = math.ceil(args.seconds * rate / frame)
                        clock_start = time.monotonic()
                        counter_start = radio.read_device_sample_counter_low32()
                        started = time.monotonic()
                        latencies = []
                        for _ in range(frames):
                            if time.monotonic() >= deadline:
                                raise TimeoutError("bounded campaign deadline")
                            one = time.monotonic()
                            block = radio.read_block(frame)
                            if block.samples.shape != (1, frame):
                                raise RuntimeError("wrong IQ shape")
                            latencies.append(time.monotonic() - one)
                        elapsed = time.monotonic() - started
                        counter_end = radio.read_device_sample_counter_low32()
                        clock_elapsed = time.monotonic() - clock_start
                        advance, measured_rate = counter_cadence(
                            counter_start, counter_end, clock_elapsed, rate
                        )
                        result.update(
                            complete=True,
                            frames=frames,
                            received_samples=frames * frame,
                            read_seconds=elapsed,
                            nominal_seconds=frames * frame / rate,
                            payload_MBps=frames * frame * 4 / elapsed / 1e6,
                            delivery_equivalent_duty=frames * frame / rate / elapsed,
                            counter_start=counter_start,
                            counter_end=counter_end,
                            global_counter_advance=advance,
                            global_counter_wall_seconds=clock_elapsed,
                            measured_counter_rate_hz=measured_rate,
                            read_latencies_seconds=latencies,
                        )
                    except Exception as error:
                        result["error"] = dict(
                            type=type(error).__name__,
                            message=str(error),
                            traceback=traceback.format_exc(),
                        )
                    report["cells"].append(result)
                    checkpoint()
                    print(
                        json.dumps(
                            {
                                k: v
                                for k, v in result.items()
                                if k not in ("read_latencies_seconds", "settings")
                            }
                        ),
                        flush=True,
                    )
                    if not result["complete"]:
                        raise RuntimeError("failed cell; inspect before retry")
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
