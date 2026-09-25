#!/usr/bin/env python3
"""Audit persisted GLRT64 scores against 1.333 ms full-frame Qin evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from leo.analysis.starlink.local_doppler import stable_measurement_floats

DEFAULT_FRAME_RESULTS = Path(
    "reports/figures/2026_08_23_470384_qin_frames_25_45/qin-frame-results.json"
)
DEFAULT_SCAN = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/"
    "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963/"
    "standard.pilot-scan.v3.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_qin_score_audit")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_qin_score_audit.md")
INK = "#17354a"
BLUE = "#2f83b7"
AMBER = "#d9881f"
GREEN = "#3f8f67"
PURPLE = "#7b65a8"
GRAY = "#8997a2"
RED = "#bd5b52"
BRANCH_COLORS = (BLUE, GREEN, PURPLE, RED, "#4e91a8")


@dataclass(frozen=True, slots=True)
class AuditWindow:
    branch_index: int
    branch_label: str
    association_index: int
    time_s: float
    model_proximate: bool
    glrt_exact: float
    glrt_control: float
    glrt_margin: float
    glrt_residual_cfo_hz: float
    glrt_residual_at_edge: bool
    candidate_rank: int
    qam_accuracy: float | None
    qam_evm: float | None
    frame_exact_median: float
    frame_control_median: float
    frame_margin_median: float
    frame_margin_positive_fraction: float
    frame_strong_exact_fraction: float
    frame_direct_gate_fraction: float
    frame_residual_boundary_fraction: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame-results", type=Path, default=DEFAULT_FRAME_RESULTS)
    parser.add_argument("--pilot-scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def audit_windows(
    frame_document: dict[str, Any], scan: dict[str, Any]
) -> tuple[AuditWindow, ...]:
    """Join original candidate scores to the exact same saved frame rows."""

    detections = {int(item["sample_start"]): item for item in scan["detections"]}
    frames_by_association: dict[int, list[dict[str, Any]]] = {}
    for frame in frame_document["frames"]:
        frames_by_association.setdefault(int(frame["association_index"]), []).append(frame)
    labels = {
        int(summary["branch"]["index"]): str(summary["branch"]["label"])
        for summary in frame_document["branches"]
    }
    values = []
    for window in frame_document["candidate_windows"]:
        association = int(window["association_index"])
        members = frames_by_association[association]
        detection = detections[int(window["probe_sample_start"])]
        candidates = [
            item
            for item in detection["candidates"]
            if int(item["rank"]) == int(window["candidate_rank"])
        ]
        if len(candidates) != 1:
            raise ValueError("saved window does not resolve to one persisted candidate")
        candidate = candidates[0]
        scores = [score for score in candidate["scores"] if score["method"] == "glrt64"]
        if len(scores) != 1:
            raise ValueError("candidate does not contain one GLRT64 score")
        score = scores[0]
        exact = np.asarray([float(item["exact_coherence"]) for item in members])
        control = np.asarray([float(item["control_coherence"]) for item in members])
        margins = exact - control
        residual = np.asarray([float(item["residual_from_initial_hz"]) for item in members])
        values.append(
            AuditWindow(
                branch_index=int(window["branch_index"]),
                branch_label=labels[int(window["branch_index"])],
                association_index=association,
                time_s=float(window["detection_time_s"]),
                model_proximate=float(window["selection_model_error_hz"]) <= 2_500.0,
                glrt_exact=float(score["exact_score"]),
                glrt_control=float(score["control_score"]),
                glrt_margin=float(score["margin"]),
                glrt_residual_cfo_hz=float(score["residual_cfo_hz"]),
                glrt_residual_at_edge=abs(float(score["residual_cfo_hz"])) >= 110_000.0,
                candidate_rank=int(candidate["rank"]),
                qam_accuracy=(
                    None
                    if candidate.get("qam_accuracy") is None
                    else float(candidate["qam_accuracy"])
                ),
                qam_evm=(
                    None if candidate.get("qam_evm") is None else float(candidate["qam_evm"])
                ),
                frame_exact_median=float(np.median(exact)),
                frame_control_median=float(np.median(control)),
                frame_margin_median=float(np.median(margins)),
                frame_margin_positive_fraction=float(np.mean(margins >= 0.0)),
                frame_strong_exact_fraction=float(np.mean(exact >= 0.02)),
                frame_direct_gate_fraction=float(np.mean((exact >= 0.02) & (margins >= 0.0))),
                frame_residual_boundary_fraction=float(np.mean(np.abs(residual) >= 3_900.0)),
            )
        )
    return tuple(values)


def _percentiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "p05": float(np.percentile(array, 5)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
    }


def branch_summaries(
    windows: tuple[AuditWindow, ...], branch_count: int
) -> tuple[dict[str, Any], ...]:
    summaries = []
    for branch_index in range(branch_count):
        values = tuple(
            item
            for item in windows
            if item.branch_index == branch_index and item.model_proximate
        )
        qam = [item.qam_accuracy for item in values if item.qam_accuracy is not None]
        evm = [item.qam_evm for item in values if item.qam_evm is not None]
        summaries.append(
            {
                "branch_index": branch_index,
                "branch_label": values[0].branch_label,
                "model_proximate_window_count": len(values),
                "original_glrt64": {
                    "exact": _percentiles([item.glrt_exact for item in values]),
                    "control": _percentiles([item.glrt_control for item in values]),
                    "margin": _percentiles([item.glrt_margin for item in values]),
                    "positive_margin_window_fraction": float(
                        np.mean([item.glrt_margin >= 0.0 for item in values])
                    ),
                    "margin_at_least_005_window_fraction": float(
                        np.mean([item.glrt_margin >= 0.05 for item in values])
                    ),
                    "residual_grid_edge_window_fraction": float(
                        np.mean([item.glrt_residual_at_edge for item in values])
                    ),
                },
                "frame_local_300_symbol": {
                    "window_median_exact": _percentiles(
                        [item.frame_exact_median for item in values]
                    ),
                    "window_median_control": _percentiles(
                        [item.frame_control_median for item in values]
                    ),
                    "window_median_margin": _percentiles(
                        [item.frame_margin_median for item in values]
                    ),
                    "positive_margin_frame_fraction": float(
                        np.mean([item.frame_margin_positive_fraction for item in values])
                    ),
                    "exact_at_least_002_frame_fraction": float(
                        np.mean([item.frame_strong_exact_fraction for item in values])
                    ),
                    "combined_gate_frame_fraction": float(
                        np.mean([item.frame_direct_gate_fraction for item in values])
                    ),
                    "residual_search_boundary_frame_fraction": float(
                        np.mean([item.frame_residual_boundary_fraction for item in values])
                    ),
                },
                "full_frame_qam_rank0": {
                    "window_count": len(qam),
                    "accuracy": None if not qam else _percentiles(qam),
                    "evm": None if not evm else _percentiles(evm),
                },
            }
        )
    return tuple(summaries)


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def render_score_time_comparison(
    path: Path, windows: tuple[AuditWindow, ...], branch_count: int
) -> None:
    figure, axes = plt.subplots(
        branch_count,
        1,
        figsize=(16, 12),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    axes = np.atleast_1d(axes)
    figure.suptitle(
        "Persisted 20 ms GLRT64 score versus independent 1.333 ms frame coherence",
        color=INK,
        fontsize=18,
        fontweight="bold",
    )
    for axis, branch_index in zip(axes, range(branch_count), strict=True):
        values = tuple(
            item
            for item in windows
            if item.branch_index == branch_index and item.model_proximate
        )
        time = [item.time_s for item in values]
        axis.scatter(time, [item.glrt_exact for item in values], color=AMBER, s=8, alpha=0.7)
        axis.scatter(
            time,
            [item.glrt_control for item in values],
            color=GRAY,
            s=6,
            alpha=0.45,
        )
        axis.scatter(
            time,
            [item.frame_exact_median for item in values],
            color=BLUE,
            s=8,
            alpha=0.75,
        )
        axis.scatter(
            time,
            [item.frame_control_median for item in values],
            color=PURPLE,
            s=5,
            alpha=0.45,
        )
        axis.axhline(0.02, color=RED, linewidth=0.9, linestyle="--")
        axis.set_yscale("log")
        axis.set_ylim(0.003, 1.0)
        axis.set_ylabel("score")
        axis.set_title(values[0].branch_label, loc="left", color=INK)
        axis.grid(alpha=0.16, which="both")
    axes[-1].set_xlabel("capture time (s)")
    axes[0].legend(
        handles=(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=AMBER,
                label="original GLRT64 exact",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=GRAY,
                label="original GLRT64 control",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=BLUE,
                label="median 300-symbol frame exact",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=PURPLE,
                label="median 300-symbol frame control",
            ),
            Line2D([0], [0], color=RED, linestyle="--", label="0.02 frame-strength gate"),
        ),
        ncol=3,
        loc="lower left",
        fontsize=9,
    )
    _save(figure, path)


def render_gate_decomposition(path: Path, summaries: tuple[dict[str, Any], ...]) -> None:
    labels = [item["branch_label"].split(" · ")[0] for item in summaries]
    x = np.arange(len(labels), dtype=float)
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.5), constrained_layout=True)
    figure.suptitle(
        "Why the early branches disappeared from the frame-level fit",
        color=INK,
        fontsize=18,
        fontweight="bold",
    )
    width = 0.25
    axes[0].bar(
        x - width,
        [item["original_glrt64"]["positive_margin_window_fraction"] for item in summaries],
        width,
        color=AMBER,
        label="GLRT margin > 0",
    )
    axes[0].bar(
        x,
        [
            item["frame_local_300_symbol"]["positive_margin_frame_fraction"]
            for item in summaries
        ],
        width,
        color=BLUE,
        label="frame exact > control",
    )
    axes[0].bar(
        x + width,
        [
            item["frame_local_300_symbol"]["exact_at_least_002_frame_fraction"]
            for item in summaries
        ],
        width,
        color=RED,
        label="frame exact ≥ 0.02",
    )
    axes[0].set_title("A · Gate decomposition", loc="left", color=INK)
    axes[0].set_ylabel("fraction")
    axes[0].legend(fontsize=8, loc="lower right")

    qam = [
        item["full_frame_qam_rank0"]["accuracy"]["median"]
        if item["full_frame_qam_rank0"]["accuracy"] is not None
        else np.nan
        for item in summaries
    ]
    axes[1].bar(x, qam, color=BRANCH_COLORS[: len(labels)])
    axes[1].axhline(0.25, color=INK, linestyle="--", linewidth=1, label="QPSK chance")
    axes[1].set_title("B · Independent full-frame QAM", loc="left", color=INK)
    axes[1].set_ylabel("median hard-symbol accuracy")
    axes[1].legend(fontsize=8)

    axes[2].bar(
        x - width / 2,
        [item["original_glrt64"]["residual_grid_edge_window_fraction"] for item in summaries],
        width,
        color=AMBER,
        label="GLRT residual near ±Nyquist",
    )
    axes[2].bar(
        x + width / 2,
        [
            item["frame_local_300_symbol"]["residual_search_boundary_frame_fraction"]
            for item in summaries
        ],
        width,
        color=BLUE,
        label="frame residual near ±4 kHz",
    )
    axes[2].set_title("C · Frequency-search boundary", loc="left", color=INK)
    axes[2].set_ylabel("fraction")
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.set_ylim(0, 1.02)
        axis.grid(axis="y", alpha=0.16)
    _save(figure, path)


def write_report(path: Path, results: dict[str, Any]) -> None:
    rows = []
    for item in results["branches"]:
        glrt = item["original_glrt64"]
        frame = item["frame_local_300_symbol"]
        qam = item["full_frame_qam_rank0"]
        rows.append(
            "| {label} | {ge:.3f} / {gm:.3f} | {fe:.4f} / {fm:.4f} | "
            "{positive:.1f}% | {strong:.1f}% | {qam:.3f} | {edge:.1f}% | "
            "{boundary:.1f}% |".format(
                label=item["branch_label"],
                ge=glrt["exact"]["median"],
                gm=glrt["margin"]["median"],
                fe=frame["window_median_exact"]["median"],
                fm=frame["window_median_margin"]["median"],
                positive=100 * frame["positive_margin_frame_fraction"],
                strong=100 * frame["exact_at_least_002_frame_fraction"],
                qam=(
                    qam["accuracy"]["median"]
                    if qam["accuracy"] is not None
                    else float("nan")
                ),
                edge=100 * glrt["residual_grid_edge_window_fraction"],
                boundary=100 * frame["residual_search_boundary_frame_fraction"],
            )
        )
    text = f"""# Audit of original GLRT64 versus 1.333 ms Qin scores

