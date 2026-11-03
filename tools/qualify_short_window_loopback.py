"""Bounded PPU short-window cable-loopback receipt and raw-IQ qualification.

Default invocation is radio-free. --execute is an RF collection and must be
covered by explicit authorization. This script neither flashes nor deploys.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import signal
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from leo.acquisition.short_window_iio import Tx2ToneOwner
from leo.scanner.short_window import (
    ShortWindowConfiguration,
    ShortWindowTarget,
    classify_window,
)
from leo.storage.short_window import ShortWindowWriter


def plan(arguments: argparse.Namespace) -> ShortWindowConfiguration:
    if not 0 < arguments.duration_seconds <= 120:
        raise ValueError("loopback duration must be positive and at most 120 seconds")
    if not 1 <= arguments.max_visits <= 512:
        raise ValueError("loopback visit limit must be in [1, 512]")
    if not -80 <= arguments.tx_gain_db <= -30:
        raise ValueError("loopback TX2 gain must be in [-80, -30] dB")
    if not 0 < arguments.tone_hz < 1_250_000:
        raise ValueError("nonzero tone must be inside the captured Nyquist bandwidth")
    frequencies = tuple(arguments.if_hz)
    if len(set(frequencies)) != len(frequencies):
        raise ValueError("loopback profiles require distinct requested IF frequencies")
    if arguments.tx_if_hz not in frequencies:
        raise ValueError("fixed TX LO must be one of the destination RX profiles")
    return ShortWindowConfiguration(
        targets=tuple(
            ShortWindowTarget(f"if-{frequency}", frequency, profile_id=str(index))
            for index, frequency in enumerate(frequencies)
        ),
        gain_db=arguments.rx_gain_db,
        duration_seconds=arguments.duration_seconds,
        max_visits=arguments.max_visits,
        policy_id="firmware-weighted-20ms-v1",
        transition_budget_ms=arguments.transition_budget_ms,
        threshold_dbfs=arguments.threshold_dbfs,
        threshold_policy_id=(
            "mean-component-ci16-minus38-comparison-v1"
            if arguments.threshold_dbfs == -38
            else "fixed-gain-cabled-test-threshold-v1"
        ),
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--host", required=True)
    result.add_argument("--serial", required=True)
    result.add_argument("--output-root", type=Path, required=True)
    result.add_argument("--session-id", default=f"loopback-{time.time_ns()}")
    result.add_argument("--if-hz", type=int, action="append", required=True)
    result.add_argument("--tx-if-hz", type=int, required=True)
    result.add_argument("--tone-hz", type=int, default=100_000)
    result.add_argument("--tx-gain-db", type=float, default=-80)
    result.add_argument("--rx-gain-db", type=float, default=40)
    result.add_argument("--duration-seconds", type=float, default=10)
    result.add_argument("--max-visits", type=int, default=64)
    result.add_argument("--transition-budget-ms", type=int, default=100)
    result.add_argument("--threshold-dbfs", type=float, default=-38)
    result.add_argument("--fixture-attenuation-db", type=float)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--receive-only", action="store_true")
    return result


def _tone_evidence(samples: np.ndarray, expected_hz: int) -> list[dict[str, Any]]:
    """Observed whole-window tone/power metrics; no frozen acceptance tolerance."""
    if not len(samples):
        return [
            {"receiver_id": receiver, "sample_count": 0, "quality": "empty_visit"}
            for receiver in range(samples.shape[1])
        ]
    complex_values = samples[..., 0].astype(np.float64) + 1j * samples[..., 1]
    frequencies = np.fft.fftfreq(len(samples), 1 / 2_500_000)
    result = []
    for receiver in range(samples.shape[1]):
        signal_values = complex_values[:, receiver]
        spectrum = np.abs(np.fft.fft(signal_values * np.hanning(len(samples)))) ** 2
        peak = int(np.argmax(spectrum))
        result.append(
            {
                "receiver_id": receiver,
                "expected_tone_hz": expected_hz,
                "observed_peak_hz": float(frequencies[peak]),
                "clipped_adc12_components": int(
                    np.count_nonzero(
                        (samples[:, receiver, :] <= -2048) | (samples[:, receiver, :] >= 2047)
                    )
                ),
                "mean_component_power_ci16": float(
                    np.mean(samples[:, receiver, :].astype(np.float64) ** 2)
                ),
            }
        )
    return result


def execute(arguments: argparse.Namespace, configuration: ShortWindowConfiguration) -> Path:
    # Verify the selected release's ABI BEFORE importing pyadi/native libiio.
    from pluto_plus.hardware.preflight import verify_metadata_runtime

    from leo.acquisition.short_window_ppu import PpuShortWindowSource

    verify_metadata_runtime(3)
    cancelled = threading.Event()
    old_handlers = {
        number: signal.signal(number, lambda signum, frame: cancelled.set())
        for number in (signal.SIGINT, signal.SIGTERM)
    }
    tone = Tx2ToneOwner(
        f"ip:{arguments.host}",
        arguments.serial,
        maximum_seconds=min(120, arguments.duration_seconds + 15),
    )

    def enable_tone() -> None:
        tone.start(arguments.tx_if_hz, tone_hz=arguments.tone_hz, gain_db=arguments.tx_gain_db)

    source = PpuShortWindowSource(
        arguments.host,
        expected_serial=arguments.serial,
        before_start_hook=None if arguments.receive_only else enable_tone,
    )
    writer = ShortWindowWriter(
        arguments.output_root,
        arguments.session_id,
        configuration=json.loads(json.dumps(dataclasses.asdict(configuration))),
        radio={"uri": f"ip:{arguments.host}", "serial": arguments.serial},
        receiver_ids=configuration.receiver_ids,
    )
    evidence: list[dict[str, Any]] = []
    errors: list[str] = []
    reason = "duration_or_visit_limit"
    manifest: Path | None = None
    try:
        if not arguments.receive_only:
            tone.open()
        source.configure_once(configuration)
        for sequence in range(configuration.max_visits):
            if cancelled.is_set():
                reason = "cancelled"
                break
            try:
                target, acquisition = source.next_capture()
            except StopIteration:
                break
            expected = arguments.tx_if_hz + arguments.tone_hz - target.if_center_hz
            tone_metrics = _tone_evidence(acquisition.samples, expected)
            if any(metric.get("clipped_adc12_components", 0) for metric in tone_metrics):
                acquisition = dataclasses.replace(
                    acquisition,
                    quality_flags=(*acquisition.quality_flags, "adc12_clipping"),
                )
            powers = classify_window(acquisition, configuration)
            metadata = {
                field.name: getattr(acquisition, field.name)
                for field in dataclasses.fields(acquisition)
                if field.name != "samples"
            }
            writer.append(
                sequence=sequence,
                target_id=target.target_id,
                samples=acquisition.samples,
                acquisition=json.loads(json.dumps(metadata)),
                powers=tuple(json.loads(json.dumps(dataclasses.asdict(power))) for power in powers),
            )
            evidence.append(
                {
                    "sequence": sequence,
                    "target_id": target.target_id,
                    "sample_count": acquisition.sample_count,
                    "tone": tone_metrics,
                }
            )
    except BaseException as error:
        reason = "failure"
        errors.append("".join(traceback.format_exception(error)))
    finally:
        # SCAN locks TX attributes as well as RX. Release the finite PPU owner
        # first; its RX-only restoration mutes TX before our TX snapshot restore.
        for owner in (source, tone):
            try:
                owner.close()
            except BaseException as error:
                errors.append(f"cleanup {type(error).__name__}: {error}")
        if tone.watchdog_error:
            errors.append(tone.watchdog_error)
        manifest = writer.finish(stop_reason=reason, failure="; ".join(errors) or None)
        receipt = {
            "kind": "short-window-cabled-tx2-loopback-v1",
            "manifest": str(manifest),
            "tx_if_hz": arguments.tx_if_hz,
            "tone_hz": arguments.tone_hz,
            "tx_gain_db": arguments.tx_gain_db,
            "fixture_attenuation_db_user_attested": arguments.fixture_attenuation_db,
            "tx_restoration": tone.restoration_receipt,
            "context_facts": tone.context_facts,
            "source_receipt": dataclasses.asdict(source.receipt) if source.receipt else None,
            "receive_only": arguments.receive_only,
            "evidence": evidence,
            "errors": errors,
            "limitations": [
                "one fixed destination tone does not qualify all directed profile pairs",
                "DDS tone cannot detect repeated buffers; coded-waveform follow-up required",
                "no held-out amplitude/frequency/settling tolerance is frozen by this smoke",
            ],
        }
        (manifest.parent / f"{arguments.session_id}.receipt.json").write_text(
            json.dumps(receipt, indent=2, default=str) + "\n"
        )
        for number, handler in old_handlers.items():
            signal.signal(number, handler)
    if errors:
        raise RuntimeError("; ".join(errors))
    return manifest


def main() -> int:
    arguments = parser().parse_args()
    configuration = plan(arguments)
    if not arguments.execute:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "configuration": dataclasses.asdict(configuration),
                    "tx_if_hz": arguments.tx_if_hz,
                    "tone_hz": arguments.tone_hz,
                    "tx_gain_db": arguments.tx_gain_db,
                    "payload_limit_bytes": configuration.window_bytes * configuration.max_visits,
                },
                indent=2,
            )
        )
        return 0
    print(execute(arguments, configuration))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
