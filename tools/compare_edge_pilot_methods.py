#!/usr/bin/env python3
"""Compare historical Starlink edge-pilot methods on one QAM timeline.

The input CSV is produced by ``analyze_edge_pilot_qam_timeline.py``.  Every
method is evaluated on the same 20 ms IQ probe and at the same acquired frame
epoch/coarse CFO, making the curves comparable.  Anchor, differential and GLRT
scores are exact-Qin-code minus the 17-symbol rolled control.  This is an
exploratory comparison of known pilot symbols; it does not decode payload data
or make a calibrated detection claim.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass, fields
from pathlib import Path

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np

from leo.analysis.starlink import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_frame,
)
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_SESSION = "production-24h-20260819-01-trial-00000132"
DEFAULT_TIMELINE = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-qam-timeline.csv"
)
DEFAULT_OUTPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.png"
)
FIRST_PILOT_SYMBOL = 2
LAST_PILOT_SYMBOL = 301
GLRT_SIZE = 512


@dataclass(frozen=True, slots=True)
class AcquiredProbe:
    index: int
    outer_chunk_index: int
    subwindow_index: int
    sample_start: int
    time_s: float
    candidate_epoch_sample: int | None
    baseband_cfo_hz: float | None
    pilot_margin: float | None
    qam_accuracy: float | None


@dataclass(frozen=True, slots=True)
class MethodMetric:
    index: int
    time_s: float
    sample_start: int
    acquired_epoch_sample: int | None
    acquired_cfo_hz: float | None
    anchor8_score: float | None
    anchor8_control_score: float | None
    anchor8_margin: float | None
    differential16_score: float | None
    differential16_control_score: float | None
    differential16_margin: float | None
    differential16_residual_cfo_hz: float | None
    differential32_score: float | None
    differential32_control_score: float | None
    differential32_margin: float | None
    differential32_residual_cfo_hz: float | None
    glrt32_score: float | None
    glrt32_control_score: float | None
    glrt32_margin: float | None
    glrt32_residual_cfo_hz: float | None
    glrt64_score: float | None
    glrt64_control_score: float | None
    glrt64_margin: float | None
    glrt64_residual_cfo_hz: float | None
    edge_tracker_score: float | None
    edge_tracker_control_score: float | None
    edge_tracker_margin: float | None
    edge_tracker_coherence: float | None
    edge_tracker_control_coherence: float | None
    symbolwise_margin: float | None
    qam_accuracy: float | None


@dataclass(frozen=True, slots=True)
class SymbolCorrelations:
    values: np.ndarray
    normalized_power: np.ndarray
    times_s: np.ndarray

    @property
    def symbol_step_s(self) -> float:
        if self.values.shape[1] < 2:
            return OFDM_SYMBOL_DURATION_S
        return float(np.median(np.diff(self.times_s, axis=1)))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", nargs="?", default=DEFAULT_SESSION)
    parser.add_argument("--timeline-csv", type=Path, default=DEFAULT_TIMELINE)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument(
        "--edge",
        choices=tuple(edge.value for edge in StarlinkEdge),
        default=StarlinkEdge.LOWER.value,
    )
    parser.add_argument("--probe-ms", type=float, default=20.0)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def _optional_int(value: str) -> int | None:
    return None if not value else int(value)


def _optional_float(value: str) -> float | None:
    return None if not value else float(value)


def _load_timeline(path: Path) -> tuple[AcquiredProbe, ...]:
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    probes = tuple(
        AcquiredProbe(
            index=int(row["index"]),
            outer_chunk_index=int(row["outer_chunk_index"]),
            subwindow_index=int(row["subwindow_index"]),
            sample_start=int(row["sample_start"]),
            time_s=float(row["time_s"]),
            candidate_epoch_sample=_optional_int(row["candidate_epoch_sample"]),
            baseband_cfo_hz=_optional_float(row["baseband_cfo_hz"]),
            pilot_margin=_optional_float(row["pilot_margin"]),
            qam_accuracy=_optional_float(row["qam_accuracy"]),
        )
        for row in rows
    )
    if not probes or tuple(item.index for item in probes) != tuple(range(len(probes))):
        raise ValueError("timeline probes must be nonempty and indexed contiguously")
    if any(
        left.sample_start >= right.sample_start
        for left, right in zip(probes, probes[1:], strict=False)
    ):
        raise ValueError("timeline probes must have strictly increasing sample starts")
    return probes


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 probe must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _symbol_correlations(
    samples: np.ndarray,
    sample_rate_hz: int,
    epoch_sample: int,
    cfo_hz: float,
    symbols: np.ndarray,
    *,
    symbol_roll: int,
    edge: StarlinkEdge,
) -> SymbolCorrelations:
    """Retain complex per-symbol matched-filter outputs instead of |z|²."""

    values = np.asarray(samples, np.complex128)
    chosen = np.asarray(symbols, dtype=int)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if chosen.ndim != 1 or not chosen.size or np.any(np.diff(chosen) <= 0):
        raise ValueError("symbols must be a nonempty strictly increasing vector")
    if chosen[0] < FIRST_PILOT_SYMBOL or chosen[-1] > LAST_PILOT_SYMBOL:
        raise ValueError("pilot symbol index lies outside 2..301")

    template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, edge, symbol_roll=symbol_roll),
        np.complex128,
    )
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    rows: list[list[complex]] = []
    powers: list[list[float]] = []
    moments: list[list[float]] = []
    frame = 0
    while True:
        frame_start = epoch_sample + round(frame * frame_period)
        if frame_start >= len(values):
            break
        row: list[complex] = []
        row_power: list[float] = []
        row_moments: list[float] = []
        complete = True
        for symbol in chosen:
            local_start = round(int(symbol) * symbol_period)
            local_stop = min(round((int(symbol) + 1) * symbol_period), len(template))
            count = local_stop - local_start
            start = frame_start + local_start
            if count < 2 or start < 0 or start + count > len(values):
                complete = False
                break
            indexes = np.arange(start, start + count, dtype=float)
            local = template[local_start:local_stop]
            corrected = values[start : start + count] * np.exp(
                -2j * np.pi * cfo_hz * indexes / sample_rate_hz
            )
            correlation = complex(np.vdot(local, corrected))
            denominator = float(np.vdot(local, local).real * np.vdot(corrected, corrected).real)
            row.append(correlation)
            row_power.append(abs(correlation) ** 2 / max(denominator, 1e-20))
            row_moments.append((start + (count - 1) / 2) / sample_rate_hz)
        if not complete:
            break
        rows.append(row)
        powers.append(row_power)
        moments.append(row_moments)
        frame += 1
    shape = (len(rows), len(chosen))
    return SymbolCorrelations(
        np.asarray(rows, np.complex128) if rows else np.zeros(shape, np.complex128),
        np.asarray(powers, float) if rows else np.zeros(shape, float),
        np.asarray(moments, float) if rows else np.zeros(shape, float),
    )


def _coherent_ceiling(values: np.ndarray) -> float:
    if not values.size:
        return 0.0
    return float(np.sum(np.sum(np.abs(values), axis=1) ** 2))


def _anchor_score(correlations: SymbolCorrelations) -> float:
    ceiling = _coherent_ceiling(correlations.values)
    power = float(np.sum(np.abs(np.sum(correlations.values, axis=1)) ** 2))
    return power / ceiling if ceiling > 0 else 0.0


def _differential(correlations: SymbolCorrelations) -> tuple[float, float]:
    leading = correlations.values[:, 1:]
    trailing = correlations.values[:, :-1]
    products = leading * np.conj(trailing)
    total = complex(np.sum(products))
    weight = float(np.sum(np.abs(leading) * np.abs(trailing)))
    residual = (
        float(np.angle(total) / (2 * np.pi * correlations.symbol_step_s)) if total != 0 else 0.0
    )
    return (abs(total) / weight if weight > 0 else 0.0, residual)


def _frame_spectrum(correlations: SymbolCorrelations) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate the 512-bin per-frame GLRT over one symbol-rate period."""

    if not correlations.values.size:
        return np.zeros(GLRT_SIZE), np.fft.fftfreq(GLRT_SIZE, d=OFDM_SYMBOL_DURATION_S)
    grid = np.fft.fftfreq(GLRT_SIZE, d=correlations.symbol_step_s)
    lags = correlations.times_s - correlations.times_s[:, :1]
    phase = np.exp(-2j * np.pi * grid[:, None, None] * lags[None, :, :])
    spectrum = np.sum(np.abs(np.sum(correlations.values[None, :, :] * phase, axis=2)) ** 2, axis=1)
    ceiling = _coherent_ceiling(correlations.values)
    return (spectrum / ceiling if ceiling > 0 else spectrum, grid)


