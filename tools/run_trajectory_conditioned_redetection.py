#!/usr/bin/env python3
"""Build an all-method trajectory bank, dechirp IQ, and redetect every method."""

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

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotProbeDetection,
    detect_pilot_methods,
)
from leo.analysis.starlink.trajectories import (
    TrajectoryObservation,
    correct_polynomial_cfo,
    default_trajectory_bank_config,
    fit_trajectory_bank,
)
from leo.contracts.digests import canonical_digest
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_SESSION = "production-24h-20260819-01-trial-00000132"
DEFAULT_INPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.csv"
)
DEFAULT_OUTPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-"
    "trajectory-redetection.png"
)

_FIELDS = {
    PilotMethod.ANCHOR8: (
        "anchor8_score",
        "anchor8_control_score",
        "anchor8_margin",
        None,
    ),
    PilotMethod.DIFFERENTIAL16: (
        "differential16_score",
        "differential16_control_score",
        "differential16_margin",
        "differential16_residual_cfo_hz",
    ),
    PilotMethod.DIFFERENTIAL32: (
        "differential32_score",
        "differential32_control_score",
        "differential32_margin",
        "differential32_residual_cfo_hz",
    ),
    PilotMethod.GLRT32: (
        "glrt32_score",
        "glrt32_control_score",
        "glrt32_margin",
        "glrt32_residual_cfo_hz",
    ),
    PilotMethod.GLRT64: (
        "glrt64_score",
        "glrt64_control_score",
        "glrt64_margin",
        "glrt64_residual_cfo_hz",
    ),
    PilotMethod.EDGE_TRACKER: (
        "edge_tracker_score",
        "edge_tracker_control_score",
        "edge_tracker_margin",
        None,
    ),
    PilotMethod.SYMBOLWISE: (
        "symbolwise_margin",
        None,
        "symbolwise_margin",
        None,
    ),
    PilotMethod.QAM_ACCURACY: (
        "qam_accuracy",
        None,
        "qam_accuracy",
        None,
    ),
}


@dataclass(frozen=True, slots=True)
class CorrectedProbe:
    family_id: str
    trajectory_id: str
    probe_index: int
    detection: PilotProbeDetection


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", nargs="?", default=DEFAULT_SESSION)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument("--probe-ms", type=float, default=20.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--maximum-families", type=int, default=16)
    return parser.parse_args()


def _observations(rows: tuple[dict[str, str], ...]) -> tuple[TrajectoryObservation, ...]:
    result = []
    for row in rows:
        acquired_text = row.get("acquired_cfo_hz", "")
        if not acquired_text:
            continue
        acquired = float(acquired_text)
        for method, (score_field, control_field, margin_field, residual_field) in _FIELDS.items():
            if not row.get(score_field) or not row.get(margin_field):
                continue
            residual = float(row[residual_field]) if residual_field else 0.0
            result.append(
                TrajectoryObservation(
                    canonical_digest({"method": method.value, "index": int(row["index"])}),
                    method,
                    int(row["sample_start"]),
                    float(row["time_s"]),
                    acquired + residual,
                    float(row[score_field]),
                    float(row[control_field]) if control_field else None,
                    float(row[margin_field]),
                )
            )
    return tuple(result)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (
        values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)
    ) / 32_768.0


def _redetect_batch(request):
    (
        family_id,
        trajectory,
        probes,
        outer_start,
        outer,
        sample_rate_hz,
        probe_samples,
    ) = request
    calibration = ReceiverFrequencyCalibration(
        "trajectory-corrected",
        0.0,
        canonical_digest(
            {
                "trajectory_id": trajectory.trajectory_id,
                "baseband_center_hz": 0.0,
            }
        ).removeprefix("sha256:"),
    )
    config = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-20_000.0,
        residual_cfo_max_hz=20_000.0,
        coarse_cfo_step_hz=10_000.0,
        fine_cfo_radius_hz=20_000.0,
        retained_candidate_count=2,
        maximum_probe_samples=probe_samples,
    )
    result = []
    for probe_index, sample_start in probes:
        relative = sample_start - outer_start
        samples = np.ascontiguousarray(outer[relative : relative + probe_samples])
        corrected = correct_polynomial_cfo(
            samples,
            sample_rate_hz,
            sample_start,
            trajectory,
        )
        result.append(
            CorrectedProbe(
                family_id,
                trajectory.trajectory_id,
                probe_index,
                detect_pilot_methods(
                    corrected,
                    sample_rate_hz,
                    sample_start=sample_start,
                    calibration=calibration,
                    acquisition_config=config,
                ),
            )
        )
    return tuple(result)


