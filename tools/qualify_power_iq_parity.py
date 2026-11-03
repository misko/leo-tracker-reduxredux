#!/usr/bin/env python3
"""Bounded one-owner native dualRX/PWR1 parity, with exact offline replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np

from leo.scanner.power_iq_parity import (
    ParityFrame,
    PowerIqCounterMappingV1,
    ci16_from_complex,
    qualify_power_iq,
)
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import run_path


def parity_preparation_frequencies(if_hz: int) -> tuple[int, ...]:
    if type(if_hz) is not int or not 70_000_000 <= if_hz <= 6_000_000_000:
        raise ValueError("parity IF is outside the radio's supported LO range")
    step = 10_000_000 if if_hz <= 5_930_000_000 else -10_000_000
    # Public preparation exits recalled Fast Lock through a distinct cached LO.
    # Only target zero is captured; the remaining slots exercise that public port.
    return tuple(if_hz + index * step for index in range(8))


def admit_mmio(response: dict[str, Any], session: int, generation: int) -> None:
    if (
        response.get("schema") != "leo.power-iq-parity-mmio.v1"
        or (response.get("session"), response.get("generation")) != (session, generation)
        or response.get("exit_status") != 0
        or response.get("error") != 0
        or response.get("cleanup_error") != 0
        or response.get("cleanup_complete") is not True
        or response.get("record_valid") is not True
        or response.get("radio_acquired") is not False
    ):
        raise ValueError("MMIO-only parity command failed or cleanup is unattested")


def collect_parity(
    capture: Any,
    helper: Callable[[], dict[str, Any]],
    *,
    mapping: PowerIqCounterMappingV1,
    session: int,
    generation: int,
    adc12_qualified: bool,
    seconds: float = 3,
) -> tuple[dict, list[ParityFrame]]:
    if not 0 < seconds <= 10:
        raise ValueError("parity capture must be explicitly bounded to at most 10 seconds")
    frames: list[ParityFrame] = []
    response: dict[str, Any] = {}
    helper_done = threading.Event()

    def execute():
        try:
            response.update(helper())
        except Exception as error:
            response.update(error=-1, transport_error=f"{type(error).__name__}: {error}")
        finally:
            helper_done.set()

    worker = threading.Thread(target=execute, name="parity-mmio", daemon=True)
    deadline = time.monotonic() + seconds
    expired = threading.Event()

    def cancel_capture():
        expired.set()
        capture.cancel()  # Public API interrupts an outstanding read_block().

    watchdog = threading.Timer(seconds, cancel_capture)
    watchdog.daemon = True
    watchdog.start()
    fault = None
    qualification = None
    try:
        while len(frames) < 100 and time.monotonic() < deadline:
            block = capture.read_block()
            if expired.is_set():
                raise TimeoutError("parity capture deadline expired")
            if not block.metadata_flags & (1 << 21):
                raise ValueError("native IQ block lacks hardware counter attestation")
            frames.append(
                ParityFrame(
                    ci16_from_complex(block.samples),
                    block.first_sample_sequence,
                    block.stream_id,
                    block.buffer_sequence,
                    block.missing_samples_before,
                    block.overflow_observed,
                )
            )
            if len(frames) == 1:
                worker.start()  # Post-OPEN snapshot only; native counter is now observable.
            if helper_done.is_set():
                admit_mmio(response, session, generation)
                words = response["words"]
                end = words[12] | words[13] << 32
                if frames[-1].fifo_start - mapping.fifo_tag_offset + len(frames[-1].samples) >= end:
                    qualification = qualify_power_iq(
                        frames,
                        words,
                        mapping=mapping,
                        session=session,
                        generation=generation,
                        adc12_qualified=adc12_qualified,
                    )
                    break
        if qualification is None:
            raise TimeoutError("exact IQ/PWR1 support was not admitted within capture bounds")
    except Exception as error:
        fault = f"{type(error).__name__}: {error}"
    finally:
        watchdog.cancel()
        if fault and not expired.is_set():
            try:
                capture.cancel()
            except Exception as error:
                fault += f"; capture cancellation failed: {str(error)[:384]}"
        if worker.ident is not None:
            # Native helper may consume its timeout plus 500 ms cleanup; SSH adds
            # one second transport grace. Keep IQ cancelled while this drains.
            worker.join(timeout=max(0, deadline + 1.5 - time.monotonic()))
            if worker.is_alive():
                fault = fault or "MMIO parity control did not finish within its bound"
    control_finished = worker.ident is None or not worker.is_alive()
    cleanup_attested = worker.ident is None or (
        control_finished
        and response.get("schema") == "leo.power-iq-parity-mmio.v1"
        and (response.get("session"), response.get("generation")) == (session, generation)
        and response.get("cleanup_complete") is True
        and response.get("cleanup_error") == 0
        and response.get("radio_acquired") is False
    )
    frozen_response = (
        dict(response)
        if control_finished
        else {
            "error": -1,
            "control_unattested": True,
            "transport_error": "MMIO control exceeded bounded cleanup grace",
        }
    )
    return {
        "kind": "bounded_power_iq_parity_qualification",
        "fault": fault,
        "frames": len(frames),
        "captured_bytes": sum(frame.samples.nbytes for frame in frames),
        "mmio": frozen_response,
        "control_finished": control_finished,
        "mmio_started": worker.ident is not None,
        "control_cleanup_attested": cleanup_attested,
        "qualification": qualification,
        "passed": bool(qualification and qualification["passed"] and not fault),
        "mapping_independently_validated": False,
        "physical_mapping_qualified": False,
        "qualified_tracking": False,
    }, frames


def replay(path: Path) -> dict:
    def bounded_read(filename: str, limit: int) -> bytes:
        with (path / filename).open("rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ValueError("parity replay input exceeds bounded retention")
        return data

    report = json.loads(bounded_read("qualification.json", 1_048_576))
    if report.get("passed") is not True or any(
        report.get(key)
        for key in ("fault", "close_fault", "radio_close_fault", "restoration_fault")
    ):
        raise ValueError("failed parity acquisition cannot become qualified on replay")
    mapping = PowerIqCounterMappingV1.model_validate(report["mapping"])
    data = bounded_read("capture.ci16", 40_000_000)
    if hashlib.sha256(data).hexdigest() != report["capture_sha256"]:
        raise ValueError("parity captured IQ checksum mismatch")
    frames = []
    offset = 0
    if len(report["frame_index"]) > 100:
        raise ValueError("parity frame index exceeds bounded retention")
    for index in report["frame_index"]:
        count = index["sample_count"]
        if type(count) is not int or not 0 < count <= 50000:
            raise ValueError("parity frame index has invalid sample count")
        samples = np.frombuffer(data[offset : offset + count * 8], dtype="<i2").reshape(count, 2, 2)
        offset += count * 8
        frames.append(
            ParityFrame(
                samples,
                index["fifo_start"],
                index["generation"],
                index["buffer_sequence"],
                index["missing_samples_before"],
                index["overflow"],
            )
        )
    if offset != len(data):
        raise ValueError("parity frame index does not exhaust actual IQ bytes")
    mmio = report["mmio"]
    admit_mmio(mmio, mmio["session"], mmio["generation"])
    return qualify_power_iq(
        frames,
        mmio["words"],
        mapping=mapping,
        session=mmio["session"],
        generation=mmio["generation"],
        adc12_qualified=report["adc12_qualified"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-bundle", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--serial")
    parser.add_argument("--if-hz", type=int)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--helper", default="/tmp/leo-power-iq-parity")
    parser.add_argument("--ssh-known-hosts", type=Path)
    parser.add_argument("--ssh-password-file", type=Path)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--future-samples", type=int, default=1_000_000)
    parser.add_argument("--gain-db", type=float, default=40)
    parser.add_argument("--adc12-qualified", action="store_true")
    args = parser.parse_args()
    if args.offline_bundle:
        print(json.dumps(replay(args.offline_bundle)))
        return
    if (
        not all((args.host, args.serial, args.if_hz, args.mapping, args.output_root, args.run_id))
        or not 0 < args.seconds <= 10
        or not 125000 <= args.future_samples <= 2500000
    ):
        raise ValueError(
            "hardware parity needs explicit identity/mapping/output and bounded timing"
        )
    from pluto_plus.adaptive_scan_radio import (
        prepare_adaptive_scan_radio,
        restore_adaptive_scan_radio,
    )
    from pluto_plus.continuous_scan import build_continuous_setup
    from pluto_plus.hardware.iio import IioRadioDevice
    from pluto_plus.setup_profiles import AD9361_2R2T_TARGET_PROFILE
    from pluto_plus.standalone_power import PowerSshCredentials

    mapping = PowerIqCounterMappingV1.model_validate_json(args.mapping.read_bytes())
    path = run_path(args.output_root, args.run_id)
    path.mkdir(parents=True, exist_ok=False)
    if args.ssh_password_file and path in args.ssh_password_file.resolve().parents:
        raise ValueError("SSH password file must remain outside the qualification archive")
    credentials = PowerSshCredentials(
        args.host.removeprefix("ip:"),
        known_hosts_file=args.ssh_known_hosts,
        password_file=args.ssh_password_file,
    )
    session, generation = secrets.randbits(32) or 1, secrets.randbits(32) or 1
    uri = args.host if args.host.startswith("ip:") else f"ip:{args.host}"
    setup = build_continuous_setup(
        session=session,
        generation=generation,
        seed=1,
        frequencies_hz=parity_preparation_frequencies(args.if_hz),
        analysis_digest=hashlib.sha256(b"exact-power-iq-parity-v1").digest(),
    )
    preparation = radio = capture = None
    frames = []
    report: dict[str, Any] = {
        "passed": False,
        "qualified_tracking": False,
        "mapping_independently_validated": False,
        "physical_mapping_qualified": False,
    }

    def helper():
        arguments = [
            args.helper,
            str(session),
            str(generation),
            str(args.future_samples),
            str(min(10000, max(200, int(args.seconds * 1000)))),
            str(int(args.adc12_qualified)),
        ]
        result = subprocess.run(
            [*credentials.argv(), shlex.join(arguments)],
            capture_output=True,
            timeout=args.seconds + 1,
            check=False,
        )
        if len(result.stdout) > 32768:
            raise ValueError("MMIO helper reply exceeded its bound")
        document = json.loads(result.stdout)
        document["exit_status"] = result.returncode
        return document

    try:
        preparation = prepare_adaptive_scan_radio(
            uri, args.serial, setup, manual_gain_db=args.gain_db
        )
        radio = IioRadioDevice(
            uri,
            serial=args.serial,
            radio_id=args.serial,
            expected_metadata_abi=3,
            require_idle_tandem_owner=True,
            iq_decoder="raw-complex64",
        )
        radio.configure_rx_layout(AD9361_2R2T_TARGET_PROFILE.rx_layout_expectation)
        radio.open()
        expected = replace(preparation.configured, center_frequency_hz=float(args.if_hz))
        if radio.read_receiver_settings_readback() != expected:
            raise ValueError("parity radio geometry changed before native capture OPEN")
        capture = radio.begin_metadata_capture(
            50000, kernel_buffers=8, counter_only=False, direct_async_frames=0
        )
        report, frames = collect_parity(
            capture,
            helper,
            mapping=mapping,
            session=session,
            generation=generation,
            adc12_qualified=args.adc12_qualified,
            seconds=args.seconds,
        )
    except Exception as error:
        report["fault"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            if capture:
                capture.close()
        except Exception as error:
            report.update(passed=False, close_fault=str(error))
        try:
            if radio:
                radio.close()
        except Exception as error:
            report.update(passed=False, radio_close_fault=str(error))
        if preparation:
            if report.get("mmio_started") and report.get("control_cleanup_attested") is not True:
                from pluto_plus.standalone_power_radio import preparation_snapshot

                report.update(
                    passed=False,
                    recovery_required=True,
                    preparation=preparation_snapshot(preparation),
                    restoration_fault="MMIO control cleanup is unattested; retained preparation",
                )
            else:
                try:
                    report["host_restoration"] = json_metadata(
                        asdict(restore_adaptive_scan_radio(preparation))
                    )
                except Exception as error:
                    report.update(passed=False, restoration_fault=str(error))
    payload = b"".join(frame.samples.tobytes() for frame in frames)
    (path / "capture.ci16").write_bytes(payload)
    report.update(
        mapping=mapping.model_dump(mode="json"),
        adc12_qualified=args.adc12_qualified,
        ssh_known_hosts_sha256=credentials.known_hosts_sha256,
        capture_sha256=hashlib.sha256(payload).hexdigest(),
        frame_index=[
            {
                "fifo_start": frame.fifo_start,
                "sample_count": len(frame.samples),
                "generation": frame.generation,
                "buffer_sequence": frame.buffer_sequence,
                "missing_samples_before": frame.missing_samples_before,
                "overflow": frame.overflow,
            }
            for frame in frames
        ],
    )
    (path / "qualification.json").write_text(json.dumps(report, sort_keys=True) + "\n")
    print(json.dumps({"path": str(path), "passed": report["passed"], "fault": report.get("fault")}))


if __name__ == "__main__":
    main()