def _glrt(correlations: SymbolCorrelations) -> tuple[float, float]:
    spectrum, grid = _frame_spectrum(correlations)
    best = int(np.argmax(spectrum)) if spectrum.size else 0
    return float(spectrum[best]), float(grid[best])


def _edge_tracker(correlations: SymbolCorrelations) -> tuple[float, float]:
    score = (
        float(np.mean(correlations.normalized_power)) if correlations.normalized_power.size else 0.0
    )
    values = correlations.values.ravel()
    coherence = (
        float(abs(np.sum(values)) / max(float(np.sum(np.abs(values))), 1e-20))
        if values.size
        else 0.0
    )
    return score, coherence


def _metric_for_probe(
    probe: AcquiredProbe,
    samples: np.ndarray,
    sample_rate_hz: int,
    edge: StarlinkEdge,
) -> MethodMetric:
    empty = {
        field.name: None
        for field in fields(MethodMetric)
        if field.name
        not in {"index", "time_s", "sample_start", "symbolwise_margin", "qam_accuracy"}
    }
    if probe.candidate_epoch_sample is None or probe.baseband_cfo_hz is None:
        return MethodMetric(
            index=probe.index,
            time_s=probe.time_s,
            sample_start=probe.sample_start,
            symbolwise_margin=probe.pilot_margin,
            qam_accuracy=probe.qam_accuracy,
            **empty,
        )
    anchors = np.unique(np.rint(np.linspace(2, 301, 8)).astype(int))
    requested = {
        "anchor8": anchors,
        "differential16": np.arange(2, 18),
        "differential32": np.arange(2, 34),
        "glrt32": np.arange(2, 34),
        "glrt64": np.arange(2, 66),
        "edge_tracker": np.arange(2, 302),
    }
    exact = {
        name: _symbol_correlations(
            samples,
            sample_rate_hz,
            probe.candidate_epoch_sample,
            probe.baseband_cfo_hz,
            symbols,
            symbol_roll=0,
            edge=edge,
        )
        for name, symbols in requested.items()
    }
    control = {
        name: _symbol_correlations(
            samples,
            sample_rate_hz,
            probe.candidate_epoch_sample,
            probe.baseband_cfo_hz,
            symbols,
            symbol_roll=CONTROL_SYMBOL_ROLL,
            edge=edge,
        )
        for name, symbols in requested.items()
    }
    anchor_exact = _anchor_score(exact["anchor8"])
    anchor_control = _anchor_score(control["anchor8"])
    d16_exact, d16_cfo = _differential(exact["differential16"])
    d16_control, _ = _differential(control["differential16"])
    d32_exact, d32_cfo = _differential(exact["differential32"])
    d32_control, _ = _differential(control["differential32"])
    g32_exact, g32_cfo = _glrt(exact["glrt32"])
    g32_control, _ = _glrt(control["glrt32"])
    g64_exact, g64_cfo = _glrt(exact["glrt64"])
    g64_control, _ = _glrt(control["glrt64"])
    tracker_exact, tracker_coherence = _edge_tracker(exact["edge_tracker"])
    tracker_control, tracker_control_coherence = _edge_tracker(control["edge_tracker"])
    return MethodMetric(
        index=probe.index,
        time_s=probe.time_s,
        sample_start=probe.sample_start,
        acquired_epoch_sample=probe.candidate_epoch_sample,
        acquired_cfo_hz=probe.baseband_cfo_hz,
        anchor8_score=anchor_exact,
        anchor8_control_score=anchor_control,
        anchor8_margin=anchor_exact - anchor_control,
        differential16_score=d16_exact,
        differential16_control_score=d16_control,
        differential16_margin=d16_exact - d16_control,
        differential16_residual_cfo_hz=d16_cfo,
        differential32_score=d32_exact,
        differential32_control_score=d32_control,
        differential32_margin=d32_exact - d32_control,
        differential32_residual_cfo_hz=d32_cfo,
        glrt32_score=g32_exact,
        glrt32_control_score=g32_control,
        glrt32_margin=g32_exact - g32_control,
        glrt32_residual_cfo_hz=g32_cfo,
        glrt64_score=g64_exact,
        glrt64_control_score=g64_control,
        glrt64_margin=g64_exact - g64_control,
        glrt64_residual_cfo_hz=g64_cfo,
        edge_tracker_score=tracker_exact,
        edge_tracker_control_score=tracker_control,
        edge_tracker_margin=tracker_exact - tracker_control,
        edge_tracker_coherence=tracker_coherence,
        edge_tracker_control_coherence=tracker_control_coherence,
        symbolwise_margin=probe.pilot_margin,
        qam_accuracy=probe.qam_accuracy,
    )


