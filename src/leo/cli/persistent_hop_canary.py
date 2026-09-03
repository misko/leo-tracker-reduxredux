"""Run one exact 300-second persistent-hop capture into the durable scanner store."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any, Literal

from leo.radio.pluto_persistent_hop import PlutoPersistentHopRadio
from leo.scanner.persistent_hop import (
    PERSISTENT_HOP_HIGH_DUTY_ACCEPTANCE_PPM,
    PersistentHopPlanV1,
    compile_persistent_hop_plan_v1,
)
from leo.storage.errors import BundleNotFoundError
from leo.storage.persistent_hop import PersistentHopIqStore, PublishedPersistentHopIqSession
from leo.storage.persistent_hop_capture import capture_persistent_hop_to_store

_DEFAULT_SAFETY_RESERVE_BYTES = 1024**3


@dataclass(frozen=True, slots=True)
class PersistentHopCanarySettings:
    """Explicit inputs for a destructive-to-disk but non-deploying hardware canary."""

    host: str
    expected_serial: str
    radio_id: str
    bulk_root: Path
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    session_id: str
    iiod_port: int | None = None
    transition_guard_us: int = 1_000
    samples_per_block: int = 131_072
    kernel_buffers: int = 8
    gain_db: float = 40.0
    read_ahead_visits: int = 8
    queue_capacity_visits: int = 64
    safety_reserve_bytes: int = _DEFAULT_SAFETY_RESERVE_BYTES


def run_persistent_hop_canary(
    settings: PersistentHopCanarySettings,
    *,
    cancel: Event | None = None,
    radio_factory: Callable[..., Any] = PlutoPersistentHopRadio,
    store_factory: Callable[[Path], Any] = PersistentHopIqStore,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    capture: Callable[..., PublishedPersistentHopIqSession] = capture_persistent_hop_to_store,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Capture, publish, and fully re-read one canary using production ports."""

    if settings.queue_capacity_visits <= 0:
        raise ValueError("persistent-hop canary queue capacity must be positive")
    if not 1 <= settings.read_ahead_visits <= 64:
        raise ValueError("persistent-hop canary read-ahead visits must be within 1..64")
    if settings.safety_reserve_bytes < 0:
        raise ValueError("persistent-hop canary safety reserve cannot be negative")
    plan = compile_persistent_hop_plan_v1(
        sample_rate_hz=settings.sample_rate_hz,
        transition_guard_us=settings.transition_guard_us,
        samples_per_block=settings.samples_per_block,
        kernel_buffers=settings.kernel_buffers,
        gain_db=settings.gain_db,
    )
    store = store_factory(settings.bulk_root)
    _require_storage_write_access(store)
    try:
        store.inspect(settings.session_id)
    except BundleNotFoundError:
        pass
    else:
        raise ValueError(f"persistent-hop canary session already exists: {settings.session_id}")

    required_free_bytes = _required_free_bytes(plan, settings.safety_reserve_bytes)
    available_free_bytes = max(0, int(disk_usage(store.root).free))
    if available_free_bytes < required_free_bytes:
        raise RuntimeError(
            "persistent-hop canary storage admission rejected: "
            f"need {required_free_bytes} free bytes, have {available_free_bytes}"
        )

    radio = radio_factory(
        settings.host,
        expected_serial=settings.expected_serial,
        radio_id=settings.radio_id,
        iiod_port=settings.iiod_port,
        read_ahead_visits=settings.read_ahead_visits,
    )
    started = monotonic()
    published = capture(
        radio,
        plan,
        session_id=settings.session_id,
        store=store,
        cancel=cancel or Event(),
        queue_capacity_visits=settings.queue_capacity_visits,
    )
    captured = monotonic()
    verified = store.verify(published)
    verified_at = monotonic()
    return _summary(
        verified,
        available_free_bytes=available_free_bytes,
        required_free_bytes=required_free_bytes,
        capture_elapsed_seconds=captured - started,
        verification_elapsed_seconds=verified_at - captured,
        read_ahead_visits=settings.read_ahead_visits,
    )


def _require_storage_write_access(store: Any) -> None:
    """Reject an unwritable transaction or publication root before RF starts."""

    for label, path in (
        ("spool", Path(store.spool_root)),
        ("scanner-hop-recordings", Path(store.bundles_root)),
    ):
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise PermissionError(f"persistent-hop canary {label} root is not writable: {path}")


def _required_free_bytes(plan: PersistentHopPlanV1, safety_reserve_bytes: int) -> int:
    raw_iq_bytes = plan.nominal_device_sample_count * len(plan.receiver_ids) * 4
    return raw_iq_bytes + safety_reserve_bytes


