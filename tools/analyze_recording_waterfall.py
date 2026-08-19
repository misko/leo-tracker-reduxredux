#!/usr/bin/env python3
"""Render a verified full-dwell recording as frequency-X/time-Y waterfall PNG.

The analysis path is deliberately the same bounded implementation used by the
Standard pipeline: ``RecordingStore`` -> ``RecordingIqReader`` ->
``bounded_waterfall``.  Matplotlib is only the final PNG renderer.

Example:
    uv run --with 'matplotlib>=3.10,<4' python tools/analyze_recording_waterfall.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from leo.analysis.waterfall import WaterfallConfig, WaterfallResult, bounded_waterfall
from leo.storage import PinnedLocalRoot, RecordingStore

if TYPE_CHECKING:
    from matplotlib.axes import Axes


DEFAULT_SESSION = "production-24h-20260819-01-trial-00000132"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_OUTPUT = Path("artifacts/production-24h-20260819-01-trial-00000132-waterfall.png")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", nargs="?", default=DEFAULT_SESSION)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--stream",
        action="append",
        dest="streams",
        help="stream ID to render; repeat for more than one (default: every stream)",
    )
    parser.add_argument(
        "--receiver",
        action="append",
        dest="receivers",
        type=int,
        help="receiver ID to render; repeat for more than one (default: every receiver)",
    )
    parser.add_argument("--time-bins", type=int, default=512)
    parser.add_argument("--frequency-bins", type=int, default=256)
    parser.add_argument("--fft-samples", type=int, default=1024)
    parser.add_argument("--block-samples", type=int, default=262_144)
    return parser.parse_args()


def _matrix(result: WaterfallResult, receiver_index: int) -> np.ndarray:
    """Return time-major dBFS values, retaining missing bins as NaN."""

    return np.asarray(
        [
            [
                math.nan if value is None else value
                for value in tile.receiver_power_dbfs[receiver_index]
            ]
            for tile in result.tiles
        ],
        dtype=np.float64,
    )


def _color_limits(matrices: tuple[np.ndarray, ...]) -> tuple[float, float]:
    finite = np.concatenate(tuple(matrix[np.isfinite(matrix)] for matrix in matrices))
    if finite.size == 0:
        raise ValueError("waterfall contains no finite power values")
    lower, upper = np.percentile(finite, (3.0, 99.7))
    if upper <= lower:
        upper = lower + 1.0
    return float(lower), float(upper)


def _render_panel(
    axis: Axes,
    matrix: np.ndarray,
    result: WaterfallResult,
    *,
    center_frequency_hz: int,
    title: str,
    lower_dbfs: float,
    upper_dbfs: float,
) -> object:
    frequencies_mhz = (
        center_frequency_hz + np.asarray(result.frequency_bin_centers_hz)
    ) / 1_000_000.0
    half_bin_mhz = (
        (frequencies_mhz[1] - frequencies_mhz[0]) / 2.0
        if len(frequencies_mhz) > 1
        else result.sample_rate_hz / 2_000_000.0
    )
    duration_s = result.coverage.expected_samples / result.sample_rate_hz
    image = axis.imshow(
        matrix,
        cmap="magma",
        interpolation="nearest",
        aspect="auto",
        origin="upper",
        extent=(
            frequencies_mhz[0] - half_bin_mhz,
            frequencies_mhz[-1] + half_bin_mhz,
            duration_s,
            0.0,
        ),
        vmin=lower_dbfs,
        vmax=upper_dbfs,
        rasterized=True,
    )
    axis.set_title(title, loc="left", fontsize=10, fontweight="bold")
    axis.set_xlabel("Tuned-domain frequency (MHz)")
    axis.set_ylabel("Elapsed time (s; increases downward)")
    axis.grid(False)
    return image


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    args = _arguments()
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "matplotlib is required only for rendering; run with: "
            "uv run --with 'matplotlib>=3.10,<4' python tools/analyze_recording_waterfall.py"
        ) from error

    config = WaterfallConfig(
        fft_samples=args.fft_samples,
        frequency_bins=args.frequency_bins,
        maximum_time_bins=args.time_bins,
        block_samples=args.block_samples,
    )
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        verification = store.verify(bundle)
        print(
            f"verified {args.session_id}: {verification.chunk_count} chunks, "
            f"{verification.uncompressed_bytes} uncompressed bytes",
            flush=True,
        )
        available = tuple(stream.stream_id for stream in bundle.manifest.streams)
        selected = available if args.streams is None else tuple(args.streams)
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise ValueError(f"recording has no requested streams: {unknown}")
        if not selected:
            raise ValueError("at least one stream is required")

        results: list[tuple[str, str, int, WaterfallResult]] = []
        stream_results: dict[str, WaterfallResult] = {}
        for stream_id in selected:
            print(f"transforming {stream_id} with {config.digest}", flush=True)
            reader = store.reader(bundle, stream_id, verify=True)
            result = bounded_waterfall(reader, config)
            print(
                f"completed {stream_id}: coverage={result.coverage.observed_fraction:.6f}, "
                f"gaps={result.coverage.gap_count}",
                flush=True,
            )
            stream_results[stream_id] = result
            requested_receivers = (
                result.receiver_ids if args.receivers is None else tuple(args.receivers)
            )
            unknown_receivers = sorted(set(requested_receivers) - set(result.receiver_ids))
            if unknown_receivers:
                raise ValueError(
                    f"{stream_id} has no requested receivers: {unknown_receivers}"
                )
            for receiver_id in requested_receivers:
                receiver_index = result.receiver_ids.index(receiver_id)
                results.append(
                    (
                        stream_id,
                        f"RX{receiver_id}",
                        receiver_index,
                        result,
                    )
                )

        matrices = tuple(
            _matrix(result, receiver_index) for _, _, receiver_index, result in results
        )
        lower_dbfs, upper_dbfs = _color_limits(matrices)
        columns = 2 if len(results) > 1 else 1
        rows = math.ceil(len(results) / columns)
        figure, axes = plt.subplots(
            rows,
            columns,
            figsize=(8.2 * columns, 4.2 * rows + 1.0),
            constrained_layout=True,
            squeeze=False,
        )
        last_image: object | None = None
        streams_by_id = {stream.stream_id: stream for stream in bundle.manifest.streams}
        for axis, matrix, (stream_id, receiver_name, _, result) in zip(
            axes.flat, matrices, results, strict=False
        ):
            stream = streams_by_id[stream_id]
            settings = stream.applied_settings or stream.requested_settings
            last_image = _render_panel(
                axis,
                matrix,
                result,
                center_frequency_hz=settings.center_frequency_hz,
                title=f"{stream_id} · {stream.radio.radio_id} · {receiver_name}",
                lower_dbfs=lower_dbfs,
                upper_dbfs=upper_dbfs,
            )
        for unused in tuple(axes.flat)[len(results) :]:
            unused.set_visible(False)
        if last_image is not None:
            figure.colorbar(
                last_image,
                ax=list(axes.flat),
                label="Power spectral density (dBFS)",
            )
        figure.suptitle(
            f"Verified full-dwell waterfall · {args.session_id}\n"
            f"{config.maximum_time_bins} time bins × {config.frequency_bins} frequency bins · "
            f"{config.fft_samples}-sample Hann FFT",
            fontsize=13,
            fontweight="bold",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.output, dpi=160, format="png", metadata={"Software": "leo-tracker"})
        plt.close(figure)

        sidecar = args.output.with_suffix(".json")
        metadata = {
            "session_id": args.session_id,
            "bundle_uri": store.resolver.uri_for(bundle.path),
            "manifest_digest": bundle.manifest_sha256,
            "recording_verification": asdict(verification),
            "algorithm": "bounded-waterfall-v1",
            "configuration": asdict(config),
            "streams": [
                {
                    "stream_id": stream_id,
                    "receiver_ids": [
                        result.receiver_ids[receiver_index]
                        for item_stream_id, _, receiver_index, item_result in results
                        if item_stream_id == stream_id and item_result is result
                    ],
                    "sample_rate_hz": result.sample_rate_hz,
                    "expected_samples": result.coverage.expected_samples,
                    "observed_fraction": result.coverage.observed_fraction,
                    "transformed_fraction": result.coverage.transformed_fraction,
                    "gap_count": result.coverage.gap_count,
                }
                for stream_id, result in stream_results.items()
            ],
            "color_scale_dbfs": [lower_dbfs, upper_dbfs],
            "png_sha256": _sha256(args.output),
        }
        sidecar.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "png": str(args.output.resolve()),
                    "metadata": str(sidecar.resolve()),
                    **metadata,
                }
            )
        )
        return 0
    finally:
        if store is not None:
            store.close()
        pinned.close()


if __name__ == "__main__":
    raise SystemExit(main())