def _analyze_batch(
    request: tuple[tuple[AcquiredProbe, ...], np.ndarray, int, StarlinkEdge],
) -> tuple[MethodMetric, ...]:
    probes, outer, sample_rate_hz, edge = request
    outer_start = probes[0].sample_start - probes[0].subwindow_index * round(0.05 * sample_rate_hz)
    probe_samples = round(0.020 * sample_rate_hz)
    return tuple(
        _metric_for_probe(
            probe,
            np.ascontiguousarray(
                outer[
                    probe.sample_start - outer_start : probe.sample_start
                    - outer_start
                    + probe_samples
                ]
            ),
            sample_rate_hz,
            edge,
        )
        for probe in probes
    )


def _write_csv(path: Path, metrics: tuple[MethodMetric, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=[field.name for field in fields(MethodMetric)])
        writer.writeheader()
        for metric in metrics:
            writer.writerow(asdict(metric))


def _finite(metrics: tuple[MethodMetric, ...], name: str) -> np.ndarray:
    return np.asarray(
        [math.nan if getattr(item, name) is None else getattr(item, name) for item in metrics],
        float,
    )


def _track_components(
    times_s: np.ndarray,
    cfo_hz: np.ndarray,
    selected: np.ndarray,
    *,
    maximum_time_gap_s: float = 0.15,
    maximum_cfo_jump_hz: float = 30_000.0,
) -> tuple[np.ndarray, ...]:
    """Split accepted points instead of fitting unrelated CFO branches together."""

    indexes = np.flatnonzero(selected & np.isfinite(times_s) & np.isfinite(cfo_hz))
    if not indexes.size:
        return ()
    groups: list[list[int]] = [[int(indexes[0])]]
    for index in indexes[1:]:
        previous = groups[-1][-1]
        if (
            times_s[index] - times_s[previous] <= maximum_time_gap_s
            and abs(cfo_hz[index] - cfo_hz[previous]) <= maximum_cfo_jump_hz
        ):
            groups[-1].append(int(index))
        else:
            groups.append([int(index)])
    return tuple(np.asarray(group, dtype=int) for group in groups)


def _render_method(
    path: Path, metrics: tuple[MethodMetric, ...], field: str, title: str, color: str
) -> None:
    import matplotlib.pyplot as plt

    time = _finite(metrics, "time_s")
    value = _finite(metrics, field)
    qam = _finite(metrics, "qam_accuracy")
    strong = (qam >= 0.60) & (_finite(metrics, "symbolwise_margin") >= 0.05)
    figure, axis = plt.subplots(figsize=(15, 4), constrained_layout=True)
    axis.plot(time, value, color=color, linewidth=0.75, alpha=0.8)
    axis.scatter(time[~strong], value[~strong], s=7, color=color, alpha=0.35)
    axis.scatter(
        time[strong],
        value[strong],
        s=12,
        color="#00a878",
        alpha=0.9,
        label="symbolwise/QAM-positive probe",
    )
    axis.axhline(0, color="black", linewidth=0.6, alpha=0.6)
    axis.set(
        xlabel="Elapsed recording time (s)", ylabel="Exact − rolled-control score", title=title
    )
    axis.grid(alpha=0.2)
    axis.legend(loc="upper right")
    figure.savefig(path, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _render(output: Path, metrics: tuple[MethodMetric, ...], title: str) -> tuple[Path, ...]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    methods = (
        ("anchor8_margin", "Anchor-8 conditioned phase margin", "#6d597a"),
        ("differential16_margin", "Adjacent differential-16 margin", "#b56576"),
        ("differential32_margin", "Adjacent differential-32 margin", "#e56b6f"),
        ("glrt32_margin", "GLRT-32 searched residual-CFO margin", "#355070"),
        ("glrt64_margin", "GLRT-64 searched residual-CFO margin", "#1d4e89"),
        ("edge_tracker_margin", "Legacy edge-pilot noncoherent margin", "#2a9d8f"),
        ("symbolwise_margin", "Current full-frame symbolwise margin", "#f4a261"),
        ("qam_accuracy", "Known-symbol QAM hard-symbol accuracy", "#00a878"),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    times = _finite(metrics, "time_s")
    figure, axes = plt.subplots(4, 2, figsize=(16, 14), sharex=True, constrained_layout=True)
    paths: list[Path] = []
    for axis, (field, label, color) in zip(axes.ravel(), methods, strict=True):
        values = _finite(metrics, field)
        axis.plot(times, values, color=color, linewidth=0.7)
        axis.axhline(0, color="black", linewidth=0.5, alpha=0.5)
        axis.set_ylabel(label)
        axis.grid(alpha=0.2)
        if field == "qam_accuracy":
            axis.set_ylim(0, 1.02)
        individual = output.with_name(f"{output.stem}-{field.replace('_margin', '')}.png")
        if field == "qam_accuracy":
            single_title = label
            # The single QAM plot is an accuracy, not an exact-control margin.
            fig, one = plt.subplots(figsize=(15, 4), constrained_layout=True)
            one.plot(times, values, color=color, linewidth=0.75)
            one.set(
                xlabel="Elapsed recording time (s)",
                ylabel="Hard-symbol accuracy",
                title=single_title,
            )
            one.set_ylim(0, 1.02)
            one.grid(alpha=0.2)
            fig.savefig(individual, dpi=160, metadata={"Software": "leo-tracker"})
            plt.close(fig)
        else:
            _render_method(individual, metrics, field, label, color)
        paths.append(individual)
    for axis in axes[-1]:
        axis.set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        f"{title}\nSame 20 ms probes and acquired epoch/CFO · exact Qin pilot vs roll-17 control",
        fontsize=12,
        fontweight="bold",
    )
    figure.savefig(output, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(figure)

    cfo_path = output.with_name(f"{output.stem}-cfo-track.png")
    cfo = _finite(metrics, "acquired_cfo_hz")
    qam = _finite(metrics, "qam_accuracy")
    good = (qam >= 0.60) & (_finite(metrics, "symbolwise_margin") >= 0.05) & np.isfinite(cfo)
    fig, axis = plt.subplots(figsize=(15, 4.5), constrained_layout=True)
    axis.scatter(
        times[~good],
        cfo[~good] / 1000,
        s=6,
        color="#999999",
        alpha=0.2,
        label="all acquired probes",
    )
    axis.scatter(
        times[good], cfo[good] / 1000, s=14, color="#00a878", alpha=0.85, label="pilot/QAM-positive"
    )
    fitted = False
    for component in _track_components(times, cfo, good):
        if len(component) < 5:
            continue
        degree = min(2, len(component) - 1)
        coefficients = np.polyfit(times[component], cfo[component], degree)
        grid = np.linspace(float(times[component].min()), float(times[component].max()), 200)
        axis.plot(
            grid,
            np.polyval(coefficients, grid) / 1000,
            color="#d1495b",
            linewidth=1.5,
            label=None if fitted else "separate contiguous Doppler fits",
        )
        fitted = True
    axis.set(
        xlabel="Elapsed recording time (s)",
        ylabel="Acquired baseband CFO (kHz)",
        title="Across-time candidate CFO / Doppler linking input",
    )
    axis.grid(alpha=0.2)
    axis.legend(loc="best")
    fig.savefig(cfo_path, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(fig)
    paths.append(cfo_path)
    return tuple(paths)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    args = _arguments()
    if args.workers < 1 or args.workers > 16:
        raise ValueError("workers must lie in 1..16")
    probes = _load_timeline(args.timeline_csv)
    edge = StarlinkEdge(args.edge)
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        store.verify(bundle)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError(f"stream has no receiver {args.receiver}")
        expected_probe_samples = args.probe_ms * reader.sample_rate_hz / 1000
        if not expected_probe_samples.is_integer():
            raise ValueError("probe duration does not map to integral samples")
        by_outer: dict[int, list[AcquiredProbe]] = {}
        for probe in probes:
            by_outer.setdefault(probe.outer_chunk_index, []).append(probe)
        print(
            f"verified {args.session_id}; comparing {len(probes)} probes "
            f"with {args.workers} workers",
            flush=True,
        )
        collected: list[MethodMetric] = []
        pending: set[Future[tuple[MethodMetric, ...]]] = set()
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for group in by_outer.values():
                outer_start = min(item.sample_start for item in group)
                outer_stop = max(item.sample_start for item in group) + int(expected_probe_samples)
                outer = _complex_receiver(
                    reader.read(
                        outer_start,
                        outer_stop - outer_start,
                        receiver_ids=(args.receiver,),
                    )
                )
                pending.add(
                    executor.submit(
                        _analyze_batch,
                        (tuple(group), outer, reader.sample_rate_hz, edge),
                    )
                )
                if len(pending) >= args.workers * 2:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        collected.extend(future.result())
            while pending:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    collected.extend(future.result())
        metrics = tuple(sorted(collected, key=lambda item: item.index))
        if len(metrics) != len(probes):
            raise RuntimeError("method result count differs from input timeline")
        plots = _render(
            args.output, metrics, f"{args.session_id} · {args.stream} · RX{args.receiver}"
        )
        csv_path = args.output.with_suffix(".csv")
        _write_csv(csv_path, metrics)
        document = {
            "session_id": args.session_id,
            "manifest_digest": bundle.manifest_sha256,
            "stream_id": args.stream,
            "receiver_id": args.receiver,
            "edge": edge.value,
            "probe_count": len(metrics),
            "workers": args.workers,
            "conditioning": "common acquired epoch and coarse CFO from input symbolwise timeline",
            "control": f"Qin pilot sequence rolled by {CONTROL_SYMBOL_ROLL} symbols",
            "candidate_only": True,
            "payload_decoded": False,
            "input_timeline_csv": str(args.timeline_csv.resolve()),
            "input_timeline_sha256": _sha256(args.timeline_csv),
            "csv": str(csv_path.resolve()),
            "csv_sha256": _sha256(csv_path),
            "plots": [
                {"path": str(path.resolve()), "sha256": _sha256(path)}
                for path in (args.output, *plots)
            ],
        }
        metadata = args.output.with_suffix(".json")
        metadata.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({**document, "metadata": str(metadata.resolve())}))
        return 0
    finally:
        if store is not None:
            store.close()
        pinned.close()


if __name__ == "__main__":
    raise SystemExit(main())
