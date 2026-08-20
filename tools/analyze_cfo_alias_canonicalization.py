#!/usr/bin/env python3
"""Evaluate symbol-rate CFO alias canonicalization on recorded GLRT64 evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.cfo_aliases import (
    CfoAliasFit,
    CfoAliasObservation,
    select_cfo_alias_degree,
)
from leo.analysis.starlink.pilot_methods import PilotMethod, detect_pilot_methods
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S
from leo.analysis.starlink.trajectories import PolynomialTrajectory, correct_polynomial_cfo
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--trajectory-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--start-s", type=float, default=0.0)
    parser.add_argument("--end-s", type=float, default=10.0)
    parser.add_argument("--residual-gate-hz", type=float, default=2_500.0)
    parser.add_argument("--bulk-root", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument("--edge", choices=("lower", "upper"))
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _load_rows(path: Path) -> tuple[dict[str, str], ...]:
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    if not rows:
        raise ValueError("CFO alias input CSV is empty")
    return rows


def _high_gate(document: dict[str, Any]) -> float:
    values = {
        float(item["high_gate"])
        for item in document["glrt64_trajectory_table"]
        if item.get("high_gate") is not None
    }
    if len(values) != 1:
        raise ValueError("trajectory document does not carry one exact GLRT64 high gate")
    return values.pop()


def _observations(
    rows: tuple[dict[str, str], ...],
    *,
    start_s: float,
    end_s: float,
    high_gate: float,
) -> tuple[CfoAliasObservation, ...]:
    result = []
    for row in rows:
        time_s = float(row["time_s"])
        margin = float(row["glrt64_margin"])
        if not start_s <= time_s <= end_s or margin < high_gate:
            continue
        raw_cfo_hz = float(row["acquired_cfo_hz"]) + float(row["glrt64_residual_cfo_hz"])
        result.append(
            CfoAliasObservation(
                f"probe-{int(row['index']):04d}",
                time_s,
                raw_cfo_hz,
                max(margin, np.finfo(float).eps),
            )
        )
    return tuple(result)


def _branch_comparison(
    observations: tuple[CfoAliasObservation, ...], fit: CfoAliasFit
) -> dict[str, Any]:
    ordered = tuple(sorted(observations, key=lambda item: (item.time_s, item.observation_id)))
    time_s = np.asarray([item.time_s for item in ordered], dtype=float)
    canonical = np.asarray(fit.canonical_cfo_hz, dtype=float)
    alias = np.asarray(fit.alias_indices, dtype=int)
    retained = np.asarray(fit.retained, dtype=bool)
    weights = np.asarray([item.weight for item in ordered], dtype=float)
    branches = tuple(int(value) for value in sorted(set(alias[retained])))
    if len(branches) != 2:
        raise ValueError("focused report expects exactly two retained alias branches")
    branch_rows = []
    total_rss = 0.0
    held_out_residuals: list[float] = []
    bin_index = np.floor((time_s - float(np.min(time_s))) / 0.25).astype(int)
    for branch in branches:
        selected = retained & (alias == branch)
        coefficients = np.polyfit(
            time_s[selected], canonical[selected], 2, w=np.sqrt(weights[selected])
        )
        residual = canonical[selected] - np.polyval(coefficients, time_s[selected])
        rss = float(np.sum(weights[selected] * residual**2))
        total_rss += rss
        for fold in range(5):
            train = selected & (bin_index % 5 != fold)
            test = selected & (bin_index % 5 == fold)
            if np.count_nonzero(test) == 0:
                continue
            fold_coefficients = np.polyfit(
                time_s[train], canonical[train], 2, w=np.sqrt(weights[train])
            )
            held_out_residuals.extend(
                (canonical[test] - np.polyval(fold_coefficients, time_s[test])).tolist()
            )
        branch_rows.append(
            {
                "alias_index": branch,
                "point_count": int(np.count_nonzero(selected)),
                "coefficients_hz": [float(value) for value in coefficients],
                "residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
            }
        )
    point_count = int(np.count_nonzero(retained))
    bic = float(point_count * math.log(total_rss / point_count) + 6 * math.log(point_count))
    held_out_rms = float(np.sqrt(np.mean(np.asarray(held_out_residuals, dtype=float) ** 2)))
    return {
        "branches": branch_rows,
        "bic": bic,
        "held_out_rms_hz": held_out_rms,
        "bic_delta_vs_one_canonical": bic - fit.bic,
        "held_out_rms_delta_vs_one_canonical_hz": held_out_rms - fit.held_out_rms_hz,
    }


def _render_alias_figure(
    path: Path,
    observations: tuple[CfoAliasObservation, ...],
    fit: CfoAliasFit,
    branch_comparison: dict[str, Any],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ordered = tuple(sorted(observations, key=lambda item: (item.time_s, item.observation_id)))
    time_s = np.asarray([item.time_s for item in ordered], dtype=float)
    raw = np.asarray([item.raw_cfo_hz for item in ordered], dtype=float)
    canonical = np.asarray(fit.canonical_cfo_hz, dtype=float)
    alias = np.asarray(fit.alias_indices, dtype=int)
    retained = np.asarray(fit.retained, dtype=bool)
    dense = np.linspace(float(np.min(time_s)), float(np.max(time_s)), 600)
    figure, axes = plt.subplots(3, 1, figsize=(15, 12), sharex=True, constrained_layout=True)
    colors = {0: "#2878b5", 1: "#f47b20"}
    for branch in sorted(set(alias[retained])):
        selected = retained & (alias == branch)
        axes[0].scatter(
            time_s[selected],
            raw[selected] / 1_000,
            s=15,
            alpha=0.65,
            color=colors.get(int(branch), "#667085"),
            label=f"raw alias n={branch} ({np.count_nonzero(selected)} probes)",
        )
        axes[1].scatter(
            time_s[selected],
            canonical[selected] / 1_000,
            s=15,
            alpha=0.65,
            color=colors.get(int(branch), "#667085"),
            label=f"canonicalized from n={branch}",
        )
        axes[2].scatter(
            time_s[selected],
            np.asarray(fit.residual_hz)[selected],
            s=13,
            alpha=0.6,
            color=colors.get(int(branch), "#667085"),
            label=f"n={branch}",
        )
    rejected = ~retained
    if np.any(rejected):
        axes[0].scatter(time_s[rejected], raw[rejected] / 1_000, marker="x", color="black")
    canonical_curve = fit.frequency_hz(dense)
    axes[1].plot(
        dense,
        canonical_curve / 1_000,
        color="black",
        linewidth=2.0,
        label=f"one canonical quadratic · RMS {fit.residual_rms_hz:.1f} Hz",
    )
    for branch_row in branch_comparison["branches"]:
        raw_curve = np.polyval(branch_row["coefficients_hz"], dense)
        alias_index = int(branch_row["alias_index"])
        axes[0].plot(
            dense,
            (raw_curve + alias_index * fit.alias_spacing_hz) / 1_000,
            color=colors[alias_index],
            linewidth=2.0,
        )
    axes[2].axhline(0.0, color="black", linewidth=1.0)
    axes[2].axhline(2_500.0, color="#b54708", linestyle="--", linewidth=0.9)
    axes[2].axhline(-2_500.0, color="#b54708", linestyle="--", linewidth=0.9)
    axes[0].set_ylabel("Raw GLRT64 CFO (kHz)")
    axes[1].set_ylabel("Canonical CFO (kHz)")
    axes[2].set_ylabel("One-track residual (Hz)")
    axes[2].set_xlabel("Recording time (s)")
    axes[0].set_title("Raw CFO: two apparent branches separated by one symbol rate", loc="left")
    axes[1].set_title("Alias canonicalization: both branches collapse", loc="left")
    axes[2].set_title("Residuals retain no separate smooth branch", loc="left")
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.legend(loc="best", fontsize=8)
    figure.suptitle(
        "Standard 2×20 ms / 50 ms · 0–10 s GLRT64 CFO alias analysis\n"
        "candidate-only · raw CFO preserved · Δalias = 1 / 4.4 µs",
        fontweight="bold",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _trajectory(
    name: str, fit: CfoAliasFit, constant_shift_hz: float = 0.0
) -> PolynomialTrajectory:
    coefficients = list(fit.coefficients_hz)
    coefficients[-1] += constant_shift_hz
    retained = [
        observation_id
        for observation_id, keep in zip(fit.observation_ids, fit.retained, strict=True)
        if keep
    ]
    return PolynomialTrajectory(
        canonical_digest({"name": name, "coefficients_hz": coefficients}),
        PilotMethod.GLRT64,
        fit.polynomial_degree,
        0.0,
        tuple(coefficients),
        0.0,
        10.0,
        tuple(retained),
        len(retained),
        fit.residual_rms_hz,
        fit.bic,
        0.0,
        fit.iterations,
    )


def _published_trajectory(document: dict[str, Any]) -> PolynomialTrajectory:
    item = document["representatives"][0]
    return PolynomialTrajectory(
        item["trajectory_id"],
        PilotMethod(item["method"]),
        int(item["polynomial_degree"]),
        float(item["reference_time_s"]),
        tuple(float(value) for value in item["coefficients_hz"]),
        float(item["start_s"]),
        float(item["end_s"]),
        tuple(str(value) for value in item["observation_ids"]),
        int(item["point_count"]),
        float(item["residual_rms_hz"]),
        float(item["bic"]),
        float(item["high_gate"]),
        int(item["em_iterations"]),
    )


def _replay(
    args: argparse.Namespace,
    rows: tuple[dict[str, str], ...],
    document: dict[str, Any],
    fit: CfoAliasFit,
) -> tuple[dict[str, Any], ...]:
    if not args.bulk_root or not args.session_id or not args.edge:
        return ()
    if not 1 <= args.workers <= 16:
        raise ValueError("replay workers must lie in 1..16")
    models = {
        "published_upper_cubic": _published_trajectory(document),
        "canonical_lower_quadratic": _trajectory("canonical-lower", fit),
        "canonical_plus_one_alias": _trajectory("canonical-plus-one", fit, fit.alias_spacing_hz),
    }
    selected_rows = tuple(row for row in rows if args.start_s <= float(row["time_s"]) <= args.end_s)
    calibration = ReceiverFrequencyCalibration(
        "alias-replay",
        0.0,
        canonical_digest({"source": "candidate-only-cfo-alias-replay"}).removeprefix("sha256:"),
    )
    acquisition = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-20_000.0,
        residual_cfo_max_hz=20_000.0,
        coarse_cfo_step_hz=10_000.0,
        fine_cfo_radius_hz=20_000.0,
        retained_candidate_count=2,
        maximum_probe_samples=50_000,
    )
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    results: list[dict[str, Any]] = [
        {
            "model": "recorded_uncorrected",
            "probe_index": int(row["index"]),
            "time_s": float(row["time_s"]),
            "glrt64_margin": float(row["glrt64_margin"]),
            "symbolwise_margin": float(row["symbolwise_margin"]),
            "qam_accuracy": float(row["qam_accuracy"]),
            "reacquired_cfo_hz": float(row["acquired_cfo_hz"]),
        }
        for row in selected_rows
    ]
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        store.verify(bundle)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError("requested replay receiver is absent")
        probe_samples = int(reader.sample_rate_hz * 0.020)
        by_second: dict[int, list[dict[str, str]]] = {}
        for row in selected_rows:
            by_second.setdefault(int(float(row["time_s"])), []).append(row)

        def analyze(request: tuple[str, PolynomialTrajectory, dict[str, str], np.ndarray]):
            model_name, trajectory, row, samples = request
            corrected = correct_polynomial_cfo(
                samples,
                reader.sample_rate_hz,
                int(row["sample_start"]),
                trajectory,
            )
            detection = detect_pilot_methods(
                corrected,
                reader.sample_rate_hz,
                sample_start=int(row["sample_start"]),
                calibration=calibration,
                acquisition_config=acquisition,
                edge=StarlinkEdge(args.edge),
            )
            scores = {score.method: score for score in detection.scores}
            return {
                "model": model_name,
                "probe_index": int(row["index"]),
                "time_s": float(row["time_s"]),
                "glrt64_margin": scores[PilotMethod.GLRT64].margin,
                "symbolwise_margin": scores[PilotMethod.SYMBOLWISE].margin,
                "qam_accuracy": scores[PilotMethod.QAM_ACCURACY].margin,
                "reacquired_cfo_hz": detection.acquired_cfo_hz,
            }

        requests: list[tuple[str, PolynomialTrajectory, dict[str, str], np.ndarray]] = []
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
            for row in group:
                relative = int(row["sample_start"]) - outer_start
                samples = np.ascontiguousarray(outer[relative : relative + probe_samples])
                requests.extend(
                    (name, trajectory, row, samples) for name, trajectory in models.items()
                )
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            results.extend(executor.map(analyze, requests))
    finally:
        if store is not None:
            store.close()
        pinned.close()
    return tuple(sorted(results, key=lambda item: (item["model"], item["probe_index"])))


def _replay_summary(records: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    result = []
    for model in sorted({str(item["model"]) for item in records}):
        selected = tuple(item for item in records if item["model"] == model)
        glrt = np.asarray([item["glrt64_margin"] for item in selected], dtype=float)
        symbolwise = np.asarray([item["symbolwise_margin"] for item in selected], dtype=float)
        qam = np.asarray([item["qam_accuracy"] for item in selected], dtype=float)
        result.append(
            {
                "model": model,
                "probe_count": len(selected),
                "glrt64_median_margin": float(np.median(glrt)),
                "glrt64_positive_count": int(np.count_nonzero(glrt >= 0.02368816028965054)),
                "symbolwise_median_margin": float(np.median(symbolwise)),
                "qam_median_accuracy": float(np.median(qam)),
                "qam_pilot_positive_count": int(
                    np.count_nonzero((qam >= 0.60) & (symbolwise >= 0.05))
                ),
            }
        )
    return tuple(result)


def _render_replay(path: Path, records: tuple[dict[str, Any], ...]) -> None:
    if not records:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fields = (
        ("glrt64_margin", "GLRT64 exact − control"),
        ("symbolwise_margin", "Symbolwise margin"),
        ("qam_accuracy", "Known-pilot QAM accuracy"),
    )
    models = tuple(sorted({str(item["model"]) for item in records}))
    colors = ("#2878b5", "#f47b20", "#2a9d8f", "#7f56d9")
    figure, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True, constrained_layout=True)
    for axis, (field, label) in zip(axes, fields, strict=True):
        for model, color in zip(models, colors, strict=True):
            selected = sorted(
                (item for item in records if item["model"] == model),
                key=lambda item: item["time_s"],
            )
            axis.plot(
                [item["time_s"] for item in selected],
                [item[field] for item in selected],
                linewidth=0.9,
                alpha=0.82,
                color=color,
                label=model.replace("_", " "),
            )
        axis.set_ylabel(label)
        axis.grid(alpha=0.18)
        axis.legend(loc="best", fontsize=8)
    axes[0].axhline(0.02368816028965054, color="black", linestyle="--", linewidth=0.8)
    axes[1].axhline(0.05, color="black", linestyle="--", linewidth=0.8)
    axes[2].axhline(0.60, color="black", linestyle="--", linewidth=0.8)
    axes[2].set_xlabel("Recording time (s)")
    figure.suptitle(
        "Same-IQ trajectory correction replay · Standard 2×20 ms / 50 ms · 0–10 s\n"
        "candidate-only · published upper alias vs canonical lower vs canonical + 1/Tsymbol",
        fontweight="bold",
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> int:
    args = _arguments()
    if not math.isfinite(args.start_s) or not math.isfinite(args.end_s):
        raise ValueError("analysis interval must be finite")
    if args.start_s < 0 or args.end_s <= args.start_s:
        raise ValueError("analysis interval is invalid")
    rows = _load_rows(args.input)
    document = json.loads(args.trajectory_json.read_text(encoding="utf-8"))
    high_gate = _high_gate(document)
    spacing = 1.0 / OFDM_SYMBOL_DURATION_S
    observations = _observations(
        rows,
        start_s=args.start_s,
        end_s=args.end_s,
        high_gate=high_gate,
    )
    selected, degree_fits = select_cfo_alias_degree(
        observations,
        alias_spacing_hz=spacing,
        residual_gate_hz=args.residual_gate_hz,
    )
    branch_comparison = _branch_comparison(observations, selected)
    args.output_root.mkdir(parents=True, exist_ok=True)
    alias_png = args.output_root / "cfo-alias-canonicalization.png"
    _render_alias_figure(alias_png, observations, selected, branch_comparison)
    replay = _replay(args, rows, document, selected)
    replay_png = args.output_root / "cfo-alias-corrected-replay.png"
    _render_replay(replay_png, replay)
    output = {
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "input": str(args.input.resolve()),
        "input_sha256": _sha256(args.input),
        "trajectory_json": str(args.trajectory_json.resolve()),
        "trajectory_json_sha256": _sha256(args.trajectory_json),
        "interval_s": [args.start_s, args.end_s],
        "glrt64_high_gate": high_gate,
        "alias_spacing_hz": spacing,
        "source_observation_count": len(observations),
        "selected_fit": asdict(selected),
        "degree_comparison": [
            {
                "polynomial_degree": fit.polynomial_degree,
                "retained_count": sum(fit.retained),
                "residual_rms_hz": fit.residual_rms_hz,
                "bic": fit.bic,
                "held_out_rms_hz": fit.held_out_rms_hz,
            }
            for fit in degree_fits
        ],
        "two_branch_comparison": branch_comparison,
        "replay_summary": _replay_summary(replay),
        "replay_records": replay,
        "alias_png": str(alias_png.resolve()),
        "alias_png_sha256": _sha256(alias_png),
        "replay_png": str(replay_png.resolve()) if replay else None,
        "replay_png_sha256": _sha256(replay_png) if replay else None,
    }
    output_path = args.output_root / "cfo-alias-analysis.json"
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "selected_degree": selected.polynomial_degree,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