## Correction

The earlier statement that B1–B3 “fail the exact-Qin-versus-control test” was
too strong.  The reported 1.5–4.2% fractions included a separate
`exact coherence ≥ 0.02` strength gate.  Without that threshold, exact Qin
still beats the rolled control in 81–93% of model-proximate early frames.

![Score comparison](figures/2026_08_23_470384_qin_score_audit/glrt-vs-frame-score-time.png)

![Gate decomposition](figures/2026_08_23_470384_qin_score_audit/gate-decomposition.png)

| branch | GLRT e/m | frame e/m | Qin>ctrl | exact≥.02 | QAM | GLRT edge | frame edge |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## What changed

The two scores do not have the same integration or normalization:

- persisted GLRT64 uses symbols 2–65 from every complete frame in the 20 ms
  probe (normally 14–15 frames), pools their likelihood noncoherently, and
  normalizes after the per-symbol matched correlation;
- the new estimator makes one independent CFO estimate from all 300 pilot
  symbols in one 1.333 ms frame and normalizes by the total energy in the eight
  demodulated edge bins.

Thus the original GLRT track can be a real, sequence-specific **window-pooled**
correlation while still being too weak or contaminated for a precise CFO from
one frame.  Moving to 1.333 ms discarded most of the GLRT's cross-frame
integration gain.  The 0.02 gate then discarded the remaining low-coherence
frame evidence.

