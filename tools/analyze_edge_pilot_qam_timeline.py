#!/usr/bin/env python3
# ruff: noqa: I001
"""Search Qin edge pilots on a fixed cadence and plot known-pilot QAM quality.

Each configurable outer chunk (default 1 s) is divided into subwindows
(default 50 ms). One or more explicitly placed probes are searched in every
subwindow. The script uses the repository's verified recording
reader, native symbolwise acquisition, held-out control, and known-symbol QAM
kernel.  It never decodes payload data and never makes a calibrated detection
claim.

Example:
    uv run --with 'matplotlib>=3.10,<4' \
      python tools/analyze_edge_pilot_qam_timeline.py SESSION_ID --edge lower
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path

# One BLAS team per process prevents the coarse process pool from multiplying
# hidden numerical worker threads.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np

# Initialize the Starlink package before its QAM re-export; reversing these two
# imports exposes the package's existing acquisition/QAM import cycle.
from leo.analysis.starlink import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    StarlinkEdge,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.qam import analyze_pilot_qam
from leo.contracts.digests import canonical_digest
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_SESSION = "production-24h-20260819-01-trial-00000132"
DEFAULT_OUTPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-qam-timeline.png"
)


@dataclass(frozen=True, slots=True)
class ProbeMetric:
    index: int
    outer_chunk_index: int
    subwindow_index: int
    sample_start: int
    time_s: float
    acquisition_status: str
    candidate_epoch_sample: int | None
    baseband_cfo_hz: float | None
    verify_score: float | None
    control_score: float | None
    pilot_margin: float | None
    qam_status: str
    qam_accuracy: float | None
    qam_rms_evm: float | None
    frame_count: int | None

    @property
    def exploratory_positive(self) -> bool:
        return (
            self.pilot_margin is not None
            and self.pilot_margin >= 0.05
            and self.qam_accuracy is not None
            and self.qam_accuracy >= 0.60
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", nargs="?", default=DEFAULT_SESSION)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument(
        "--edge",
        choices=tuple(edge.value for edge in StarlinkEdge),
        required=True,
    )
    parser.add_argument("--outer-chunk-ms", type=float, default=1000.0)
    parser.add_argument("--subwindow-ms", type=float, default=50.0)
    parser.add_argument("--probe-ms", type=float, default=20.0)
    parser.add_argument(
        "--probe-offsets-ms",
        default="0",
        help="comma-separated probe starts within each subwindow (default: 0)",
    )
    parser.add_argument("--residual-cfo-min-hz", type=float, default=-400_000.0)
    parser.add_argument("--residual-cfo-max-hz", type=float, default=400_000.0)
    parser.add_argument("--coarse-cfo-step-hz", type=float, default=80_000.0)
    parser.add_argument("--fine-cfo-radius-hz", type=float, default=80_000.0)
    parser.add_argument("--fine-cfo-step-hz", type=float, default=500.0)
    parser.add_argument("--conditioned-cfo-step-hz", type=float, default=100.0)
    parser.add_argument("--maximum-outer-chunks", type=int, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="coarse 1-second chunks analyzed concurrently (default: 4)",
    )
    return parser.parse_args()


def _samples(milliseconds: float, sample_rate_hz: int, name: str) -> int:
    if not math.isfinite(milliseconds) or milliseconds <= 0:
        raise ValueError(f"{name} must be finite and positive")
    value = milliseconds * sample_rate_hz / 1000.0
    rounded = round(value)
    if not math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"{name} does not map to an integral sample count")
    return rounded


def _probe_offsets(value: str) -> tuple[float, ...]:
    try:
        offsets = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise ValueError("probe offsets must be comma-separated numbers") from error
    if (
        not offsets
        or any(not math.isfinite(item) or item < 0 for item in offsets)
        or tuple(sorted(set(offsets))) != offsets
    ):
        raise ValueError("probe offsets must be finite, nonnegative, unique, and ordered")
    return offsets


def _window_starts(
    sample_count: int,
    *,
    outer_chunk_samples: int,
    subwindow_samples: int,
    probe_samples: int,
    probe_offset_samples: tuple[int, ...] = (0,),
) -> tuple[tuple[int, int, int], ...]:
    """Return (outer index, subwindow index, absolute probe start)."""

    if min(sample_count, outer_chunk_samples, subwindow_samples, probe_samples) <= 0:
        raise ValueError("sample counts must be positive")
    if probe_samples > subwindow_samples:
        raise ValueError("probe must fit inside one subwindow")
    if (
        not probe_offset_samples
        or tuple(sorted(set(probe_offset_samples))) != probe_offset_samples
        or probe_offset_samples[0] < 0
        or probe_offset_samples[-1] + probe_samples > subwindow_samples
    ):
        raise ValueError("probe offsets must fit uniquely and in order inside one subwindow")
    if outer_chunk_samples % subwindow_samples:
        raise ValueError("outer chunk must contain an integral number of subwindows")
    starts: list[tuple[int, int, int]] = []
    for outer_index, outer_start in enumerate(range(0, sample_count, outer_chunk_samples)):
        outer_stop = min(sample_count, outer_start + outer_chunk_samples)
        for subwindow_index, relative in enumerate(
            range(0, outer_chunk_samples, subwindow_samples)
        ):
            for probe_offset in probe_offset_samples:
                start = outer_start + relative + probe_offset
                if start + probe_samples <= outer_stop:
                    starts.append((outer_index, subwindow_index, start))
    return tuple(starts)


def _calibration(receiver: int) -> ReceiverFrequencyCalibration:
    center_hz = 0.0
    digest = canonical_digest(
        {
            "receiver_id": receiver,
            "baseband_calibration_center_hz": center_hz,
            "source": "no-explicit-baseband-frequency-calibration",
        }
    ).removeprefix("sha256:")
    return ReceiverFrequencyCalibration(str(receiver), center_hz, digest)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 probe must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _analyze_probe(
    item: tuple[int, int, int, int, int, np.ndarray],
    *,
    sample_rate_hz: int,
    seed_cfo_hz: float | None,
    local_acquisition_config: SymbolwiseAcquisitionConfig,
    edge: StarlinkEdge,
) -> ProbeMetric:
    index, outer_index, subwindow_index, sample_start, _, samples = item
    if seed_cfo_hz is None:
        return ProbeMetric(
            index,
            outer_index,
            subwindow_index,
            sample_start,
            sample_start / sample_rate_hz,
            NumericalStatus.NO_RESULT.value,
            None,
            None,
            None,
            None,
            None,
            NumericalStatus.INSUFFICIENT.value,
            None,
            None,
            None,
        )
    local_calibration = ReceiverFrequencyCalibration(
        receiver_id="outer-chunk-tracked-prior",
        center_hz=seed_cfo_hz,
        calibration_sha256=canonical_digest(
            {
                "source": "outer-chunk-wide-acquisition-prior",
                "center_hz": seed_cfo_hz,
            }
        ).removeprefix("sha256:"),
    )
    acquisition = acquire_symbolwise(
        samples,
        sample_rate_hz,
        local_calibration,
        edge=edge,
        config=local_acquisition_config,
    )
    winner = acquisition.winner
    if winner is None:
        return ProbeMetric(
            index,
            outer_index,
            subwindow_index,
            sample_start,
            sample_start / sample_rate_hz,
            acquisition.status.value,
            None,
            None,
            None,
            None,
            None,
            NumericalStatus.INSUFFICIENT.value,
            None,
            None,
            None,
        )
    qam = analyze_pilot_qam(
        samples,
        sample_rate_hz,
        epoch_sample=winner.refined_epoch_sample,
        absolute_cfo_hz=winner.absolute_cfo_hz,
        edge=edge,
    )
    metrics = qam.metrics
    return ProbeMetric(
        index,
        outer_index,
        subwindow_index,
        sample_start,
        sample_start / sample_rate_hz,
        acquisition.status.value,
        winner.refined_epoch_sample,
        qam.absolute_cfo_hz,
        winner.verify_score,
        winner.conditioned_control_score,
        winner.verify_minus_control_margin,
        qam.status.value,
        None if metrics is None else metrics.hard_symbol_accuracy,
        None if metrics is None else metrics.rms_evm,
        None if metrics is None else metrics.frame_count,
    )


def _write_csv(path: Path, metrics: tuple[ProbeMetric, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=tuple(asdict(metrics[0])))
        writer.writeheader()
        for metric in metrics:
            writer.writerow(asdict(metric))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _analyze_outer_chunk(
    request: tuple[
        int,
        int,
        int,
        np.ndarray,
        int,
        int,
        int,
        int,
        tuple[int, ...],
        ReceiverFrequencyCalibration,
        SymbolwiseAcquisitionConfig,
        SymbolwiseAcquisitionConfig,
        StarlinkEdge,
    ],
) -> tuple[ProbeMetric, ...]:
    (
        outer_index,
        outer_start,
        first_probe_index,
        outer,
        sample_rate_hz,
        outer_samples,
        subwindow_samples,
        probe_samples,
        probe_offset_samples,
        calibration,
        wide_config,
        local_config,
        edge,
    ) = request
    seed = acquire_symbolwise(
        np.ascontiguousarray(outer[:probe_samples]),
        sample_rate_hz,
        calibration,
        edge=edge,
        config=wide_config,
    ).winner
    results: list[ProbeMetric] = []
    index = first_probe_index
    for subwindow_index, relative in enumerate(range(0, outer_samples, subwindow_samples)):
        for probe_offset in probe_offset_samples:
            probe_start = relative + probe_offset
            if probe_start + probe_samples > len(outer):
                continue
            sample_start = outer_start + probe_start
            results.append(
                _analyze_probe(
                    (
                        index,
                        outer_index,
                        subwindow_index,
                        sample_start,
                        probe_start,
                        np.ascontiguousarray(outer[probe_start : probe_start + probe_samples]),
                    ),
                    sample_rate_hz=sample_rate_hz,
                    seed_cfo_hz=None if seed is None else seed.absolute_cfo_hz,
                    local_acquisition_config=local_config,
                    edge=edge,
                )
            )
            index += 1
    return tuple(results)


def _render(
    path: Path,
    metrics: tuple[ProbeMetric, ...],
    title: str,
    *,
    subwindow_ms: float,
    probe_ms: float,
    probe_offsets_ms: tuple[float, ...],
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "matplotlib is required only for rendering; run with: "
            "uv run --with 'matplotlib>=3.10,<4' python "
            "tools/analyze_edge_pilot_qam_timeline.py"
        ) from error

    times = np.asarray([item.time_s for item in metrics])
    accuracy = np.asarray(
        [math.nan if item.qam_accuracy is None else item.qam_accuracy for item in metrics]
    )
    margin = np.asarray(
        [math.nan if item.pilot_margin is None else item.pilot_margin for item in metrics]
    )
    positive = np.asarray([item.exploratory_positive for item in metrics])

    figure, (qam_axis, pilot_axis) = plt.subplots(
        2,
        1,
        figsize=(15, 8),
        sharex=True,
        constrained_layout=True,
        gridspec_kw={"height_ratios": (2, 1)},
    )
    qam_axis.plot(times, accuracy, color="#8c8c8c", linewidth=0.65, alpha=0.75)
    qam_axis.scatter(
        times[~positive],
        accuracy[~positive],
        s=8,
        color="#8c8c8c",
        alpha=0.55,
        label="searched probe",
    )
    qam_axis.scatter(
        times[positive],
        accuracy[positive],
        s=14,
        color="#00a878",
        alpha=0.9,
        label="accuracy ≥ 0.60 and pilot margin ≥ 0.05",
    )
    qam_axis.axhline(0.60, color="#d1495b", linestyle="--", linewidth=1.2)
    qam_axis.set_ylim(0, 1.02)
    qam_axis.set_ylabel("Known-pilot hard-symbol accuracy")
    qam_axis.set_title(title, loc="left", fontweight="bold")
    qam_axis.grid(alpha=0.2)
    qam_axis.legend(loc="upper right")

    pilot_axis.plot(times, margin, color="#355070", linewidth=0.8)
    pilot_axis.scatter(times[positive], margin[positive], s=11, color="#00a878", alpha=0.9)
    pilot_axis.axhline(0.05, color="#d1495b", linestyle="--", linewidth=1.2)
    pilot_axis.axhline(0.0, color="black", linewidth=0.6, alpha=0.5)
    pilot_axis.set_xlabel("Elapsed recording time (s)")
    pilot_axis.set_ylabel("Pilot verify − control margin")
    pilot_axis.grid(alpha=0.2)
    figure.suptitle(
        f"{probe_ms:g} ms Qin edge-pilot probes at offsets "
        f"{','.join(f'{item:g}' for item in probe_offsets_ms)} ms per "
        f"{subwindow_ms:g} ms · candidate-only · no payload",
        fontsize=11,
    )
    figure.savefig(path, dpi=160, format="png", metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> int:
    args = _arguments()
    if args.workers < 1 or args.workers > 16:
        raise ValueError("workers must lie in 1..16")
    if args.maximum_outer_chunks is not None and args.maximum_outer_chunks < 1:
        raise ValueError("maximum_outer_chunks must be positive when supplied")
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        verification = store.verify(bundle)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError(f"stream has no receiver {args.receiver}")
        outer_samples = _samples(args.outer_chunk_ms, reader.sample_rate_hz, "outer chunk")
        subwindow_samples = _samples(args.subwindow_ms, reader.sample_rate_hz, "subwindow")
        probe_samples = _samples(args.probe_ms, reader.sample_rate_hz, "probe")
        probe_offsets_ms = _probe_offsets(args.probe_offsets_ms)
        probe_offset_samples = tuple(
            _samples(item, reader.sample_rate_hz, "probe offset") if item else 0
            for item in probe_offsets_ms
        )
        starts = _window_starts(
            reader.sample_count,
            outer_chunk_samples=outer_samples,
            subwindow_samples=subwindow_samples,
            probe_samples=probe_samples,
            probe_offset_samples=probe_offset_samples,
        )
        if args.maximum_outer_chunks is not None:
            starts = tuple(item for item in starts if item[0] < args.maximum_outer_chunks)
        config = SymbolwiseAcquisitionConfig(
            residual_cfo_min_hz=args.residual_cfo_min_hz,
            residual_cfo_max_hz=args.residual_cfo_max_hz,
            coarse_cfo_step_hz=args.coarse_cfo_step_hz,
            fine_cfo_radius_hz=args.fine_cfo_radius_hz,
            fine_cfo_step_hz=args.fine_cfo_step_hz,
            conditioned_cfo_step_hz=args.conditioned_cfo_step_hz,
            maximum_probe_samples=probe_samples,
        )
        local_config = SymbolwiseAcquisitionConfig(
            residual_cfo_min_hz=-20_000.0,
            residual_cfo_max_hz=20_000.0,
            coarse_cfo_step_hz=min(args.coarse_cfo_step_hz, 5_000.0),
            fine_cfo_radius_hz=20_000.0,
            fine_cfo_step_hz=args.fine_cfo_step_hz,
            conditioned_cfo_step_hz=args.conditioned_cfo_step_hz,
            retained_candidate_count=2,
            maximum_probe_samples=probe_samples,
        )
        calibration = _calibration(args.receiver)
        edge = StarlinkEdge(args.edge)
        print(
            f"verified {args.session_id}: {verification.chunk_count} chunks; "
            f"searching {len(starts)} probes across {args.workers} coarse-chunk workers",
            flush=True,
        )

        collected: list[ProbeMetric] = []
        total_outer = math.ceil(reader.sample_count / outer_samples)
        if args.maximum_outer_chunks is not None:
            total_outer = min(total_outer, args.maximum_outer_chunks)
        completed_outer = 0
        next_probe_index = 0
        pending: set[Future[tuple[ProbeMetric, ...]]] = set()
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for outer_index, outer_start in enumerate(range(0, reader.sample_count, outer_samples)):
                if outer_index >= total_outer:
                    break
                count = min(outer_samples, reader.sample_count - outer_start)
                outer = _complex_receiver(
                    reader.read(
                        outer_start,
                        count,
                        receiver_ids=(args.receiver,),
                    )
                )
                probe_count = sum(
                    relative + probe_offset + probe_samples <= count
                    for relative in range(0, outer_samples, subwindow_samples)
                    for probe_offset in probe_offset_samples
                )
                pending.add(
                    executor.submit(
                        _analyze_outer_chunk,
                        (
                            outer_index,
                            outer_start,
                            next_probe_index,
                            outer,
                            reader.sample_rate_hz,
                            outer_samples,
                            subwindow_samples,
                            probe_samples,
                            probe_offset_samples,
                            calibration,
                            config,
                            local_config,
                            edge,
                        ),
                    )
                )
                next_probe_index += probe_count
                if len(pending) >= args.workers * 2:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        collected.extend(future.result())
                        completed_outer += 1
                    print(
                        f"completed {completed_outer}/{total_outer} coarse chunks",
                        flush=True,
                    )
            while pending:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    collected.extend(future.result())
                    completed_outer += 1
                print(
                    f"completed {completed_outer}/{total_outer} coarse chunks",
                    flush=True,
                )
        metrics = tuple(sorted(collected, key=lambda item: item.index))
        if len(metrics) != len(starts):
            raise RuntimeError("analyzed probe count differs from the declared schedule")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        _render(
            args.output,
            metrics,
            f"{args.session_id} · {args.stream} · RX{args.receiver} · {edge.value} edge",
            subwindow_ms=args.subwindow_ms,
            probe_ms=args.probe_ms,
            probe_offsets_ms=probe_offsets_ms,
        )
        csv_path = args.output.with_suffix(".csv")
        _write_csv(csv_path, metrics)
        json_path = args.output.with_suffix(".json")
        positives = sum(item.exploratory_positive for item in metrics)
        document = {
            "session_id": args.session_id,
            "bundle_uri": store.resolver.uri_for(bundle.path),
            "manifest_digest": bundle.manifest_sha256,
            "stream_id": args.stream,
            "receiver_id": args.receiver,
            "edge": edge.value,
            "known_symbols_only": True,
            "candidate_only": True,
            "payload_decoded": False,
            "windowing": {
                "outer_chunk_ms": args.outer_chunk_ms,
                "subwindow_ms": args.subwindow_ms,
                "probe_ms": args.probe_ms,
                "probe_offsets_ms": list(probe_offsets_ms),
                "probe_count": len(metrics),
                "coarse_parallel_workers": args.workers,
            },
            "outer_acquisition_config_digest": canonical_digest(asdict(config)),
            "probe_acquisition_config_digest": canonical_digest(asdict(local_config)),
            "positive_gate": {"minimum_qam_accuracy": 0.60, "minimum_pilot_margin": 0.05},
            "exploratory_positive_count": positives,
            "maximum_qam_accuracy": max(
                (item.qam_accuracy for item in metrics if item.qam_accuracy is not None),
                default=None,
            ),
            "maximum_pilot_margin": max(
                (item.pilot_margin for item in metrics if item.pilot_margin is not None),
                default=None,
            ),
            "png_sha256": _sha256(args.output),
            "csv_sha256": _sha256(csv_path),
        }
        json_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "png": str(args.output.resolve()),
                    "csv": str(csv_path.resolve()),
                    "metadata": str(json_path.resolve()),
                    **document,
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
