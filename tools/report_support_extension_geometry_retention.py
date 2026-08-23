#!/usr/bin/env python3
"""Render connected Hough support without using phase replay as a deletion gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.standard.analyzers import (  # noqa: E402
    _receiver_standard_config,
    production_standard_v2_configuration,
)
from leo.analysis.standard.full_capture_glrt20ms import (  # noqa: E402
    WindowResult,
    _threshold_winners,
)
from leo.analysis.starlink.trajectory_feedback import (  # noqa: E402
    fit_residual_hough_pilot_trajectories,
    trajectory_observations,
)

_SUPPORT_PATH = Path(__file__).with_name("report_full_capture_support_extension.py")
_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "full_capture_support_extension_tool", _SUPPORT_PATH
)
assert _SUPPORT_SPEC is not None and _SUPPORT_SPEC.loader is not None
support = importlib.util.module_from_spec(_SUPPORT_SPEC)
sys.modules[_SUPPORT_SPEC.name] = support
_SUPPORT_SPEC.loader.exec_module(support)

SOURCE_JSON = support.SOURCE_JSON
SEED_REPLAY_JSON = support.SEED_REPLAY_JSON
SEED_POLICY_JSON = Path(
    "reports/figures/2026_08_23_h1_replay_seed_policy/h1-replay-seed-policy.json"
)
OUTPUT_ROOT = Path("reports/figures/2026_08_23_support_extension_geometry_retention")
REPORT_PATH = Path("reports/2026_08_23_support_extension_geometry_retention.md")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, default=SOURCE_JSON)
    parser.add_argument("--seed-replay-json", type=Path, default=SEED_REPLAY_JSON)
    parser.add_argument("--seed-policy-json", type=Path, default=SEED_POLICY_JSON)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def geometry_representative(group: tuple[Any, ...]) -> Any:
    """Choose the strongest support closure without consulting replay outcome."""

    if not group:
        raise ValueError("geometry group cannot be empty")
    maximum_support = max(item.trajectory.point_count for item in group)
    support_ties = tuple(
        item for item in group if item.trajectory.point_count == maximum_support
    )
    minimum_rms = min(item.trajectory.residual_rms_hz for item in support_ties)
    rms_ties = tuple(
        item
        for item in support_ties
        if abs(item.trajectory.residual_rms_hz - minimum_rms) <= 1e-6
    )
    return min(rms_ties, key=lambda item: int(item.label.removeprefix("H")))


def _plot(
    output: Path,
    observations: tuple[Any, ...],
    current: tuple[tuple[str, Any], ...],
    retained: tuple[tuple[str, Any], ...],
    alias_spacing_hz: float,
) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(16, 11), sharex=True, sharey=True)
    colors = support._probe_colors(observations)
    time_s = [item.time_s for item in observations]
    raw_khz = [item.tracking_cfo_hz / 1e3 for item in observations]
    for axis in axes:
        axis.scatter(
            time_s,
            raw_khz,
            marker="x",
            s=18,
            linewidths=0.75,
            color=colors,
            zorder=2,
        )
        axis.grid(alpha=0.18)
        axis.set_ylabel("winning 20 ms-window CFO (kHz)")
        axis.set_xlim(20.0, 47.0)
    support._plot_raw_branches(axes[0], current, observations, alias_spacing_hz)
    support._plot_raw_branches(axes[1], retained, observations, alias_spacing_hz)
    axes[0].set_title(
        f"A · Current Hough output: {len(current)} bounded, overlapping degree-one segments"
    )
    axes[1].set_title(
        f"B · Connected-support geometry: {len(retained)} deduplicated tracks; "
        "phase replay does not delete H1"
    )
    axes[1].set_xlabel("capture time (s)")
    figure.suptitle(
        "Algorithmically independent 20 ms GLRT window probes versus time · "
        "geometry-retention update\n"
        f"{support.SESSION_ID} · stream-0/RX0 upper · degree-one only · "
        "10 ms stride; adjacent probes share 10 ms of IQ",
        fontsize=14,
    )
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _write_report(
    path: Path,
    *,
    figure: Path,
    policy_figure: Path,
    rows: list[dict[str, Any]],
    policy: dict[str, Any],
    result_json: Path,
) -> None:
    lines = [
        "# Connected-support geometry retention after the H1 replay audit",
        "",
        "## Result",
        "",
        "The earlier four-track lower panel was not a neutral support-closure result. It "
        "deleted H1, H4, and H6 using the tracking-CFO residual-consumption replay test. "
        "The updated view keeps line geometry and known-pilot evidence separate from phase-"
        "correction qualification. Connected support therefore yields six deduplicated "
        "geometric tracks, including H1.",
        "",
        f"![Updated support geometry]({figure.relative_to(path.parent)})",
        "",
        f"![Replay seed-policy comparison]({policy_figure.relative_to(path.parent)})",
        "",
        "## Retained geometry",
        "",
        "| Track | Seed interval | Closed interval | Rate | Seed support | Closed support | "
        "Status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['seed_start_s']:.2f}–{row['seed_end_s']:.2f} s | "
            f"{row['start_s']:.2f}–{row['end_s']:.2f} s | "
            f"{row['slope_hz_s'] / 1e3:+.3f} kHz/s | {row['seed_support_count']} | "
            f"{row['support_count']} | {row['status']} |"
        )
    h1 = policy["summaries"]["H1"]
    lines.extend(
        [
            "",
            "## H1 evidence",
            "",
            f"H1 has {h1['associated_probe_count']} associated probes. The current replay "
            f"keeps {h1['current_transitions']['positive_to_positive']} and changes "
            f"{h1['current_transitions']['positive_to_negative']} from positive to negative. "
            "Transporting the acquisition coordinate keeps "
            f"{h1['transport_transitions']['positive_to_positive']}/"
            f"{h1['associated_probe_count']} positive with zero P→N transitions. Its median "
            f"margin is {h1['transport_median_margin']:.4f}, versus "
            f"{h1['baseline_median_margin']:.4f} before correction.",
            "",
            "H2 remains visible as low-support geometry. It is not promoted to phase "
            "correction merely because it appears in this panel. Likewise, retaining H1 as "
            "evidence does not claim satellite attribution or phase continuity.",
            "",
            f"Machine-readable geometry: [`{result_json.name}`]"
            f"({result_json.relative_to(path.parent)})",
            "",
            "This is a research-only, degree-one analysis and changes no Standard product.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    replay = {
        item["label"]: item
        for item in json.loads(args.seed_replay_json.read_text(encoding="utf-8"))["tracks"]
    }
    policy = json.loads(args.seed_policy_json.read_text(encoding="utf-8"))
    windows = tuple(WindowResult(**item) for item in source["windows"])
    detections = _threshold_winners(windows)
    config = _receiver_standard_config(
        production_standard_v2_configuration()["path-standard"]
    )
    _, representatives = fit_residual_hough_pilot_trajectories(
        detections, config.feedback, config.segmentation
    )
    ordered = tuple(
        sorted(representatives, key=lambda item: (item[1].start_s, item[1].end_s))
    )
    current = tuple(
        (f"H{index}", trajectory)
        for index, (_, trajectory) in enumerate(ordered, start=1)
    )
    observations = trajectory_observations(detections)
    hough = config.segmentation.initial_hough
    closed = tuple(
        support.close_degree_one_support(
            label=f"H{index}",
            family_id=family_id,
            seed=trajectory,
            observations=observations,
            alias_spacing_hz=hough.alias_spacing_hz,
            residual_gate_hz=hough.residual_gate_hz,
            maximum_gap_s=hough.maximum_gap_s,
            minimum_extension_support=hough.minimum_support,
            minimum_extension_span_s=hough.minimum_span_s,
        )
        for index, (family_id, trajectory) in enumerate(ordered, start=1)
    )
    groups = support.overlap_groups(closed, minimum_jaccard=0.80)
    selected = tuple(geometry_representative(group) for group in groups)
    selected = tuple(sorted(selected, key=lambda item: item.trajectory.start_s))
    retained = tuple((item.label, item.trajectory) for item in selected)
    group_members_by_selected = {
        geometry_representative(group).label: [member.label for member in group]
        for group in groups
    }

    rows = []
    for item in selected:
        old = replay[item.label]
        if item.label == "H1":
            status = "strong pilot geometry; acquisition-transport replay 163/163 P→P"
        elif item.label == "H2":
            status = "low-support geometry; phase qualification pending"
        elif old["conditioned_transitions"]["positive_to_negative"] == 0:
            status = "previous residual-consumption replay had zero P→N"
        else:
            status = "geometry retained; residual-consumption replay is diagnostic only"
        rows.append(
            {
                "label": item.label,
                "group_members": group_members_by_selected[item.label],
                "seed_start_s": item.seed.start_s,
                "seed_end_s": item.seed.end_s,
                "start_s": item.trajectory.start_s,
                "end_s": item.trajectory.end_s,
                "seed_slope_hz_s": item.seed.coefficients_hz[0],
                "slope_hz_s": item.trajectory.coefficients_hz[0],
                "seed_support_count": item.seed.point_count,
                "support_count": item.trajectory.point_count,
                "residual_rms_hz": item.trajectory.residual_rms_hz,
                "status": status,
            }
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    figure = args.output_root / "frame-probes-geometry-retained.png"
    result_json = args.output_root / "geometry-retention.json"
    _plot(figure, observations, current, retained, hough.alias_spacing_hz)
    document = {
        "schema_version": 1,
        "kind": "connected-support-geometry-retention-update",
        "session_id": source["session_id"],
        "stream_id": source["stream_id"],
        "receiver_id": source["receiver_id"],
        "edge": source["edge"],
        "degree_one_only": True,
        "promoted_to_standard": False,
        "current_hough_count": len(current),
        "geometry_retained_count": len(retained),
        "tracks": rows,
    }
    result_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    policy_figure = args.seed_policy_json.parent / "h1-vs-h3-seed-policy.png"
    _write_report(
        args.report,
        figure=figure,
        policy_figure=policy_figure,
        rows=rows,
        policy=policy,
        result_json=result_json,
    )
    print(json.dumps(document, indent=2), flush=True)
    print(f"wrote {args.report}", flush=True)
    print(f"wrote {figure}", flush=True)
    print(f"wrote {result_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
