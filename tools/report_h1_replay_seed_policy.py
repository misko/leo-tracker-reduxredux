#!/usr/bin/env python3
"""Compare tracking-CFO and acquisition-CFO transport during conditioned replay.

This is a research-only audit for the strong H1 line in the 2026-08-21
full-capture example.  It deliberately leaves Standard products unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Literal

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.standard.analyzers import (
    _receiver_standard_config,
    production_standard_v2_configuration,
)
from leo.analysis.standard.full_capture_glrt20ms import (
    WindowResult,
    _threshold_winners,
    _window_winners,
)
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.trajectories import correct_polynomial_cfo
from leo.analysis.starlink.trajectory_accounting import associate_trajectory_baseline
from leo.analysis.starlink.trajectory_feedback import (
    fit_residual_hough_pilot_trajectories,
    infer_hough_replay_alias_indices,
    trajectory_observations,
)
from leo.storage import PinnedLocalRoot, RecordingStore

SOURCE_JSON = Path(
    "reports/figures/2026_08_23_140820_glrt20ms/"
    "cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.json"
)
OUTPUT_ROOT = Path("reports/figures/2026_08_23_h1_replay_seed_policy")
REPORT_PATH = Path("reports/2026_08_23_h1_replay_seed_policy.md")
SeedPolicy = Literal["tracking", "acquired"]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, default=SOURCE_JSON)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def conditioned_seed_hz(
    *,
    acquired_cfo_hz: float,
    tracking_cfo_hz: float,
    lifted_trajectory_hz: float,
    policy: SeedPolicy,
) -> float:
    """Transport one detector coordinate through a trajectory correction."""

    values = (acquired_cfo_hz, tracking_cfo_hz, lifted_trajectory_hz)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("conditioned seed inputs must be finite")
    if policy == "tracking":
        return tracking_cfo_hz - lifted_trajectory_hz
    if policy == "acquired":
        return acquired_cfo_hz - lifted_trajectory_hz
    raise ValueError("unknown conditioned replay seed policy")


def _values(rows: list[dict[str, float]], key: str) -> np.ndarray:
    return np.asarray([row[key] for row in rows], dtype=float)


def _transitions(rows: list[dict[str, float]], field: str, *, threshold: float) -> dict[str, int]:
    counts = {"positive_to_positive": 0, "positive_to_negative": 0}
    for row in rows:
        before = row["baseline_margin"] >= threshold
        after = row[field] >= threshold
        if not before:
            continue
        counts["positive_to_positive" if after else "positive_to_negative"] += 1
    return counts


def summarize_track(rows: list[dict[str, float]], *, positive_margin: float) -> dict[str, Any]:
    """Return stable statistics for one probe-level seed-policy comparison."""

    if not rows or not math.isfinite(positive_margin):
        raise ValueError("track summary requires rows and a finite threshold")
    baseline = _values(rows, "baseline_margin")
    current = _values(rows, "current_margin")
    transported = _values(rows, "transport_margin")
    baseline_residual = _values(rows, "baseline_residual_hz")
    transported_residual = _values(rows, "transport_residual_hz")
    transported_total = _values(rows, "transport_seed_hz") + transported_residual
    current_total = _values(rows, "current_seed_hz") + _values(rows, "current_residual_hz")
    return {
        "associated_probe_count": len(rows),
        "positive_margin": positive_margin,
        "baseline_positive_count": int(np.sum(baseline >= positive_margin)),
        "current_transitions": _transitions(rows, "current_margin", threshold=positive_margin),
        "transport_transitions": _transitions(rows, "transport_margin", threshold=positive_margin),
        "baseline_median_margin": float(np.median(baseline)),
        "current_median_margin": float(np.median(current)),
        "transport_median_margin": float(np.median(transported)),
        "current_median_margin_delta": float(np.median(current - baseline)),
        "transport_median_margin_delta": float(np.median(transported - baseline)),
        "baseline_median_exact": float(np.median(_values(rows, "baseline_exact"))),
        "baseline_median_control": float(np.median(_values(rows, "baseline_control"))),
        "current_median_exact": float(np.median(_values(rows, "current_exact"))),
        "current_median_control": float(np.median(_values(rows, "current_control"))),
        "transport_median_exact": float(np.median(_values(rows, "transport_exact"))),
        "transport_median_control": float(np.median(_values(rows, "transport_control"))),
        "transport_residual_recovery_median_abs_hz": float(
            np.median(np.abs(transported_residual - baseline_residual))
        ),
        "current_total_residual_median_abs_hz": float(np.median(np.abs(current_total))),
        "transport_total_residual_median_abs_hz": float(np.median(np.abs(transported_total))),
        "transport_total_residual_p90_abs_hz": float(np.percentile(np.abs(transported_total), 90)),
        "transport_total_residual_max_abs_hz": float(np.max(np.abs(transported_total))),
    }


def _plot_h1(output: Path, rows: list[dict[str, float]], threshold: float) -> None:
    time_s = _values(rows, "time_s")
    figure, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True, constrained_layout=True)
    axes[0].scatter(
        time_s,
        _values(rows, "acquired_cfo_hz") / 1e3,
        s=14,
        marker="x",
        color="#f28e2b",
        alpha=0.75,
        label="acquisition CFO A",
    )
    axes[0].scatter(
        time_s,
        _values(rows, "tracking_cfo_hz") / 1e3,
        s=13,
        color="#2678a8",
        alpha=0.75,
        label="reported GLRT tracking CFO A+r",
    )
    axes[0].plot(
        time_s,
        _values(rows, "line_hz") / 1e3,
        color="#111827",
        linewidth=1.4,
        label="H1 lifted line L",
    )
    axes[0].set_ylabel("CFO (kHz)")
    axes[0].set_title("A · H1 is strong and linear after the GLRT residual is added", loc="left")
    axes[0].legend(ncol=3, fontsize=9)

    axes[1].scatter(
        time_s,
        _values(rows, "baseline_residual_hz") / 1e3,
        s=14,
        marker="x",
        color="#c44e52",
        alpha=0.8,
        label="baseline GLRT residual r=(A+r)-A",
    )
    axes[1].axhline(0.0, color="#9aa3aa", linewidth=0.8)
    axes[1].set_ylabel("GLRT residual (kHz)")
    axes[1].set_title(
        "B · H1 residual is large and time-varying; consuming it changes the detector coordinate",
        loc="left",
    )
    axes[1].legend(fontsize=9)

    axes[2].scatter(
        time_s,
        _values(rows, "baseline_margin"),
        s=16,
        facecolors="none",
        edgecolors="#f28e2b",
        linewidths=0.7,
        label="baseline at acquired CFO A",
    )
    axes[2].scatter(
        time_s,
        _values(rows, "current_margin"),
        s=11,
        color="#c44e52",
        alpha=0.65,
        label="current replay seed (A+r)-L",
    )
    axes[2].scatter(
        time_s,
        _values(rows, "transport_margin"),
        s=11,
        color="#2a9d6f",
        alpha=0.65,
        label="transported acquisition seed A-L",
    )
    axes[2].axhline(
        threshold,
        color="#111827",
        linestyle="--",
        linewidth=1.0,
        label=f"accounting threshold {threshold:.3f}",
    )
    axes[2].set_ylabel("exact − control margin")
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_title(
        "C · H1 loss is caused by seed transport, not disappearance of pilot evidence",
        loc="left",
    )
    axes[2].legend(ncol=2, fontsize=9)
    figure.suptitle(
        "H1 conditioned-replay loss audit · cap-20260821T140820-470384cc9284 · stream-0/RX0 upper",
        fontsize=15,
        fontweight="bold",
    )
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _plot_control(
    output: Path,
    tracks: dict[str, list[dict[str, float]]],
    summaries: dict[str, dict[str, Any]],
    threshold: float,
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(15, 5.4), sharey=True, constrained_layout=True)
    for axis, label in zip(axes, ("H1", "H3"), strict=True):
        rows = tracks[label]
        time_s = _values(rows, "time_s")
        axis.scatter(
            time_s,
            _values(rows, "baseline_margin"),
            s=13,
            facecolors="none",
            edgecolors="#f28e2b",
            linewidths=0.6,
            label="baseline",
        )
        axis.scatter(
            time_s,
            _values(rows, "current_margin"),
            s=9,
            color="#c44e52",
            alpha=0.55,
            label="current tracking-CFO seed",
        )
        axis.scatter(
            time_s,
            _values(rows, "transport_margin"),
            s=9,
            color="#2a9d6f",
            alpha=0.55,
            label="transport acquired-CFO seed",
        )
        axis.axhline(threshold, color="#111827", linestyle="--", linewidth=0.9)
        summary = summaries[label]
        current = summary["current_transitions"]["positive_to_positive"]
        transported = summary["transport_transitions"]["positive_to_positive"]
        count = summary["associated_probe_count"]
        axis.set_title(
            f"{label}: current {current}/{count} positive; transported {transported}/{count}"
        )
        axis.set_xlabel("capture time (s)")
    axes[0].set_ylabel("exact − control margin")
    axes[0].legend(fontsize=8)
    figure.suptitle("Conditioned replay seed-policy comparison", fontsize=15, fontweight="bold")
    figure.savefig(output, dpi=190)
    plt.close(figure)


def _write_report(
    path: Path,
    *,
    source: dict[str, Any],
    summaries: dict[str, dict[str, Any]],
    tracks: dict[str, dict[str, Any]],
    audit_figure: Path,
    control_figure: Path,
    result_json: Path,
) -> None:
    h1 = summaries["H1"]
    h3 = summaries["H3"]
    lines = [
        "# H1 conditioned-replay seed-policy experiment",
        "",
        "## Result",
        "",
        "H1 is not lost by Hough or by support closure. It is lost when conditioned "
        "replay subtracts the trajectory and seeds GLRT with the already residual-adjusted "
        "tracking CFO. Transporting the acquisition CFO instead preserves all H1 pilot "
        "evidence while the recomputed acquisition-plus-residual coordinate remains near zero.",
        "",
        f"![H1 replay loss audit]({audit_figure.relative_to(path.parent)})",
        "",
        f"![H1 and H3 control]({control_figure.relative_to(path.parent)})",
        "",
        "## Statistics",
        "",
        "| Track | Rate | Associated | Baseline positive | Current P→P / P→N | "
        "Transported P→P / P→N | Baseline median margin | Current | Transported |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, summary in (("H1", h1), ("H3", h3)):
        current = summary["current_transitions"]
        transported = summary["transport_transitions"]
        lines.append(
            f"| {label} | {tracks[label]['slope_hz_s'] / 1e3:+.3f} kHz/s | "
            f"{summary['associated_probe_count']} | {summary['baseline_positive_count']} | "
            f"{current['positive_to_positive']} / {current['positive_to_negative']} | "
            f"{transported['positive_to_positive']} / "
            f"{transported['positive_to_negative']} | "
            f"{summary['baseline_median_margin']:.4f} | "
            f"{summary['current_median_margin']:.4f} | "
            f"{summary['transport_median_margin']:.4f} |"
        )
    lines.extend(
        [
            "",
            "For H1, transported replay leaves a median absolute total residual of "
            f"{h1['transport_total_residual_median_abs_hz']:.1f} Hz, a 90th percentile "
            f"of {h1['transport_total_residual_p90_abs_hz']:.1f} Hz, and a maximum of "
            f"{h1['transport_total_residual_max_abs_hz']:.1f} Hz.",
            "",
            "## Detector-coordinate interpretation",
            "",
            "Let `A` be acquisition CFO, `r` the GLRT correlation-domain residual, `T=A+r` "
            "the reported tracking CFO, and `L` the trajectory correction. The current "
            "policy seeds replay at `T-L`. The tested policy seeds at `A-L`, then allows "
            "GLRT to re-estimate `r`. The latter preserves the two-stage detector coordinate. "
            "It is intentionally reported separately from the stronger question of whether "
            "`r` can be consumed directly as a sample-domain phase correction.",
            "",
            "This experiment is degree-one, candidate-only, research-only, and makes no "
            "satellite attribution. It changes no Standard product or gate.",
            "",
            f"Probe-level results: [`{result_json.name}`]({result_json.relative_to(path.parent)})",
            "",
            "## Provenance",
            "",
            f"- Session: `{source['session_id']}`",
            f"- Path: `{source['stream_id']}/RX{source['receiver_id']} {source['edge']}`",
            f"- Window/stride: {source['window_ms']} ms / {source['stride_ms']} ms",
            f"- GLRT size: {source['glrt_size']}",
            "- H1 is the first time-ordered production Hough representative; H3 is the "
            "surviving-track control.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    windows = tuple(WindowResult(**item) for item in source["windows"])
    hough_detections = _threshold_winners(windows)
    replay_detections = _window_winners(windows, require_margin_pass=False)
    config = _receiver_standard_config(production_standard_v2_configuration()["path-standard"])
    _, representatives = fit_residual_hough_pilot_trajectories(
        hough_detections, config.feedback, config.segmentation
    )
    ordered = tuple(sorted(representatives, key=lambda item: (item[1].start_s, item[1].end_s)))
    if len(ordered) < 3:
        raise ValueError("H1/H3 audit requires at least three Hough representatives")
    selected = {"H1": ordered[0], "H3": ordered[2]}
    observations = trajectory_observations(hough_detections)
    alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
    aliases = infer_hough_replay_alias_indices(
        tuple(selected.values()), observations, alias_spacing_hz=alias_spacing_hz
    )
    matches: dict[str, list[tuple[Any, Any]]] = {}
    for label, (_, trajectory) in selected.items():
        offset_hz = aliases[trajectory.trajectory_id] * alias_spacing_hz
        values = []
        for detection in replay_detections:
            if not trajectory.start_s <= detection.time_s <= trajectory.end_s:
                continue
            match = associate_trajectory_baseline(
                detection,
                trajectory,
                frequency_offset_hz=offset_hz,
                association_gate_hz=config.trajectory_accounting.association_gate_hz,
            )
            if match is not None:
                values.append((detection, match))
        matches[label] = values

    tracks: dict[str, list[dict[str, float]]] = {}
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(source["session_id"])
        reader = store.reader(bundle, source["stream_id"], verify=True)
        receiver_id = int(source["receiver_id"])
        sample_rate_hz = reader.sample_rate_hz
        probe_samples = round(source["window_ms"] * sample_rate_hz / 1_000)
        for label, (_, trajectory) in selected.items():
            print(f"scoring {label}: {len(matches[label])} associated probes", flush=True)
            offset_hz = aliases[trajectory.trajectory_id] * alias_spacing_hz
            rows: list[dict[str, float]] = []
            for detection, match in matches[label]:
                ci16 = reader.read(
                    detection.sample_start, probe_samples, receiver_ids=(receiver_id,)
                )
                samples = (
                    ci16[:, 0, 0].astype(np.float64) + 1j * ci16[:, 0, 1].astype(np.float64)
                ) / 32_768.0
                corrected = correct_polynomial_cfo(
                    samples,
                    sample_rate_hz,
                    detection.sample_start,
                    trajectory,
                    frequency_offset_hz=offset_hz,
                )
                lifted_hz = float(trajectory.frequency_hz(detection.time_s)) + offset_hz
                current_seed = conditioned_seed_hz(
                    acquired_cfo_hz=match.candidate_acquired_cfo_hz,
                    tracking_cfo_hz=match.trajectory_tracking_cfo_hz,
                    lifted_trajectory_hz=lifted_hz,
                    policy="tracking",
                )
                transport_seed = conditioned_seed_hz(
                    acquired_cfo_hz=match.candidate_acquired_cfo_hz,
                    tracking_cfo_hz=match.trajectory_tracking_cfo_hz,
                    lifted_trajectory_hz=lifted_hz,
                    policy="acquired",
                )
                current = conditioned_glrt64_score(
                    corrected,
                    sample_rate_hz,
                    epoch_sample=match.candidate_epoch_sample,
                    acquired_cfo_hz=current_seed,
                    edge=source["edge"],
                    glrt_size=config.feedback.glrt_size,
                )
                transported = conditioned_glrt64_score(
                    corrected,
                    sample_rate_hz,
                    epoch_sample=match.candidate_epoch_sample,
                    acquired_cfo_hz=transport_seed,
                    edge=source["edge"],
                    glrt_size=config.feedback.glrt_size,
                )
                baseline = match.scores[0]
                rows.append(
                    {
                        "time_s": detection.time_s,
                        "sample_start": float(detection.sample_start),
                        "acquired_cfo_hz": match.candidate_acquired_cfo_hz,
                        "tracking_cfo_hz": match.trajectory_tracking_cfo_hz,
                        "baseline_residual_hz": (
                            match.trajectory_tracking_cfo_hz - match.candidate_acquired_cfo_hz
                        ),
                        "line_hz": lifted_hz,
                        "association_error_hz": match.association_error_hz,
                        "baseline_margin": baseline.margin,
                        "baseline_exact": baseline.exact_score,
                        "baseline_control": float(baseline.control_score or 0.0),
                        "current_seed_hz": current_seed,
                        "current_margin": current.margin,
                        "current_exact": current.exact_score,
                        "current_control": float(current.control_score or 0.0),
                        "current_residual_hz": current.residual_cfo_hz,
                        "transport_seed_hz": transport_seed,
                        "transport_margin": transported.margin,
                        "transport_exact": transported.exact_score,
                        "transport_control": float(transported.control_score or 0.0),
                        "transport_residual_hz": transported.residual_cfo_hz,
                    }
                )
            tracks[label] = rows
    finally:
        store.close()

    positive_margin = config.trajectory_accounting.positive_margin
    summaries = {
        label: summarize_track(rows, positive_margin=positive_margin)
        for label, rows in tracks.items()
    }
    metadata = {
        label: {
            "trajectory_id": trajectory.trajectory_id,
            "family_id": family_id,
            "start_s": trajectory.start_s,
            "end_s": trajectory.end_s,
            "slope_hz_s": trajectory.coefficients_hz[0],
            "support_count": trajectory.point_count,
            "alias_index": aliases[trajectory.trajectory_id],
        }
        for label, (family_id, trajectory) in selected.items()
    }
    document = {
        "schema_version": 1,
        "kind": "h1-conditioned-replay-seed-policy-experiment",
        "session_id": source["session_id"],
        "stream_id": source["stream_id"],
        "receiver_id": source["receiver_id"],
        "edge": source["edge"],
        "degree_one_only": True,
        "promoted_to_standard": False,
        "policies": {
            "current": "tracking_cfo_minus_lifted_trajectory",
            "transported": "acquired_cfo_minus_lifted_trajectory_then_reestimate_residual",
        },
        "tracks": metadata,
        "summaries": summaries,
        "probe_rows": tracks,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    audit_figure = args.output_root / "h1-replay-loss-audit.png"
    control_figure = args.output_root / "h1-vs-h3-seed-policy.png"
    result_json = args.output_root / "h1-replay-seed-policy.json"
    _plot_h1(audit_figure, tracks["H1"], positive_margin)
    _plot_control(control_figure, tracks, summaries, positive_margin)
    result_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    _write_report(
        args.report,
        source=source,
        summaries=summaries,
        tracks=metadata,
        audit_figure=audit_figure,
        control_figure=control_figure,
        result_json=result_json,
    )
    print(json.dumps(summaries, indent=2), flush=True)
    print(f"wrote {args.report}", flush=True)
    print(f"wrote {audit_figure}", flush=True)
    print(f"wrote {control_figure}", flush=True)
    print(f"wrote {result_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
