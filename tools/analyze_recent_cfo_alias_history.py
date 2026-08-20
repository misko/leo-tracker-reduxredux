#!/usr/bin/env python3
"""Compare raw and symbol-rate-canonical GLRT64 CFO evidence across captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

from leo.analysis.starlink.cfo_aliases import (
    CfoAliasAssignment,
    CfoAliasObservation,
    CfoAliasTrajectoryReference,
    assign_cfo_aliases_to_trajectories,
)
from leo.contracts.digests import canonical_digest

matplotlib.use("Agg")


SYMBOL_DURATION_S = 4.4e-6
ALIAS_SPACING_HZ = 1.0 / SYMBOL_DURATION_S


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--session-id", action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--residual-gate-hz", type=float, default=2_500.0)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return document


def _observation_id(sample_start: int, rank: int) -> str:
    return canonical_digest(
        {"sample_start": sample_start, "candidate_rank": rank, "method": "glrt64"}
    )


def _observations(pilot: dict[str, Any], high_gate: float) -> tuple[CfoAliasObservation, ...]:
    result: list[CfoAliasObservation] = []
    for detection in pilot["detections"]:
        for candidate in detection["candidates"]:
            score = next(item for item in candidate["scores"] if item["method"] == "glrt64")
            margin = float(score["margin"])
            if margin < high_gate:
                continue
            result.append(
                CfoAliasObservation(
                    _observation_id(int(detection["sample_start"]), int(candidate["rank"])),
                    float(detection["time_s"]),
                    float(score["tracking_cfo_hz"]),
                    max(margin, np.finfo(float).eps),
                )
            )
    return tuple(result)


def _references(bank: dict[str, Any]) -> tuple[CfoAliasTrajectoryReference, ...]:
    return tuple(
        CfoAliasTrajectoryReference(
            str(item["trajectory_id"]),
            int(item["polynomial_degree"]),
            float(item["reference_time_s"]),
            tuple(float(value) for value in item["coefficients_hz"]),
            float(item["start_s"]),
            float(item["end_s"]),
        )
        for item in bank["replayed_representatives"]
    )


def _summarize_path(path_root: Path, *, residual_gate_hz: float) -> dict[str, Any]:
    report_path = path_root / "standard.path-report.v1.json"
    pilot_path = path_root / "standard.pilot-scan.v3.json"
    bank_path = path_root / "standard.trajectory-bank.v2.json"
    report = _load(report_path)
    pilot = _load(pilot_path)
    bank = _load(bank_path)
    references = _references(bank)
    high_gates = {float(item["high_gate"]) for item in bank["trajectories"]}
    high_gate = min(high_gates) if high_gates else math.inf
    observations = _observations(pilot, high_gate)
    assignments = assign_cfo_aliases_to_trajectories(
        observations,
        references,
        alias_spacing_hz=ALIAS_SPACING_HZ,
        residual_gate_hz=residual_gate_hz,
    )
    alias_by_probe: dict[tuple[float, str], set[int]] = defaultdict(set)
    for assignment in assignments:
        alias_by_probe[(assignment.observation.time_s, assignment.trajectory_id)].add(
            assignment.alias_index
        )
    selected_ids = {
        observation_id
        for item in bank["replayed_representatives"]
        for observation_id in item["observation_ids"]
    }
    label = f"{report['radio_id']} · RX{report['receiver_id']}"
    return {
        "label": label,
        "stream_id": report["stream_id"],
        "radio_id": report["radio_id"],
        "receiver_id": report["receiver_id"],
        "status": report["status"],
        "high_gate": None if not math.isfinite(high_gate) else high_gate,
        "strong_observation_count": len(observations),
        "representative_count": len(references),
        "selected_support_count": len(selected_ids),
        "aligned_observation_count": len(assignments),
        "shifted_alias_count": sum(item.alias_index != 0 for item in assignments),
        "multi_alias_probe_count": sum(len(values) > 1 for values in alias_by_probe.values()),
        "alias_indices": sorted({item.alias_index for item in assignments}),
        "residual_rms_hz": (
            float(np.sqrt(np.mean([item.residual_hz**2 for item in assignments])))
            if assignments
            else None
        ),
        "input_sha256": {
            "pilot_scan": _sha256(pilot_path),
            "trajectory_bank": _sha256(bank_path),
            "path_report": _sha256(report_path),
        },
        "_observations": observations,
        "_references": references,
        "_assignments": assignments,
        "_selected_ids": selected_ids,
    }


def _render_session(path: Path, session_id: str, paths: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    rows = len(paths)
    figure, axes = plt.subplots(
        rows,
        2,
        figsize=(17, max(4.0 * rows, 5.0)),
        sharex=True,
        squeeze=False,
        constrained_layout=True,
    )
    palette = plt.get_cmap("tab10")
    for row, summary in enumerate(paths):
        raw_axis, canonical_axis = axes[row]
        observations: tuple[CfoAliasObservation, ...] = summary["_observations"]
        references: tuple[CfoAliasTrajectoryReference, ...] = summary["_references"]
        assignments: tuple[CfoAliasAssignment, ...] = summary["_assignments"]
        selected_ids: set[str] = summary["_selected_ids"]
        if observations:
            raw_axis.scatter(
                [item.time_s for item in observations],
                [item.raw_cfo_hz / 1_000 for item in observations],
                s=5,
                alpha=0.18,
                color="#667085",
                rasterized=True,
                label="all GLRT64 observations ≥ high gate",
            )
            selected = [item for item in observations if item.observation_id in selected_ids]
            raw_axis.scatter(
                [item.time_s for item in selected],
                [item.raw_cfo_hz / 1_000 for item in selected],
                s=8,
                alpha=0.65,
                color="#101828",
                rasterized=True,
                label="published representative support",
            )
        for index, reference in enumerate(references):
            color = palette(index % 10)
            dense = np.linspace(reference.start_s, reference.end_s, 240)
            raw_axis.plot(
                dense,
                reference.frequency_hz(dense) / 1_000,
                color=color,
                linewidth=2.0,
                label=f"track {index + 1} · degree {reference.polynomial_degree}",
            )
            selected_assignments = [
                item for item in assignments if item.trajectory_id == reference.trajectory_id
            ]
            canonical_axis.scatter(
                [item.observation.time_s for item in selected_assignments],
                [item.canonical_cfo_hz / 1_000 for item in selected_assignments],
                s=7,
                alpha=0.42,
                color=color,
                rasterized=True,
            )
            canonical_axis.plot(
                dense,
                reference.frequency_hz(dense) / 1_000,
                color=color,
                linewidth=2.0,
                label=f"track {index + 1}",
            )
        raw_axis.set_ylabel(f"{summary['label']}\nRaw CFO (kHz)")
        canonical_axis.set_ylabel("Canonical CFO (kHz)")
        raw_axis.set_title("Before: independent ±400 kHz GLRT64 CFO observations", loc="left")
        canonical_axis.set_title(
            "After: closest published trajectory modulo 227.273 kHz", loc="left"
        )
        for axis in (raw_axis, canonical_axis):
            axis.grid(alpha=0.16)
            axis.set_xlim(0, 60)
        if references:
            raw_axis.legend(loc="best", fontsize=7, ncols=2)
            canonical_axis.legend(loc="best", fontsize=7, ncols=2)
        else:
            canonical_axis.text(
                0.5,
                0.5,
                "No published trajectory representative",
                ha="center",
                va="center",
                transform=canonical_axis.transAxes,
            )
    axes[-1][0].set_xlabel("Recording time (s)")
    axes[-1][1].set_xlabel("Recording time (s)")
    figure.suptitle(
        f"Historical Standard 2×20 ms CFO alias comparison · {session_id}\n"
        "candidate-only · persisted independent-search evidence · raw CFO preserved",
        fontweight="bold",
    )
    figure.savefig(path, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _public_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if not key.startswith("_")}


def main() -> None:
    arguments = _arguments()
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    sessions: list[dict[str, Any]] = []
    for session_id in arguments.session_id:
        session_root = arguments.analysis_root / session_id
        candidates = sorted(
            path.parent
            for path in session_root.glob(
                "capture-*/scientific/path-standard/sha256:*/standard.path-report.v1.json"
            )
        )
        if not candidates:
            raise ValueError(f"no Standard path products found for {session_id}")
        paths = [
            _summarize_path(candidate, residual_gate_hz=arguments.residual_gate_hz)
            for candidate in candidates
        ]
        paths.sort(key=lambda item: (item["stream_id"], item["receiver_id"]))
        figure_name = f"{session_id}-cfo-alias-comparison.png"
        _render_session(arguments.output_root / figure_name, session_id, paths)
        sessions.append(
            {
                "session_id": session_id,
                "figure": figure_name,
                "paths": [_public_summary(item) for item in paths],
            }
        )
    document = {
        "schema_version": 1,
        "algorithm": "published-trajectory-nearest-symbol-rate-alias-v1",
        "alias_spacing_hz": ALIAS_SPACING_HZ,
        "symbol_duration_s": SYMBOL_DURATION_S,
        "residual_gate_hz": arguments.residual_gate_hz,
        "candidate_only": True,
        "specificity_claimed": False,
        "sessions": sessions,
    }
    (arguments.output_root / "recent-cfo-alias-history.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
