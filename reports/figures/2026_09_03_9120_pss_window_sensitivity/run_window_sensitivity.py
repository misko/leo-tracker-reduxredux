#!/usr/bin/env python3
"""Replay native PSS timing with half/baseline/double window geometry.

This is a recording-specific analysis driver, not a production pipeline entry
point.  The immutable path binding is supplied on stdin from the catalog.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from leo.analysis.standard.native_pss import (  # noqa: E402
    StandardNativePssConfig,
    StandardNativePssRunner,
)
from leo.contracts.standard_native_pss import (  # noqa: E402
    StandardNativePssFrameTimingV1,
)
from leo.pipeline.validity import DeviceIqSpan  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402

from leo.contracts.standard_pipeline import StandardPathInputBindV5  # noqa: E402
from leo.storage.store import RecordingStore  # noqa: E402

SESSION_ID = "cap-20260903T004006-9120aba2922e"
RUN_ID = "native-capture-e77330d77f904d928137be403995a77f"
RELEASE_REVISION = "2524936bd8bd6fee417cfcedcdb6b44ed6bd9a7f"
RF_REFERENCE_HZ = 9_750_000_000.0 + 1_467_500_000.0
BASELINE_PRODUCT = Path(
    "/srv/bulk/leo/analysis/cap-20260903T004006-9120aba2922e/"
    "native-capture-e77330d77f904d928137be403995a77f/scientific/"
    "path-pss-native/"
    "sha256:206dad357c678770b9f1b5257f0dad385aecff9348ec08198f258bdf5c398c80/"
    "standard.pss-frame-timing.v1.json"
)
VARIANTS = {
    "half": (0.0625, 0.03125),
    "baseline": (0.125, 0.0625),
    "double": (0.25, 0.125),
}
COLORS = {"half": "#16a34a", "baseline": "#f97316", "double": "#2563eb"}


class CachingReadOnlyStore(RecordingStore):
    """Keep a tiny verified decompression cache for overlapping offline reads."""

    cache_limit = 3

    def _ensure_cache(self) -> None:
        if not hasattr(self, "_replay_cache"):
            self._replay_cache: OrderedDict[tuple[str, bool], bytes] = OrderedDict()
            self.cache_hits = 0
            self.cache_misses = 0

    def _decompress_chunk(self, bundle_path, stream, chunk, *, verify):  # type: ignore[no-untyped-def]
        self._ensure_cache()
        key = (chunk.relative_path, verify)
        payload = self._replay_cache.get(key)
        if payload is not None:
            self.cache_hits += 1
            self._replay_cache.move_to_end(key)
            return payload
        started = time.monotonic()
        payload = super()._decompress_chunk(bundle_path, stream, chunk, verify=verify)
        self.cache_misses += 1
        self._replay_cache[key] = payload
        self._replay_cache.move_to_end(key)
        while len(self._replay_cache) > self.cache_limit:
            self._replay_cache.popitem(last=False)
        print(
            f"verified/decompressed {chunk.relative_path} "
            f"({len(payload) / 1e6:.1f} MB in {time.monotonic() - started:.1f}s)",
            flush=True,
        )
        return payload


class BoundReplayReader:
    """Minimal validity-aware read port over one immutable receiver path."""

    def __init__(self, store: CachingReadOnlyStore, binding: StandardPathInputBindV5) -> None:
        self._store = store
        self._binding = binding
        self._bundle = store.inspect(binding.session_id)
        self._read_count = 0

    @property
    def sample_rate_hz(self) -> int:
        return self._binding.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._binding.tuned_center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._binding.logical_sample_count

    @property
    def observed_sample_count(self) -> int:
        return self._binding.observed_sample_count

    @property
    def missing_sample_count(self) -> int:
        return self._binding.missing_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (self._binding.receiver_id,)

    @property
    def validity_inventory(self):  # type: ignore[no-untyped-def]
        return self._binding.validity_inventory

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        stop = device_sample_start + sample_count
        segment = next(
            (
                item
                for item in self.validity_inventory.segments
                if item.device_sample_start <= device_sample_start
                and stop <= item.device_sample_stop
            ),
            None,
        )
        if segment is None:
            raise ValueError("PSS replay requested IQ outside one observed continuity segment")
        values = self._store.read_ci16(
            self._bundle,
            self._binding.stream_id,
            device_sample_start,
            sample_count,
            receiver_ids=self.receiver_ids,
            verify=True,
        )
        self._read_count += 1
        if self._read_count % 100 == 0:
            print(
                f"completed {self._read_count} bounded IQ reads "
                f"(cache {self._store.cache_hits} hits/{self._store.cache_misses} loads)",
                flush=True,
            )
        return DeviceIqSpan(
            samples=np.ascontiguousarray(values),
            valid_samples=np.ones(sample_count, dtype=np.bool_),
            continuity_segment_ids=np.full(
                sample_count,
                segment.segment_index,
                dtype=np.int32,
            ),
            device_sample_start=device_sample_start,
            receiver_ids=self.receiver_ids,
        )

    def close(self) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recording-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--run",
        choices=("half", "double", "both", "summary"),
        default="both",
    )
    return parser.parse_args()


def load_binding() -> StandardPathInputBindV5:
    document = json.load(sys.stdin)
    binding = StandardPathInputBindV5.model_validate(document)
    if binding.session_id != SESSION_ID or binding.sample_rate_hz != 25_000_000:
        raise ValueError("stdin path binding is not the requested native-25 recording path")
    return binding


def load_product(path: Path) -> StandardNativePssFrameTimingV1:
    return StandardNativePssFrameTimingV1.model_validate_json(path.read_bytes())


def atomic_write_product(path: Path, product: StandardNativePssFrameTimingV1) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(product.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_variant(
    name: str,
    *,
    reader: BoundReplayReader,
    binding: StandardPathInputBindV5,
    output_dir: Path,
) -> StandardNativePssFrameTimingV1:
    window_s, stride_s = VARIANTS[name]
    path = output_dir / f"pss-{name}-{window_s * 1e3:g}ms-{stride_s * 1e3:g}ms.json"
    if path.exists():
        product = load_product(path)
        if product.source.path_input_binding_digest != binding.binding_digest:
            raise ValueError(f"cached {name} product has a foreign path binding")
        print(f"reusing validated {name} product: {path}", flush=True)
        return product
    baseline = StandardNativePssConfig()
    required_samples = round(window_s * binding.sample_rate_hz)
    config = replace(
        baseline,
        maximum_block_duration_s=window_s,
        block_overlap_duration_s=window_s - stride_s,
        maximum_input_block_samples=max(baseline.maximum_input_block_samples, required_samples),
    )
    print(
        f"starting {name}: {window_s * 1e3:g} ms window / "
        f"{stride_s * 1e3:g} ms stride / {required_samples:,} samples",
        flush=True,
    )
    started = time.monotonic()
    product = StandardNativePssRunner(config).run(reader, binding)
    atomic_write_product(path, product)
    print(
        f"finished {name} in {(time.monotonic() - started) / 60:.2f} min: "
        f"{len(product.modes)} modes, {len(product.tracks)} tracks",
        flush=True,
    )
    return product


def dominant_track(product: StandardNativePssFrameTimingV1):  # type: ignore[no-untyped-def]
    if not product.tracks:
        return None
    return max(
        product.tracks,
        key=lambda item: (
            len(item.mode_ids),
            item.time_stop_s - item.time_start_s,
            -item.rms_residual_us,
            item.track_id,
        ),
    )


def possible_block_count(binding: StandardPathInputBindV5, window_s: float, stride_s: float) -> int:
    window = round(window_s * binding.sample_rate_hz)
    stride = round(stride_s * binding.sample_rate_hz)
    return sum(
        0
        if segment.observed_sample_count < window
        else 1 + (segment.observed_sample_count - window) // stride
        for segment in binding.validity_inventory.segments
    )


def summarize(
    name: str,
    product: StandardNativePssFrameTimingV1,
    binding: StandardPathInputBindV5,
) -> dict[str, Any]:
    window_s, stride_s = VARIANTS[name]
    track = dominant_track(product)
    possible = possible_block_count(binding, window_s, stride_s)
    anchor_count = sum(item.block_index < possible for item in product.blocks)
    tracking_count = len(product.blocks) - anchor_count
    anchor_candidates = sum(
        bool(item.retained_mode_ids) for item in product.blocks if item.block_index < possible
    )
    tracking_candidates = sum(
        bool(item.retained_mode_ids) for item in product.blocks if item.block_index >= possible
    )
    block_lengths = {
        item.input_device_sample_stop - item.input_device_sample_start for item in product.blocks
    }
    row: dict[str, Any] = {
        "variant": name,
        "window_ms": window_s * 1e3,
        "stride_ms": stride_s * 1e3,
        "overlap_percent": 100.0 * (window_s - stride_s) / window_s,
        "nominal_pss_opportunities_per_window": window_s * 750.0,
        "requested_samples_per_window": round(window_s * binding.sample_rate_hz),
        "actual_block_sample_counts": sorted(block_lengths),
        "complete_windows_over_observed_segments": possible,
        "blind_anchor_blocks_searched": anchor_count,
        "blind_anchor_candidate_blocks": anchor_candidates,
        "blind_anchor_candidate_fraction": (
            anchor_candidates / anchor_count if anchor_count else None
        ),
        "refined_tracking_blocks_searched": tracking_count,
        "refined_tracking_candidate_blocks": tracking_candidates,
        "refined_tracking_candidate_fraction": (
            tracking_candidates / tracking_count if tracking_count else None
        ),
        "searched_blocks": len(product.blocks),
        "candidate_blocks": product.accounting.candidate_block_count,
        "candidate_block_fraction": (
            product.accounting.candidate_block_count / len(product.blocks)
            if product.blocks
            else None
        ),
        "retained_modes": len(product.modes),
        "track_count": len(product.tracks),
        "science_configuration_digest": product.science_configuration_digest,
        "result_digest": product.result_digest,
    }
    if track is None:
        row.update(
            {
                "dominant_track_points": 0,
                "dominant_track_span_s": None,
                "quadratic_rms_us": None,
                "quadratic_max_abs_us": None,
                "frequency_rate_khz_per_s": None,
                "nonoverlap_parity_rates_khz_per_s": None,
                "nonoverlap_parity_rate_spread_hz_per_s": None,
                "median_peak_to_median": None,
                "median_robust_z": None,
                "median_frame_support": None,
                "strong_window_fraction": None,
            }
        )
        return row
    modes_by_id = {item.mode_id: item for item in product.modes}
    modes = [modes_by_id[item] for item in track.mode_ids]
    window_count = sum(item.window_count for item in modes)
    times = np.asarray([item.center_time_s for item in modes], dtype=float)
    phase = np.polyval(
        np.asarray(track.coefficients_descending_s),
        times - track.time_origin_s,
    ) + np.asarray(track.residuals_us) / 1e6
    parity_rates = []
    for parity in (0, 1):
        indexes = np.arange(parity, len(times), 2)
        coefficients = np.polyfit(times[indexes] - np.mean(times[indexes]), phase[indexes], 2)
        parity_rates.append(-RF_REFERENCE_HZ * 2.0 * coefficients[0] / 1e3)
    row.update(
        {
            "dominant_track_points": len(modes),
            "dominant_track_span_s": track.time_stop_s - track.time_start_s,
            "dominant_track_start_s": track.time_start_s,
            "dominant_track_stop_s": track.time_stop_s,
            "quadratic_rms_us": track.rms_residual_us,
            "quadratic_max_abs_us": track.maximum_absolute_residual_us,
            "frequency_rate_khz_per_s": (
                -RF_REFERENCE_HZ * 2.0 * track.coefficients_descending_s[0] / 1e3
            ),
            "nonoverlap_parity_rates_khz_per_s": parity_rates,
            "nonoverlap_parity_rate_spread_hz_per_s": (
                abs(parity_rates[0] - parity_rates[1]) * 1e3
            ),
            "median_peak_to_median": float(np.median([item.peak_to_median for item in modes])),
            "median_robust_z": float(np.median([item.robust_z for item in modes])),
            "median_frame_support": float(np.median([item.frame_support for item in modes])),
            "strong_window_fraction": (
                sum(item.strong_window_count for item in modes) / window_count
                if window_count
                else None
            ),
        }
    )
    return row


def track_arrays(product: StandardNativePssFrameTimingV1):  # type: ignore[no-untyped-def]
    track = dominant_track(product)
    if track is None:
        return None
    modes_by_id = {item.mode_id: item for item in product.modes}
    modes = [modes_by_id[item] for item in track.mode_ids]
    times = np.asarray([item.center_time_s for item in modes], dtype=float)
    local = times - track.time_origin_s
    coefficients = np.asarray(track.coefficients_descending_s, dtype=float)
    phase = np.polyval(coefficients, local) + np.asarray(track.residuals_us) / 1e6
    affine_origin = float(np.mean(times))
    affine = np.polyfit(times - affine_origin, phase, 1)
    linear_residual_us = (phase - np.polyval(affine, times - affine_origin)) * 1e6
    drift = 2.0 * coefficients[0] * local + coefficients[1]
    return track, times, linear_residual_us, np.asarray(track.residuals_us), drift


def write_comparison(
    products: dict[str, StandardNativePssFrameTimingV1],
    binding: StandardPathInputBindV5,
    output_dir: Path,
) -> None:
    rows = [summarize(name, products[name], binding) for name in VARIANTS]
    baseline_rate = next(
        row["frequency_rate_khz_per_s"] for row in rows if row["variant"] == "baseline"
    )
    for row in rows:
        rate = row["frequency_rate_khz_per_s"]
        row["rate_delta_from_baseline_hz_per_s"] = (
            None if rate is None else (rate - baseline_rate) * 1e3
        )
        row["rate_delta_from_baseline_percent"] = (
            None if rate is None else 100.0 * (rate - baseline_rate) / baseline_rate
        )
    comparison = {
        "session_id": SESSION_ID,
        "analysis_run_id": RUN_ID,
        "release_revision": RELEASE_REVISION,
        "path_input_binding_digest": binding.binding_digest,
        "rf_reference_hz": RF_REFERENCE_HZ,
        "fit_weighting": "equal weight per retained PSS mode in np.polyfit",
        "variants": rows,
    }
    (output_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    columns = list(rows[0])
    with (output_dir / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    available = {name: track_arrays(product) for name, product in products.items()}
    absolute_reference = float(
        np.mean(
            [
                value[1].mean()
                for value in available.values()
                if value is not None
            ]
        )
    )
    figure, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True, constrained_layout=True)
    for axis in axes:
        axis.grid(True, alpha=0.22)
        axis.axhline(0.0, color="#111827", linewidth=0.8)
    for name in VARIANTS:
        arrays = available[name]
        if arrays is None:
            continue
        track, times, linear_residual, quadratic_residual, drift = arrays
        label = f"{VARIANTS[name][0] * 1e3:g}/{VARIANTS[name][1] * 1e3:g} ms"
        marker = {"half": ".", "baseline": "x", "double": "o"}[name]
        marker_style = (
            {"facecolors": "none", "edgecolors": COLORS[name]}
            if marker == "o"
            else {"color": COLORS[name]}
        )
        axes[0].scatter(
            times,
            linear_residual,
            s={"half": 13, "baseline": 22, "double": 18}[name],
            marker=marker,
            alpha=0.8,
            label=label,
            **marker_style,
        )
        axes[1].scatter(
            times,
            quadratic_residual,
            s={"half": 13, "baseline": 22, "double": 18}[name],
            marker=marker,
            alpha=0.8,
            label=f"{label} · RMS {track.rms_residual_us:.3f} µs",
            **marker_style,
        )
        reference_drift = float(
            2.0 * track.coefficients_descending_s[0] * (absolute_reference - track.time_origin_s)
            + track.coefficients_descending_s[1]
        )
        frequency_change = -RF_REFERENCE_HZ * (drift - reference_drift) / 1e3
        rate = -RF_REFERENCE_HZ * 2.0 * track.coefficients_descending_s[0] / 1e3
        axes[2].plot(
            times,
            frequency_change,
            color=COLORS[name],
            linewidth=2.0,
            label=f"{label} · {rate:+.3f} kHz/s",
        )
    axes[0].set_ylabel("Affine-fit residual (µs)")
    axes[0].set_title("A · PSS timing curvature after an independent affine fit")
    axes[1].set_ylabel("Quadratic-fit residual (µs)")
    axes[1].set_title("B · Residual noise around each independently fitted quadratic")
    axes[2].set_ylabel("Frequency change (kHz)")
    axes[2].set_xlabel("Device-axis seconds from recording start")
    axes[2].set_title("C · Phase-derived frequency change about a common time reference")
    for axis in axes:
        axis.legend(loc="best", fontsize=8)
    figure.suptitle(
        f"{SESSION_ID} · native 25 MS/s PSS window/stride sensitivity\n"
        "same blind/tracking detector settings · 50% overlap · independent equal-weight fits"
    )
    figure.savefig(output_dir / "comparison.png", dpi=170)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    binding = load_binding()
    baseline = load_product(BASELINE_PRODUCT)
    if baseline.source.path_input_binding_digest != binding.binding_digest:
        raise ValueError("persisted baseline and catalog path binding disagree")
    products = {"baseline": baseline}
    requested = (
        ()
        if args.run == "summary"
        else ("half", "double")
        if args.run == "both"
        else (args.run,)
    )
    store = CachingReadOnlyStore.open_read_only(args.recording_root)
    reader = BoundReplayReader(store, binding)
    try:
        for name in requested:
            products[name] = run_variant(
                name,
                reader=reader,
                binding=binding,
                output_dir=args.output_dir,
            )
        for name in ("half", "double"):
            if name in products:
                continue
            window_s, stride_s = VARIANTS[name]
            path = args.output_dir / f"pss-{name}-{window_s * 1e3:g}ms-{stride_s * 1e3:g}ms.json"
            if path.exists():
                products[name] = load_product(path)
        if set(products) != set(VARIANTS):
            print(
                json.dumps(
                    [
                        summarize(name, products[name], binding)
                        for name in VARIANTS
                        if name in products
                    ],
                    indent=2,
                )
            )
            return
        write_comparison(products, binding, args.output_dir)
    finally:
        reader.close()
        store.close()
    print(json.dumps([summarize(name, products[name], binding) for name in VARIANTS], indent=2))


if __name__ == "__main__":
    main()