def _summary(
    published: PublishedPersistentHopIqSession,
    *,
    available_free_bytes: int,
    required_free_bytes: int,
    capture_elapsed_seconds: float,
    verification_elapsed_seconds: float,
    read_ahead_visits: int,
) -> dict[str, Any]:
    manifest = published.manifest
    receipt = manifest.receipt
    queue = manifest.queue_telemetry
    high_duty_target_met = receipt.valid_duty_ppm >= PERSISTENT_HOP_HIGH_DUTY_ACCEPTANCE_PPM
    return {
        "schema": "org.leo.persistent-hop-durable-canary/v1",
        "passed": receipt.qualified and high_duty_target_met,
        "session_id": published.session_id,
        "sample_rate_hz": manifest.plan.sample_rate_hz,
        "rf_bandwidth_hz": manifest.plan.bandwidth_hz,
        "samples_per_block": manifest.plan.samples_per_block,
        "kernel_buffers": manifest.plan.kernel_buffers,
        "read_ahead_visits": read_ahead_visits,
        "radio_id": receipt.radio_id,
        "radio_serial": receipt.radio_serial,
        "radio_uri": receipt.radio_uri,
        "capture_outcome": receipt.capture_outcome,
        "visit_count": len(receipt.visits),
        "target_visits": {
            f"CH{item.target.channel}{item.target.edge.value[0].upper()}": item.visit_count
            for item in receipt.target_coverage
        },
        "valid_sample_count": receipt.valid_sample_count,
        "transition_invalid_sample_count": receipt.transition_invalid_sample_count,
        "duty_denominator_sample_count": receipt.duty_denominator_sample_count,
        "valid_duty_ppm": receipt.valid_duty_ppm,
        "valid_duty_percent": receipt.valid_duty_percent,
        "duty_target_met": receipt.duty_target_met,
        "high_duty_acceptance_ppm": PERSISTENT_HOP_HIGH_DUTY_ACCEPTANCE_PPM,
        "high_duty_target_met": high_duty_target_met,
        "continuity_attested": receipt.continuity_attested,
        "missing_sample_count": receipt.missing_sample_count,
        "overflow_count": receipt.overflow_count,
        "hop_event_sequence_gap_count": receipt.hop_event_sequence_gap_count,
        "restoration_status": receipt.restoration.status,
        "capture_elapsed_seconds": capture_elapsed_seconds,
        "verification_elapsed_seconds": verification_elapsed_seconds,
        "storage": {
            "path": str(published.path),
            "uri": published.uri,
            "manifest_sha256": published.manifest_sha256,
            "chunk_count": len(manifest.chunks),
            "uncompressed_bytes": manifest.uncompressed_bytes,
            "compressed_bytes": manifest.compressed_bytes,
            "uncompressed_sha256": manifest.uncompressed_sha256,
            "required_free_bytes_before_capture": required_free_bytes,
            "available_free_bytes_before_capture": available_free_bytes,
            "full_chunk_verification_passed": True,
            "scanner_history_eligible": True,
        },
        "queue_telemetry": None if queue is None else queue.model_dump(mode="json"),
    }


def _default_session_id(sample_rate_hz: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rate = "2p5m" if sample_rate_hz == 2_500_000 else "5m"
    return f"canary-hop-{stamp}-{rate}"


def _positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return number


def _port(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 65_535:
        raise argparse.ArgumentTypeError("iiOD port must be within 1..65535")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="literal 192.168.1.x radio address")
    parser.add_argument("--serial", required=True, help="exact expected radio serial")
    parser.add_argument("--radio-id", required=True, help="scanner-visible radio identity")
    parser.add_argument("--bulk-root", required=True, type=Path, help="existing local bulk root")
    parser.add_argument(
        "--sample-rate",
        required=True,
        type=int,
        choices=(2_500_000, 5_000_000),
        help="sample rate; RF bandwidth is always set to the same value",
    )
    parser.add_argument(
        "--iiod-port",
        type=_port,
        help="opt-in alternate iiOD port; omission preserves the production endpoint",
    )
    parser.add_argument("--session-id", help="unique durable session ID")
    parser.add_argument("--transition-guard-us", type=_positive_integer, default=1_000)
    parser.add_argument("--samples-per-block", type=_positive_integer, default=131_072)
    parser.add_argument("--kernel-buffers", type=_positive_integer, default=8)
    parser.add_argument("--gain-db", type=float, default=40.0)
    parser.add_argument("--read-ahead-visits", type=_positive_integer, default=8)
    parser.add_argument("--queue-capacity-visits", type=_positive_integer, default=64)
    parser.add_argument(
        "--safety-reserve-bytes",
        type=_nonnegative_integer,
        default=_DEFAULT_SAFETY_RESERVE_BYTES,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    session_id = args.session_id or _default_session_id(args.sample_rate)
    settings = PersistentHopCanarySettings(
        host=args.host,
        expected_serial=args.serial,
        radio_id=args.radio_id,
        bulk_root=args.bulk_root,
        sample_rate_hz=args.sample_rate,
        session_id=session_id,
        iiod_port=args.iiod_port,
        transition_guard_us=args.transition_guard_us,
        samples_per_block=args.samples_per_block,
        kernel_buffers=args.kernel_buffers,
        gain_db=args.gain_db,
        read_ahead_visits=args.read_ahead_visits,
        queue_capacity_visits=args.queue_capacity_visits,
        safety_reserve_bytes=args.safety_reserve_bytes,
    )
    cancel = Event()

    def request_cancel(_signum: int, _frame: Any) -> None:
        cancel.set()

    previous = {
        selected: signal.signal(selected, request_cancel)
        for selected in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        summary = run_persistent_hop_canary(settings, cancel=cancel)
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": "org.leo.persistent-hop-durable-canary/v1",
                    "passed": False,
                    "session_id": session_id,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        for selected, handler in previous.items():
            signal.signal(selected, handler)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