def _method_threshold(rows: tuple[dict[str, str], ...], method: PilotMethod) -> float:
    if method is PilotMethod.QAM_ACCURACY:
        return 0.60
    margin_field = _FIELDS[method][2]
    negative = np.abs(
        np.asarray(
            [
                float(row[margin_field])
                for row in rows
                if row.get(margin_field) and float(row[margin_field]) < 0
            ]
        )
    )
    if not len(negative):
        return math.inf
    return float(np.median(negative) / 0.6744897501960817 * 5.0)


def _summary(
    rows: tuple[dict[str, str], ...],
    corrected: tuple[CorrectedProbe, ...],
    family_ids: tuple[str, ...],
):
    by_index = {int(row["index"]): row for row in rows}
    result = []
    for family_id in family_ids:
        family = tuple(item for item in corrected if item.family_id == family_id)
        for method in PilotMethod:
            baseline = []
            redetected = []
            margin_field = _FIELDS[method][2]
            for item in family:
                row = by_index[item.probe_index]
                score = next(
                    (value for value in item.detection.scores if value.method is method),
                    None,
                )
                if score is not None and row.get(margin_field):
                    baseline.append(float(row[margin_field]))
                    redetected.append(score.margin)
            threshold = _method_threshold(rows, method)
            count = min(len(baseline), len(redetected))
            baseline_values = np.asarray(baseline[:count], dtype=float)
            corrected_values = np.asarray(redetected[:count], dtype=float)
            result.append(
                {
                    "family_id": family_id,
                    "method": method.value,
                    "paired_probe_count": count,
                    "threshold": threshold,
                    "baseline_median": (
                        float(np.median(baseline_values)) if count else None
                    ),
                    "corrected_median": (
                        float(np.median(corrected_values)) if count else None
                    ),
                    "median_delta": (
                        float(np.median(corrected_values - baseline_values)) if count else None
                    ),
                    "baseline_positive_count": int(np.count_nonzero(baseline_values >= threshold)),
                    "corrected_positive_count": int(
                        np.count_nonzero(corrected_values >= threshold)
                    ),
                }
            )
    return tuple(result)


