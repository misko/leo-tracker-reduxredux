#!/usr/bin/env python3
"""Read-only V2 replay evaluation over one sealed local Standard capture."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.standard.analyzers import _pilot_detections
from leo.analysis.standard.runner import SingleReceiverIqReader
from leo.analysis.starlink.cfo_dealias import (
    calibrate_replay_gate_v2,
    default_cfo_dealias_config,
    replay_observed_cfo_lifts_v2,
)
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.contracts.cfo_dealias import CfoLiftReplayV1, CfoLiftReplayV2, DealiasedTrajectoryBankV2
from leo.contracts.states import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--sealed-run-root", type=Path, required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--edge", choices=("lower", "upper"), default="lower")
    return parser.parse_args()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_path(path: Path, label: str, bank: DealiasedTrajectoryBankV2, replay: Any) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = {(item.branch_id, item.alias_index): item for item in replay.rows}
    figure, (geometry_axis, evidence_axis) = plt.subplots(
        2, 1, figsize=(15, 9), sharex=True, constrained_layout=True
    )
    observations = {item.observation_id: item for item in bank.observations}
    colors = {
        "replay_improved": "#138a36",
        "replay_stable": "#087e8b",
        "geometry_only": "#d97706",
        "replay_rejected": "#c81d25",
        "insufficient": "#7a7a7a",
    }
    for branch in bank.branches:
        for observation_id in branch.observation_ids:
            observation = observations[observation_id]
            geometry_axis.scatter(
                observation.time_s,
                observation.raw_cfo_hz / 1_000,
                color="#a0a0a0",
                alpha=0.30,
                s=8,
            )
        for alias_index in branch.observed_alias_indices:
            row = rows[(branch.branch_id, alias_index)]
            model = next(item for item in branch.models if item.model_id == row.canonical_model_id)
            times = np.linspace(model.start_s, model.end_s, 300)
            frequency = (
                np.polyval(model.coefficients_hz, times - model.reference_time_s)
                + alias_index * default_cfo_dealias_config().alias_spacing_hz
            )
            geometry_axis.plot(
                times,
                frequency / 1_000,
                color=colors[row.tier.value],
                linewidth=2.6 if row.automatic_correction_eligible else 1.5,
                linestyle="-" if row.automatic_correction_eligible else "--",
                label=f"{branch.branch_id[7:15]} n={alias_index:+d} · {row.tier.value}",
            )
            if row.blocks:
                evidence_axis.plot(
                    [
                        (item.block_index + 0.5) * replay.gate_config.block_duration_s
                        for item in row.blocks
                    ],
                    [item.median_corrected_margin for item in row.blocks],
                    color=colors[row.tier.value],
                    marker="o",
                    markersize=3,
                    linewidth=1.0,
                    label=f"{branch.branch_id[7:15]} n={alias_index:+d}",
                )
    geometry_axis.set_ylabel("Absolute CFO (kHz)")
    geometry_axis.grid(alpha=0.2)
    geometry_axis.legend(fontsize=7, ncol=2, loc="best")
    evidence_axis.axhline(
        replay.gate_config.minimum_median_corrected_margin,
        color="black",
        linestyle=":",
        label="absolute corrected-margin gate",
    )
    evidence_axis.set_ylabel("Block-median corrected GLRT64 margin")
    evidence_axis.set_xlabel("Recording time (s)")
    evidence_axis.grid(alpha=0.2)
    evidence_axis.legend(fontsize=7, ncol=2, loc="best")
    figure.suptitle(
        f"V2 replay tiers · {label}\nsolid = automatic correction · dashed = geometry display only",
        fontweight="bold",
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker-replay-gate-v2"})
    plt.close(figure)


def _render_paired(
    path: Path, evaluated: tuple[tuple[str, DealiasedTrajectoryBankV2, Any], ...]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        2, 2, figsize=(16, 10), sharex=True, sharey=True, constrained_layout=True
    )
    colors = {
        "replay_improved": "#138a36",
        "replay_stable": "#087e8b",
        "geometry_only": "#d97706",
        "replay_rejected": "#c81d25",
        "insufficient": "#7a7a7a",
    }
    spacing = default_cfo_dealias_config().alias_spacing_hz
    for axis, (label, bank, replay) in zip(axes.flat, evaluated, strict=True):
        rows = {(item.branch_id, item.alias_index): item for item in replay.rows}
        for branch in bank.branches:
            for alias_index in branch.observed_alias_indices:
                row = rows[(branch.branch_id, alias_index)]
                model = next(
                    item for item in branch.models if item.model_id == row.canonical_model_id
                )
                times = np.linspace(model.start_s, model.end_s, 250)
                frequency = np.polyval(model.coefficients_hz, times - model.reference_time_s)
                axis.plot(
                    times,
                    (frequency + alias_index * spacing) / 1_000,
                    color=colors[row.tier.value],
                    linewidth=2.3 if row.automatic_correction_eligible else 1.3,
                    linestyle="-" if row.automatic_correction_eligible else "--",
                    label=f"{branch.branch_id[7:15]} {row.tier.value}",
                )
        axis.set_title(label)
        axis.grid(alpha=0.2)
        if rows:
            axis.legend(fontsize=6, loc="best")
    for axis in axes[:, 0]:
        axis.set_ylabel("Absolute CFO (kHz)")
    for axis in axes[-1, :]:
        axis.set_xlabel("Recording time (s)")
    figure.suptitle(
        "Paired CFO inventory after V2 replay gate\n"
        "solid = automatic · dashed = preserved geometry",
        fontweight="bold",
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker-replay-gate-v2"})
    plt.close(figure)


def main() -> int:
    args = _arguments()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must lie in 1..16")
    control_document = _read(args.controls)
    gate = calibrate_replay_gate_v2(
        {name: tuple(values) for name, values in control_document["controls"].items()},
        equivalence_safety_multiplier=float(control_document["safety_multiplier"]),
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    scientific_root = args.sealed_run_root / "scientific" / "path-standard"
    presentation_root = args.sealed_run_root / "presentation" / "path-standard"
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.recordings_root))
    bundle = store.inspect(args.session_id)
    store.verify(bundle)
    evaluated = []
    comparisons: list[dict[str, Any]] = []
    try:
        for scope_root in sorted(item for item in scientific_root.iterdir() if item.is_dir()):
            report = _read(scope_root / "standard.path-report.v2.json")["raw_report"]
            label = f"{report['radio_id']} · {report['stream_id']}/RX{report['receiver_id']}"
            bank = DealiasedTrajectoryBankV2.model_validate(
                _read(scope_root / "standard.dealiased-trajectory-bank.v2.json")
            )
            old = CfoLiftReplayV1.model_validate(
                _read(scope_root / "standard.cfo-lift-replay.v1.json")
            )
            pilot = _read(scope_root / "standard.pilot-scan.v3.json")
            scope_output = args.output_root / scope_root.name
            scope_output.mkdir(parents=True, exist_ok=True)
            replay_path = scope_output / "standard.cfo-lift-replay.v2.json"
            if replay_path.exists():
                replay = CfoLiftReplayV2.model_validate(_read(replay_path))
            else:
                source = store.reader(bundle, report["stream_id"], verify=True)
                iq = SingleReceiverIqReader(source, int(report["receiver_id"]))
                feedback = replace(TrajectoryFeedbackConfig(), maximum_workers=args.workers)
                replay = replay_observed_cfo_lifts_v2(
                    iq,
                    _pilot_detections(pilot),
                    bank,
                    feedback,
                    edge=StarlinkEdge(args.edge),
                    path_input_binding_digest=old.path_input_binding_digest,
                    pilot_scan_digest=old.pilot_scan_digest,
                    dealias_config=default_cfo_dealias_config(),
                    gate_config=gate,
                )
            replay_path.write_text(
                json.dumps(replay.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before = (
                presentation_root / scope_root.name / "standard.cfo-trajectories-final-png.v1.png"
            )
            shutil.copyfile(before, scope_output / "before-cfo-final-v1.png")
            _render_path(scope_output / "after-cfo-replay-v2.png", label, bank, replay)
            old_by_key = {(row.branch_id, row.alias_index): row for row in old.rows}
            for row in replay.rows:
                prior = old_by_key.get((row.branch_id, row.alias_index))
                comparisons.append(
                    {
                        "path": label,
                        "branch_id": row.branch_id,
                        "alias_index": row.alias_index,
                        "before_v1": prior.status.value if prior else "not_replayed_v1_model",
                        "after_v2": row.tier.value,
                        "automatic_correction": row.automatic_correction_eligible,
                        "geometry_display": row.geometry_display_eligible,
                        "observations": row.observation_count,
                        "duration_s": row.duration_s,
                        "residual_rms_hz": row.residual_rms_hz,
                        "probes": row.evaluated_probe_count,
                        "blocks": row.evaluated_block_count,
                        "coverage": row.block_coverage_ratio,
                        "median_block_delta": row.median_block_margin_delta,
                        "median_corrected_margin": row.median_block_corrected_margin,
                        "harmful_blocks": row.harmful_block_count,
                        "reason": "; ".join(row.reasons),
                    }
                )
            evaluated.append((label, bank, replay))
    finally:
        store.close()
    paired_before = next(
        (args.sealed_run_root / "presentation" / "paired-presentation").glob(
            "*/standard.cfo-trajectories-final-png.v1.png"
        )
    )
    shutil.copyfile(paired_before, args.output_root / "before-paired-cfo-final-v1.png")
    _render_paired(args.output_root / "after-paired-cfo-replay-v2.png", tuple(evaluated))
    comparison_json = args.output_root / "replay-gate-v1-v2-comparison.json"
    comparison_json.write_text(json.dumps(comparisons, indent=2, sort_keys=True) + "\n")
    with (args.output_root / "replay-gate-v1-v2-comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as destination:
        writer = csv.DictWriter(destination, fieldnames=tuple(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    print(json.dumps({"rows": len(comparisons), "output_root": str(args.output_root.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