This is not primarily a ±4 kHz search-range failure: only 0.9–3.3% of early
frame estimates hit that boundary.  However, B2 and B3 place about 94% of their
original GLRT residuals near the ±113.6 kHz symbol-rate Nyquist boundary, so
their absolute GLRT CFO coordinate is especially alias-sensitive.

The independent full-frame QAM check is also important.  B1–B3 remain near the
QPSK chance level (median 0.26–0.27), whereas B4–B5 reach 0.82–0.88.  So the
early line is not lost raw signal; it is weaker evidence that does not support
the same per-frame phase/CFO precision as the later signal.

## Consequence for fitting

Removing only the 0.02 threshold does not recover trustworthy early ramps.
Their independent-lock robust CFO RMS is roughly 1.1–1.6 kHz, and no segment
passes the existing 20 ms / 40 Hz-RMS coherence gate.  Recovery therefore needs
longer coherent or semi-coherent pooling—not simply a looser frame threshold.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    frames = _load(arguments.frame_results)
    scan = _load(arguments.pilot_scan)
    windows = audit_windows(frames, scan)
    summaries = branch_summaries(windows, len(frames["branches"]))
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    score_path = arguments.output_root / "glrt-vs-frame-score-time.png"
    gate_path = arguments.output_root / "gate-decomposition.png"
    render_score_time_comparison(score_path, windows, len(summaries))
    render_gate_decomposition(gate_path, summaries)
    results = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-glrt64-vs-frame-qin-score-audit-v1",
            "input": {
                "frame_results": str(arguments.frame_results),
                "pilot_scan": str(arguments.pilot_scan),
            },
            "branches": summaries,
            "windows": [asdict(item) for item in windows],
            "figures": {"score_time": str(score_path), "gate_decomposition": str(gate_path)},
        }
    )
    (arguments.output_root / "qin-score-audit-results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(arguments.report_path, results)
    print(json.dumps(results["branches"], indent=2))


if __name__ == "__main__":
    main()
