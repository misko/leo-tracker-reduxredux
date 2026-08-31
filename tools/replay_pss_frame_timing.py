#!/usr/bin/env python3
"""Replay candidate-only, rate-generic PSS frame-timing search on recorded IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from leo.analysis.starlink import (
    PssFrameTimingResult,
    PssTimingSearchConfig,
    pss_subband_template,
    search_pss_frame_timing,
)
from leo.storage import PublishedBundle, RecordingStore

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
_QNAP_ROOT = Path("/mnt/qnap01")


@dataclass(frozen=True, slots=True)
class ReplayTarget:
    stream_id: str
    receiver_id: int


@dataclass(frozen=True, slots=True)
class ReplayBlock:
    continuity_segment_index: int
    device_sample_start: int
    sample_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_id")
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        metavar="STREAM_ID:RECEIVER_ID",
        help="recording stream and receiver; repeat to replay multiple rates",
    )
    parser.add_argument("--channel-reference-hz", type=float, required=True)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--block-seconds", type=float, default=1.0)
    parser.add_argument("--nominal-frequency-offset-hz", type=float, default=0.0)
    parser.add_argument("--frequency-half-width-hz", type=float, default=400_000.0)
    parser.add_argument("--frequency-step-hz", type=float, default=100_000.0)
    parser.add_argument("--minimum-frame-support", type=int, default=4)
    parser.add_argument("--minimum-epoch-peak-to-median", type=float, default=1.15)
    parser.add_argument("--minimum-epoch-robust-z", type=float, default=6.0)
    parser.add_argument("--maximum-epoch-candidates", type=int, default=8)
    parser.add_argument(
        "--maximum-blocks-per-target",
        type=int,
        help="bounded smoke cap; omission searches every observed continuity block",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    return parser.parse_args()


def _parse_target(raw: str) -> ReplayTarget:
    stream_id, separator, receiver = raw.rpartition(":")
    if not separator or not stream_id:
        raise ValueError("target must have the form STREAM_ID:RECEIVER_ID")
    try:
        receiver_id = int(receiver)
    except ValueError as error:
        raise ValueError("target receiver ID must be an integer") from error
    if receiver_id < 0:
        raise ValueError("target receiver ID must be nonnegative")
    return ReplayTarget(stream_id=stream_id, receiver_id=receiver_id)


def _frequency_bank(
    *, nominal_hz: float, half_width_hz: float, step_hz: float
) -> tuple[float, ...]:
    if not all(math.isfinite(value) for value in (nominal_hz, half_width_hz, step_hz)):
        raise ValueError("frequency-search values must be finite")
    if half_width_hz < 0 or step_hz <= 0:
        raise ValueError("frequency half-width must be nonnegative and step must be positive")
    step_count = math.floor(half_width_hz / step_hz + 1e-12)
    return tuple(nominal_hz + index * step_hz for index in range(-step_count, step_count + 1))


def _continuity_blocks(
    *,
    continuity_segment_index: int,
    device_sample_start: int,
    sample_count: int,
    maximum_block_samples: int,
    minimum_block_samples: int,
) -> tuple[ReplayBlock, ...]:
    if sample_count < 0 or maximum_block_samples <= 0 or minimum_block_samples <= 0:
        raise ValueError("continuity block sizes must be nonnegative with positive limits")
    if sample_count == 0:
        return ()
    output: list[ReplayBlock] = []
    cursor = device_sample_start
    remaining = sample_count
    while remaining:
        count = min(remaining, maximum_block_samples)
        trailing = remaining - count
        if 0 < trailing < minimum_block_samples:
            count = remaining
        output.append(
            ReplayBlock(
                continuity_segment_index=continuity_segment_index,
                device_sample_start=cursor,
                sample_count=count,
            )
        )
        cursor += count
        remaining -= count
    return tuple(output)


def _complex_receiver(samples: np.ndarray) -> np.ndarray:
    if samples.ndim != 3 or samples.shape[1:] != (1, 2):
        raise ValueError("replay requires one selected receiver with interleaved I/Q")
    return np.asarray(samples[:, 0, 0] + 1j * samples[:, 0, 1], dtype=np.complex64)


def _validate_output_path(path: Path) -> None:
    canonical = path.resolve(strict=False)
    if canonical == _QNAP_ROOT or canonical.is_relative_to(_QNAP_ROOT):
        raise ValueError("PSS replay output may not be written beneath the read-only QNAP root")


def _result_document(result: PssFrameTimingResult) -> dict[str, object]:
    value = asdict(result)
    return value


def _replay_target(
    store: RecordingStore,
    bundle: PublishedBundle,
    target: ReplayTarget,
    *,
    channel_reference_hz: float,
    block_seconds: float,
    frequency_offsets_hz: tuple[float, ...],
    nominal_frequency_offset_hz: float,
    config: PssTimingSearchConfig,
    maximum_blocks: int | None,
) -> dict[str, object]:
    reader = store.reader(bundle, target.stream_id, verify=True)
    if target.receiver_id not in reader.receiver_ids:
        raise ValueError(
            f"receiver {target.receiver_id} is absent from {target.stream_id}: "
            f"{reader.receiver_ids}"
        )
    if not math.isfinite(block_seconds) or block_seconds <= 0:
        raise ValueError("replay block duration must be finite and positive")
    if maximum_blocks is not None and maximum_blocks < 1:
        raise ValueError("maximum replay blocks must be positive")

    sample_rate_hz = float(reader.sample_rate_hz)
    slice_center_offset_hz = float(reader.center_frequency_hz - channel_reference_hz)
    template = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=slice_center_offset_hz,
    )
    maximum_block_samples = round(block_seconds * sample_rate_hz)
    minimum_block_samples = (
        math.ceil(config.minimum_frame_support * sample_rate_hz / 750.0) + template.size
    )
    inventory = reader.validity_inventory()
    blocks = tuple(
        block
        for segment in inventory.segments
        for block in _continuity_blocks(
            continuity_segment_index=segment.segment_index,
            device_sample_start=segment.device_sample_start,
            sample_count=segment.observed_sample_count,
            maximum_block_samples=maximum_block_samples,
            minimum_block_samples=minimum_block_samples,
        )
    )
    selected_blocks = blocks if maximum_blocks is None else blocks[:maximum_blocks]

    documents = []
    status_counts: dict[str, int] = {}
    qualified_candidates = 0
    window_count = 0
    for block_index, block in enumerate(selected_blocks):
        span = reader.read_device_span(
            block.device_sample_start,
            block.sample_count,
            receiver_ids=(target.receiver_id,),
        )
        if not np.all(span.valid_samples):
            raise ValueError("an observed replay block unexpectedly contains invalid samples")
        if not np.all(span.continuity_segment_ids == block.continuity_segment_index):
            raise ValueError("replay block crosses a persisted continuity segment")
        result = search_pss_frame_timing(
            _complex_receiver(span.samples),
            sample_rate_hz,
            global_device_sample_start=block.device_sample_start,
            continuity_segment_index=block.continuity_segment_index,
            slice_center_offset_hz=slice_center_offset_hz,
            nominal_frequency_offset_hz=nominal_frequency_offset_hz,
            frequency_offsets_hz=frequency_offsets_hz,
            config=config,
        )
        result_document = _result_document(result)
        documents.append({"block_index": block_index, "result": result_document})
        status = str(result.status)
        status_counts[status] = status_counts.get(status, 0) + 1
        qualified_candidates += len(result.qualified_candidates)
        window_count += len(result.windows)
        if (block_index + 1) % 10 == 0 or block_index + 1 == len(selected_blocks):
            print(
                f"{target.stream_id}:rx{target.receiver_id} "
                f"{block_index + 1}/{len(selected_blocks)} blocks",
                file=sys.stderr,
            )

    return {
        "stream_id": target.stream_id,
        "receiver_id": target.receiver_id,
        "sample_rate_hz": reader.sample_rate_hz,
        "center_frequency_hz": reader.center_frequency_hz,
        "slice_center_offset_hz": slice_center_offset_hz,
        "receiver_ids": list(reader.receiver_ids),
        "validity_inventory_digest": str(inventory.inventory_digest),
        "logical_sample_count": inventory.logical_sample_count,
        "observed_sample_count": inventory.observed_sample_count,
        "missing_sample_count": inventory.missing_sample_count,
        "continuity_segment_count": len(inventory.segments),
        "available_block_count": len(blocks),
        "searched_block_count": len(selected_blocks),
        "bounded": len(selected_blocks) != len(blocks),
        "summary": {
            "status_counts": status_counts,
            "qualified_candidate_count": qualified_candidates,
            "window_count": window_count,
        },
        "blocks": documents,
    }


def main() -> None:
    args = _arguments()
    _validate_output_path(args.output)
    targets = tuple(_parse_target(raw) for raw in args.target)
    if len(set(targets)) != len(targets):
        raise ValueError("replay targets must be unique")
    if args.output.exists() and not args.force:
        raise FileExistsError(f"refusing to replace existing replay output: {args.output}")
    frequency_offsets = _frequency_bank(
        nominal_hz=args.nominal_frequency_offset_hz,
        half_width_hz=args.frequency_half_width_hz,
        step_hz=args.frequency_step_hz,
    )
    config = PssTimingSearchConfig(
        minimum_frame_support=args.minimum_frame_support,
        minimum_epoch_peak_to_median=args.minimum_epoch_peak_to_median,
        minimum_epoch_robust_z=args.minimum_epoch_robust_z,
        maximum_epoch_candidates=args.maximum_epoch_candidates,
    )
    store = RecordingStore.open_read_only(args.bulk_root)
    try:
        bundle = store.inspect(args.capture_id)
        target_documents = [
            _replay_target(
                store,
                bundle,
                target,
                channel_reference_hz=args.channel_reference_hz,
                block_seconds=args.block_seconds,
                frequency_offsets_hz=frequency_offsets,
                nominal_frequency_offset_hz=args.nominal_frequency_offset_hz,
                config=config,
                maximum_blocks=args.maximum_blocks_per_target,
            )
            for target in targets
        ]
        document = {
            "schema_version": 1,
            "analysis_kind": "candidate-only-rate-generic-pss-frame-timing-replay",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "capture_id": args.capture_id,
            "recording_manifest_sha256": bundle.manifest_sha256,
            "channel_reference_hz": args.channel_reference_hz,
            "standard_pipeline_registered": False,
            "candidate_only": True,
            "absolute_carrier_phase_resolved": False,
            "coordinate_semantics": (
                "zero-based device sample offsets from each stream's first FPGA counter"
            ),
            "configuration": {
                **asdict(config),
                "block_seconds": args.block_seconds,
                "nominal_frequency_offset_hz": args.nominal_frequency_offset_hz,
                "frequency_offsets_hz": list(frequency_offsets),
                "maximum_blocks_per_target": args.maximum_blocks_per_target,
            },
            "targets": target_documents,
        }
    finally:
        store.close()

    payload = (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(args.output)
    print(f"wrote {args.output} ({len(payload)} bytes)")
    print(f"sha256:{hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