def _render(path: Path, summaries, labels: dict[str, str]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "run with: uv run --with 'matplotlib>=3.10,<4' python "
            "tools/run_trajectory_conditioned_redetection.py"
        ) from error
    methods = tuple(PilotMethod)
    families = tuple(labels)
    margin = np.full((len(families), len(methods)), np.nan)
    counts = np.full((len(families), len(methods)), np.nan)
    lookup = {(item["family_id"], item["method"]): item for item in summaries}
    for row_index, family_id in enumerate(families):
        for column_index, method in enumerate(methods):
            item = lookup[(family_id, method.value)]
            margin[row_index, column_index] = item["median_delta"]
            counts[row_index, column_index] = (
                item["corrected_positive_count"] - item["baseline_positive_count"]
            )
    figure, axes = plt.subplots(2, 1, figsize=(15, 8), constrained_layout=True)
    for axis, values, title, color_label, cmap in (
        (axes[0], margin, "Median corrected − baseline metric", "metric delta", "RdYlGn"),
        (
            axes[1],
            counts,
            "Change in above-threshold probe count",
            "count delta",
            "PiYG",
        ),
    ):
        limit = max(float(np.nanmax(np.abs(values))), np.finfo(float).eps)
        image = axis.imshow(values, aspect="auto", cmap=cmap, vmin=-limit, vmax=limit)
        axis.set_xticks(range(len(methods)), [method.value for method in methods], rotation=30)
        axis.set_yticks(range(len(families)), [labels[item] for item in families])
        axis.set_title(title, loc="left", fontweight="bold")
        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                axis.text(
                    column,
                    row,
                    (
                        f"{values[row, column]:+.3f}"
                        if axis is axes[0]
                        else f"{values[row, column]:+.0f}"
                    ),
                    ha="center",
                    va="center",
                    fontsize=8,
                )
        figure.colorbar(image, ax=axis, label=color_label)
    figure.suptitle(
        "Trajectory-conditioned detector replay · candidate-only · same IQ controls",
        fontweight="bold",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    args = _arguments()
    if not 1 <= args.workers <= 16 or not 1 <= args.maximum_families <= 64:
        raise ValueError("worker and family bounds are invalid")
    with args.input.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    bank_config = default_trajectory_bank_config()
    bank = fit_trajectory_bank(_observations(rows), bank_config)
    by_trajectory = {item.trajectory_id: item for item in bank.trajectories}
    families = bank.families[: args.maximum_families]
    representatives = tuple(
        (family, by_trajectory[family.representative_trajectory_id]) for family in families
    )
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    corrected: list[CorrectedProbe] = []
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        store.verify(bundle)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError(f"stream has no receiver {args.receiver}")
        probe_samples_float = args.probe_ms * reader.sample_rate_hz / 1_000
        if not probe_samples_float.is_integer():
            raise ValueError("probe duration does not map to integral samples")
        probe_samples = int(probe_samples_float)
        pending: set[Future[tuple[CorrectedProbe, ...]]] = set()
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for family, trajectory in representatives:
                selected = tuple(
                    row
                    for row in rows
                    if trajectory.start_s <= float(row["time_s"]) <= trajectory.end_s
                )
                by_second: dict[int, list[dict[str, str]]] = {}
                for row in selected:
                    by_second.setdefault(int(float(row["time_s"])), []).append(row)
                for group in by_second.values():
                    outer_start = min(int(row["sample_start"]) for row in group)
                    outer_stop = max(int(row["sample_start"]) for row in group) + probe_samples
                    outer = _complex_receiver(
                        reader.read(
                            outer_start,
                            outer_stop - outer_start,
                            receiver_ids=(args.receiver,),
                        )
                    )
                    pending.add(
                        executor.submit(
                            _redetect_batch,
                            (
                                family.family_id,
                                trajectory,
                                tuple(
                                    (int(row["index"]), int(row["sample_start"]))
                                    for row in group
                                ),
                                outer_start,
                                outer,
                                reader.sample_rate_hz,
                                probe_samples,
                            ),
                        )
                    )
                    if len(pending) >= args.workers * 2:
                        finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                        for future in finished:
                            corrected.extend(future.result())
            while pending:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    corrected.extend(future.result())
        corrected_tuple = tuple(
            sorted(corrected, key=lambda item: (item.family_id, item.probe_index))
        )
        family_ids = tuple(family.family_id for family in families)
        summaries = _summary(rows, corrected_tuple, family_ids)
        labels = {
            family.family_id: (
                f"{trajectory.method.value} d{trajectory.polynomial_degree} "
                f"{trajectory.start_s:.1f}–{trajectory.end_s:.1f}s"
            )
            for family, trajectory in representatives
        }
        _render(args.output, summaries, labels)
        document = {
            "session_id": args.session_id,
            "stream_id": args.stream,
            "receiver_id": args.receiver,
            "manifest_digest": bundle.manifest_sha256,
            "input": str(args.input.resolve()),
            "input_sha256": _sha256(args.input),
            "trajectory_bank_config_digest": bank.config_digest,
            "trajectory_count": len(bank.trajectories),
            "family_count": len(bank.families),
            "replayed_family_count": len(families),
            "probe_result_count": len(corrected_tuple),
            "candidate_only": True,
            "payload_decoded": False,
            "families": [asdict(item) for item in families],
            "representatives": [asdict(item) for _, item in representatives],
            "summaries": summaries,
            "png": str(args.output.resolve()),
            "png_sha256": _sha256(args.output),
        }
        metadata = args.output.with_suffix(".json")
        metadata.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "png": str(args.output.resolve()),
                    "metadata": str(metadata.resolve()),
                    "trajectory_count": len(bank.trajectories),
                    "family_count": len(bank.families),
                    "probe_result_count": len(corrected_tuple),
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
