"""One authorized RX0-only transport measurement, bounded by FPGA source time."""
import dataclasses
import json
from pathlib import Path
import signal
import sys
import time

from leo.acquisition.authority import (
    CaptureTaskKind, LocalCaptureAuthority, RadioBusyError, RadioResource,
)
from pluto_plus.hardware.base import restore_settings_exact
from pluto_plus.hardware.iio import IioRadioDevice
from pluto_plus.hardware.preflight import verify_metadata_runtime
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.tandem import TandemMode, TandemSessionRequestV1

RATE = 10_000_000
WINDOW = 30 * RATE
SAMPLES = 131_072
SERIAL = "1040005e0b100007100010000bf33a5d4d"
URI = "ip:192.168.1.20:30431"
RADIO = "radio_pluto_5d4d"


def normalize(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def clipped_count(start, end, origin, window=WINDOW):
    return max(0, min(end, origin + window) - max(start, origin))


def timeout_handler(signum, frame):
    raise TimeoutError("90-second acquisition safety deadline exceeded")


def main():
    output = Path(sys.argv[1])
    if output.exists():
        raise FileExistsError(output)
    report = dict(
        kind="authorized_rx0_10msps_30s_transport_duty",
        sample_rate_hz=RATE, requested_source_seconds=30,
        samples_per_frame=SAMPLES, kernel_buffers=8, receiver_ids=[0],
        uri=URI, serial=SERIAL, fixed_tuning=True, iq_retained=False,
        source_window="[first returned FPGA sample, first + 300000000)",
        runtime=verify_metadata_runtime(expected_abi=3), frames=[],
        original_settings_restored=False, status="pending",
    )
    owner = LocalCaptureAuthority(
        Path("/srv/bulk/leo/control"), (RadioResource(RADIO, SERIAL, "ip:192.168.1.20"),)
    )
    report["authority_before"] = owner.snapshot()
    lease = None
    wait_start = time.monotonic()
    while lease is None:
        try:
            lease = owner.claim((RADIO,), task_id="user-rx0-10m-30s-duty", task_kind=CaptureTaskKind.QUALIFICATION)
        except RadioBusyError:
            if time.monotonic() - wait_start > 360:
                raise TimeoutError("existing scanner did not release its acquisition lease")
            print("Waiting for existing acquisition lease; no test RF started", flush=True)
            time.sleep(10)
    print("Acquired production radio lease", flush=True)
    try:
        with lease, acquire_radio_lock(SERIAL):
            radio = IioRadioDevice(
                URI, serial=SERIAL, radio_id=RADIO, expected_metadata_abi=3,
                iq_decoder="raw-complex64", require_idle_tandem_owner=True,
            )
            original = None
            opened = False
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(90)
            try:
                radio.open()
                opened = True
                report["identity"] = radio.identity
                original = radio.read_settings()
                report["original_settings"] = original
                requested = original.model_copy(update={
                    "sample_rate_hz": RATE, "bandwidth_hz": RATE, "channels": (0,),
                })
                actual = radio.apply_settings(requested)
                assert actual.sample_rate_hz == RATE and actual.bandwidth_hz == RATE
                assert tuple(actual.channels) == (0,)
                report["actual_settings"] = actual
                report["started_utc_ns"] = time.time_ns()
                started = time.perf_counter_ns()
                print("Starting fixed-tuning RX0-only 10 MS/s capture", flush=True)
                with radio.begin_metadata_capture(
                    SAMPLES, kernel_buffers=8,
                    tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
                ) as capture:
                    assert capture.kernel_buffers == 8
                    origin = previous_end = stream = None
                    received_in_window = gaps_in_window = 0
                    next_progress = 5
                    while True:
                        block = capture.read_block()
                        now = time.perf_counter_ns()
                        assert block.samples.shape == (1, SAMPLES)
                        first = block.first_sample_sequence
                        end = block.last_sample_sequence_exclusive
                        if origin is None:
                            origin, stream = first, block.stream_id
                            report["first_frame_latency_seconds"] = (now - started) / 1e9
                        assert block.stream_id == stream
                        if previous_end is not None:
                            assert first >= previous_end
                            assert first - previous_end == block.missing_samples_before
                            gaps_in_window += clipped_count(previous_end, first, origin)
                        received_in_window += clipped_count(first, end, origin)
                        report["frames"].append(dict(
                            sequence=block.buffer_sequence, first=first, end_exclusive=end,
                            missing_samples_before=block.missing_samples_before,
                            overflow_observed=block.overflow_observed,
                            host_elapsed_seconds=(now - started) / 1e9,
                        ))
                        previous_end = end
                        elapsed_source = (end - origin) / RATE
                        if elapsed_source >= next_progress:
                            print(f"Device span {elapsed_source:.3f}s; received {received_in_window / RATE:.3f}s", flush=True)
                            next_progress += 5
                        if end - origin >= WINDOW:
                            break
                    report.update(
                        source_window_observed_samples=received_in_window,
                        source_window_missing_samples=gaps_in_window,
                        source_window_duty_percent=100 * received_in_window / WINDOW,
                        source_span_seconds=(end - origin) / RATE,
                        read_elapsed_seconds=(now - started) / 1e9,
                        received_payload_bytes=len(report["frames"]) * SAMPLES * 4,
                    )
                    assert received_in_window + gaps_in_window == WINDOW
                report["capture_closed_elapsed_seconds"] = (time.perf_counter_ns() - started) / 1e9
                report["status"] = "complete"
            finally:
                signal.alarm(0)
                try:
                    if opened and original is not None:
                        restoration = restore_settings_exact(radio, original)
                        report["restoration"] = restoration
                        report["original_settings_restored"] = restoration.restored == original
                finally:
                    if opened:
                        radio.close()
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["finished_utc_ns"] = time.time_ns()
        with output.open("x") as stream:
            json.dump(report, stream, default=normalize, indent=2)
            stream.write("\n")
        print(json.dumps({k:v for k,v in report.items() if k not in (
            "frames", "restoration", "runtime", "identity", "original_settings", "actual_settings", "authority_before",
        )}, default=normalize), flush=True)


if __name__ == "__main__":
    main()
