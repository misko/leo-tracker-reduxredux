#!/usr/bin/env python3
"""Produce a bounded, read-only stage-retention audit for two CFO branches."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

TARGET_PREFIXES = ("d049e4ed", "2d370842")
X_LIMIT_S = (0.0, 60.0)
Y_LIMIT_HZ = (-520_000.0, 520_000.0)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--target-prefix", action="append", dest="target_prefixes")
    parser.add_argument(
        "--expected-sha256",
        action="append",
        default=[],
        metavar="NAME=HEX",
        help="verify a copied artifact before reading it (repeatable)",
    )
    return parser.parse_args()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(root: Path, expected_rows: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for item in expected_rows:
        name, separator, digest = item.partition("=")
        if not separator or not name or len(digest) != 64:
            raise ValueError(f"invalid --expected-sha256 value: {item!r}")
        expected[name] = digest
    actual = {name: _sha256(root / name) for name in expected}
    mismatches = [name for name in expected if actual[name] != expected[name]]
    if mismatches:
        raise ValueError(f"artifact digest mismatch: {', '.join(sorted(mismatches))}")
    return {name: f"sha256:{digest}" for name, digest in sorted(actual.items())}


def _raw_points(pilot: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    points = [
        (float(detection["time_s"]), float(score["tracking_cfo_hz"]))
        for detection in pilot["detections"]
        for candidate in detection["candidates"]
        for score in candidate["scores"]
        if score["method"] == "glrt64"
    ]
    return np.asarray([row[0] for row in points]), np.asarray([row[1] for row in points])


def _model_values(model: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    time = np.linspace(float(model["start_s"]), float(model["end_s"]), 300)
    frequency = np.polyval(
        np.asarray(model["coefficients_hz"], dtype=float),
        time - float(model["reference_time_s"]),
    )
    return time, frequency


def _target_id(branches: list[dict[str, Any]], prefix: str) -> str:
    matches = [row["branch_id"] for row in branches if row["branch_id"][7:].startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"target prefix {prefix!r} resolved to {len(matches)} branches")
    return str(matches[0])


def _selected_model(branch: dict[str, Any]) -> dict[str, Any]:
    return next(row for row in branch["models"] if row["model_id"] == branch["selected_model_id"])


def _short(identifier: str) -> str:
    return identifier[7:15]


def _replay_gate_facts(row: dict[str, Any], gate: dict[str, Any]) -> dict[str, bool]:
    block_count = int(row["evaluated_block_count"])
    harmful_fraction = float(row["harmful_block_count"]) / block_count if block_count else 1.0
    return {
        "geometry_display": bool(row["geometry_display_eligible"]),
        "minimum_probes": int(row["evaluated_probe_count"]) >= int(gate["minimum_probe_count"]),
        "minimum_coverage": float(row["block_coverage_ratio"])
        >= float(gate["minimum_block_coverage_ratio"]),
        "minimum_corrected_margin": float(row["median_block_corrected_margin"])
        >= float(gate["minimum_median_corrected_margin"]),
        "harmful_fraction": harmful_fraction <= float(gate["maximum_harmful_block_fraction"]),
        "harmful_run": int(row["maximum_consecutive_harmful_blocks"])
        <= int(gate["maximum_consecutive_harmful_blocks"]),
    }


def _final_fallback_gate_facts(
    row: dict[str, Any], replay_gate: dict[str, Any], selection: dict[str, Any]
) -> dict[str, bool]:
    return {
        "geometry_only_tier": row["tier"] == "geometry_only",
        "geometry_display": bool(row["geometry_display_eligible"]),
        "minimum_probes": int(row["evaluated_probe_count"])
        >= int(replay_gate["minimum_probe_count"]),
        "minimum_coverage": float(row["block_coverage_ratio"])
        >= float(replay_gate["minimum_block_coverage_ratio"]),
        "zero_harmful_blocks": int(row["harmful_block_count"]) == 0,
        "zero_maximum_harmful_run": int(row["maximum_consecutive_harmful_blocks"]) == 0,
        "minimum_corrected_margin": float(row["median_block_corrected_margin"])
        >= float(selection["minimum_corrected_margin"]),
    }


def _audit_only_fallback_gate_facts(
    row: dict[str, Any], replay_gate: dict[str, Any], minimum_corrected_margin: float = 0.0025
) -> dict[str, bool]:
    """Evaluate V3 final-selection evidence; harmful values are intentionally absent."""

    return {
        "geometry_only_tier": row["tier"] == "geometry_only",
        "geometry_display": bool(row["geometry_display_eligible"]),
        "minimum_probes": int(row["evaluated_probe_count"])
        >= int(replay_gate["minimum_probe_count"]),
        "minimum_coverage": float(row["block_coverage_ratio"])
        >= float(replay_gate["minimum_block_coverage_ratio"]),
        "minimum_corrected_margin": float(row["median_block_corrected_margin"])
        >= minimum_corrected_margin,
    }


def _audit_only_selected_rows(replay: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    rows_by_branch: dict[str, list[dict[str, Any]]] = {}
    for row in replay["rows"]:
        rows_by_branch.setdefault(str(row["branch_id"]), []).append(row)
    for branch_id in sorted(rows_by_branch):
        rows = rows_by_branch[branch_id]
        automatic = [row for row in rows if row["automatic_correction_eligible"]]
        if automatic:
            selected.extend(automatic)
            continue
        eligible = [
            row
            for row in rows
            if all(_audit_only_fallback_gate_facts(row, replay["gate_config"]).values())
        ]
        if eligible:
            selected.append(
                min(
                    eligible,
                    key=lambda row: (
                        -float(row["median_block_corrected_margin"]),
                        abs(int(row["alias_index"])),
                        int(row["alias_index"]),
                        str(row["canonical_model_id"]),
                    ),
                )
            )
    return sorted(selected, key=lambda row: (row["branch_id"], row["alias_index"]))


def build_facts(
    pilot: dict[str, Any],
    raw: dict[str, Any],
    dealiased: dict[str, Any],
    replay: dict[str, Any],
    final: dict[str, Any],
    prefixes: tuple[str, ...] = TARGET_PREFIXES,
) -> dict[str, Any]:
    branch_by_id = {row["branch_id"]: row for row in dealiased["branches"]}
    replay_by_id = {row["branch_id"]: row for row in replay["rows"]}
    final_by_id = {row["branch_id"]: row for row in final["trajectories"]}
    disposition_by_branch = {row["output_branch_id"]: row for row in dealiased["seed_dispositions"]}
    raw_ids = {row["trajectory_id"] for row in raw["trajectories"]}
    targets: list[dict[str, Any]] = []
    after_rows = _audit_only_selected_rows(replay)
    after_ids = {row["branch_id"] for row in after_rows}
    for prefix in prefixes:
        branch_id = _target_id(list(branch_by_id.values()), prefix)
        branch = branch_by_id[branch_id]
        row = replay_by_id[branch_id]
        disposition = disposition_by_branch[branch_id]
        replay_gates = _replay_gate_facts(row, replay["gate_config"])
        fallback_gates = _final_fallback_gate_facts(
            row, replay["gate_config"], final["selection_config"]
        )
        targets.append(
            {
                "branch_id": branch_id,
                "seed_trajectory_id": disposition["seed_trajectory_id"],
                "seed_present_in_raw_bank": disposition["seed_trajectory_id"] in raw_ids,
                "seed_source_observation_count": disposition["source_observation_count"],
                "dealiased_selected_probe_count": disposition["selected_probe_count"],
                "dealiased_branch_present": True,
                "dealiased_observation_count": len(branch["observation_ids"]),
                "dealiased_start_s": branch["start_s"],
                "dealiased_end_s": branch["end_s"],
                "replay_row_present": True,
                "replay_tier": row["tier"],
                "replay_automatic": row["automatic_correction_eligible"],
                "replay_geometry_display": row["geometry_display_eligible"],
                "replay_evaluated_probe_count": row["evaluated_probe_count"],
                "replay_evaluated_block_count": row["evaluated_block_count"],
                "replay_block_coverage_ratio": row["block_coverage_ratio"],
                "replay_median_corrected_margin": row["median_block_corrected_margin"],
                "replay_corrected_margin_floor": replay["gate_config"][
                    "minimum_median_corrected_margin"
                ],
                "replay_harmful_block_count": row["harmful_block_count"],
                "replay_maximum_consecutive_harmful_blocks": row[
                    "maximum_consecutive_harmful_blocks"
                ],
                "replay_reasons": row["reasons"],
                "replay_gate_pass": replay_gates,
                "final_fallback_gate_pass": fallback_gates,
                "final_present": branch_id in final_by_id,
                "audit_only_final_present": branch_id in after_ids,
                "audit_only_fallback_gate_pass": _audit_only_fallback_gate_facts(
                    row, replay["gate_config"]
                ),
                "final_trajectory_id": (
                    final_by_id[branch_id]["trajectory_id"] if branch_id in final_by_id else None
                ),
                "stop_gate": (
                    None
                    if branch_id in final_by_id
                    else "final_selection.zero_harmful_blocks_and_run"
                    if not fallback_gates["zero_harmful_blocks"]
                    and not fallback_gates["zero_maximum_harmful_run"]
                    else "final_selection.zero_harmful_blocks"
                    if not fallback_gates["zero_harmful_blocks"]
                    else "final_selection.other"
                ),
            }
        )
    return {
        "fixed_axes": {"time_s": list(X_LIMIT_S), "cfo_hz": list(Y_LIMIT_HZ)},
        "funnel": {
            "pilot_detections": len(pilot["detections"]),
            "raw_glrt64_candidates": sum(
                1
                for detection in pilot["detections"]
                for candidate in detection["candidates"]
                if any(score["method"] == "glrt64" for score in candidate["scores"])
            ),
            "raw_fitted_trajectories": len(raw["trajectories"]),
            "raw_families": len(raw["families"]),
            "dealiased_source_branches": dealiased["source_branch_count"],
            "dealiased_returned_branches": dealiased["returned_branch_count"],
            "dealiased_truncated_branches": dealiased["truncated_branch_count"],
            "replay_source_lifts": replay["source_lift_count"],
            "replay_returned_lifts": replay["returned_lift_count"],
            "replay_truncated_lifts": replay["truncated_lift_count"],
            "replay_automatic_lifts": len(replay["automatic_correction_lifts"]),
            "replay_geometry_display_lifts": len(replay["geometry_display_lifts"]),
            "final_selection_candidates": final["source_trajectory_count"],
            "final_returned_trajectories": final["returned_trajectory_count"],
            "final_automatic_trajectories": len(final["automatic_correction_trajectory_ids"]),
            "audit_only_final_selection_candidates": len(after_rows),
            "audit_only_final_returned_trajectories": len(after_rows),
            "audit_only_final_automatic_trajectories": sum(
                bool(row["automatic_correction_eligible"]) for row in after_rows
            ),
        },
        "selection_config": final["selection_config"],
        "targets": targets,
    }


def plot_policy_before_after(
    output: Path,
    pilot: dict[str, Any],
    dealiased: dict[str, Any],
    replay: dict[str, Any],
    final: dict[str, Any],
    facts: dict[str, Any],
) -> None:
    time, frequency = _raw_points(pilot)
    branches = {row["branch_id"]: row for row in dealiased["branches"]}
    target_ids = {row["branch_id"] for row in facts["targets"]}
    before = {row["branch_id"] for row in final["trajectories"]}
    after = {row["branch_id"] for row in _audit_only_selected_rows(replay)}
    colors = {"d049e4ed": "#2563eb", "2d370842": "#c026d3"}
    figure, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True, sharey=True)
    for axis in axes:
        _background(axis, time, frequency)
    for axis, retained, title in (
        (axes[0], before, "Before · final V2 zero-harmful fallback · 5/6 retained"),
        (axes[1], after, "After · final V3 audit-only harmful metrics · 6/6 retained"),
    ):
        for branch_id in sorted(target_ids):
            model_time, values = _model_values(_selected_model(branches[branch_id]))
            present = branch_id in retained
            axis.plot(
                model_time,
                values / 1_000.0,
                color=colors[_short(branch_id)] if present else "#dc2626",
                linewidth=3 if present else 1.5,
                linestyle="--" if present else ":",
                label=f"{_short(branch_id)} {'retained' if present else 'vetoed'}",
            )
        axis.set_title(title, loc="left")
        axis.legend(loc="upper right")
    axes[1].set_xlabel("Time from capture start (s)")
    figure.suptitle("405bcced8e67 · stream-0/RX1 · fixed 0–60 s and ±520 kHz", fontsize=16)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(output, dpi=170)
    plt.close(figure)


def _background(axis: Any, time: np.ndarray, frequency: np.ndarray) -> None:
    axis.scatter(time, frequency / 1_000.0, s=2, alpha=0.1, color="#7c8794", rasterized=True)
    axis.set_xlim(*X_LIMIT_S)
    axis.set_ylim(Y_LIMIT_HZ[0] / 1_000.0, Y_LIMIT_HZ[1] / 1_000.0)
    axis.set_ylabel("CFO (kHz)")
    axis.grid(alpha=0.18)


def plot_funnel(
    output: Path,
    pilot: dict[str, Any],
    raw: dict[str, Any],
    dealiased: dict[str, Any],
    replay: dict[str, Any],
    final: dict[str, Any],
    facts: dict[str, Any],
) -> None:
    time, frequency = _raw_points(pilot)
    branch_by_id = {row["branch_id"]: row for row in dealiased["branches"]}
    raw_by_id = {row["trajectory_id"]: row for row in raw["trajectories"]}
    target_ids = {row["branch_id"] for row in facts["targets"]}
    colors = {next(row for row in target_ids if _short(row) == "d049e4ed"): "#2563eb"}
    colors.update({row: "#c026d3" for row in target_ids if _short(row) == "2d370842"})
    figure, axes = plt.subplots(4, 1, figsize=(16, 19), sharex=True, sharey=True)
    for axis in axes:
        _background(axis, time, frequency)

    for fact in facts["targets"]:
        model = raw_by_id[fact["seed_trajectory_id"]]
        model_time, values = _model_values(model)
        axes[0].plot(
            model_time,
            values / 1_000.0,
            color=colors[fact["branch_id"]],
            linewidth=3,
            label=f"seed {_short(fact['seed_trajectory_id'])} → {_short(fact['branch_id'])}",
        )
    axes[0].set_title(
        f"A · raw CFO: {len(raw['trajectories'])} fits / {len(raw['families'])} families; "
        "target seeds highlighted",
        loc="left",
    )
    axes[0].legend(loc="upper right")

    for branch_id in sorted(target_ids):
        model_time, values = _model_values(_selected_model(branch_by_id[branch_id]))
        axes[1].plot(
            model_time,
            values / 1_000.0,
            color=colors[branch_id],
            linewidth=3,
            label=f"branch {_short(branch_id)}",
        )
    axes[1].set_title(
        "B · seeded de-aliased V3: both targets present "
        f"({dealiased['returned_branch_count']}/{dealiased['source_branch_count']} "
        "branches returned)",
        loc="left",
    )
    axes[1].legend(loc="upper right")

    for row in replay["rows"]:
        if row["branch_id"] not in target_ids:
            continue
        model_time, values = _model_values(_selected_model(branch_by_id[row["branch_id"]]))
        axes[2].plot(
            model_time,
            values / 1_000.0,
            color=colors[row["branch_id"]],
            linewidth=3,
            linestyle="--",
            label=(
                f"{_short(row['branch_id'])}: {row['tier']}, "
                f"margin={row['median_block_corrected_margin']:.4f}"
            ),
        )
    axes[2].set_title(
        "C · Replay V3: both targets retained as displayable geometry-only", loc="left"
    )
    axes[2].legend(loc="upper right")

    final_by_branch = {row["branch_id"]: row for row in final["trajectories"]}
    for branch_id in sorted(target_ids):
        branch = branch_by_id[branch_id]
        model_time, values = _model_values(_selected_model(branch))
        retained = branch_id in final_by_branch
        axes[3].plot(
            model_time,
            values / 1_000.0,
            color=colors[branch_id] if retained else "#dc2626",
            linewidth=3 if retained else 1.5,
            linestyle="--" if retained else ":",
            alpha=1.0 if retained else 0.9,
            label=(
                f"{_short(branch_id)} retained display-only"
                if retained
                else f"{_short(branch_id)} removed: nonzero harmful blocks"
            ),
        )
    axes[3].set_title("D · final V2 selection: d049e4ed retained; 2d370842 removed", loc="left")
    axes[3].legend(loc="upper right")
    axes[3].set_xlabel("Time from capture start (s)")
    figure.suptitle("405bcced8e67 · stream-0/RX1 · fixed 0–60 s and ±520 kHz", fontsize=16)
    figure.tight_layout(rect=(0, 0, 1, 0.98))
    figure.savefig(output, dpi=170)
    plt.close(figure)


def plot_replay_evidence(output: Path, replay: dict[str, Any], facts: dict[str, Any]) -> None:
    target_ids = {row["branch_id"] for row in facts["targets"]}
    rows = [row for row in replay["rows"] if row["branch_id"] in target_ids]
    colors = {"d049e4ed": "#2563eb", "2d370842": "#c026d3"}
    all_indices = [block["block_index"] for row in rows for block in row["blocks"]]
    x_limit = (min(all_indices) - 0.5, max(all_indices) + 0.5)
    figure, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    for row in rows:
        prefix = _short(row["branch_id"])
        indices = [block["block_index"] for block in row["blocks"]]
        corrected = [block["median_corrected_margin"] for block in row["blocks"]]
        delta = [block["median_margin_delta"] for block in row["blocks"]]
        axes[0].plot(indices, corrected, "o-", color=colors[prefix], label=prefix)
        axes[1].plot(indices, delta, "o-", color=colors[prefix], label=prefix)
    axes[0].axhline(
        replay["gate_config"]["minimum_median_corrected_margin"],
        color="#15803d",
        linestyle="--",
        label="Replay automatic median floor 0.05",
    )
    axes[0].set_xlim(*x_limit)
    axes[0].set_ylim(-0.01, 0.43)
    axes[0].set_ylabel("Corrected exact-control margin")
    axes[0].grid(alpha=0.2)
    axes[0].legend(ncol=3)
    axes[1].axhline(
        replay["gate_config"]["harmful_block_delta"],
        color="#dc2626",
        linestyle="--",
        label="Harmful-block threshold −0.02",
    )
    axes[1].set_xlim(*x_limit)
    axes[1].set_ylim(-0.40, 0.02)
    axes[1].set_xlabel("One-second block index")
    axes[1].set_ylabel("Corrected − independent margin")
    axes[1].grid(alpha=0.2)
    axes[1].legend(ncol=3)
    figure.suptitle("Replay V3 block evidence · fixed block and evidence axes")
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(output, dpi=170)
    plt.close(figure)


def main() -> int:
    args = arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    verified = _verify(args.artifacts_root, args.expected_sha256)
    pilot = _read(args.artifacts_root / "standard.pilot-scan.v3.json")
    raw = _read(args.artifacts_root / "standard.trajectory-bank.v2.json")
    dealiased = _read(args.artifacts_root / "standard.dealiased-trajectory-bank.v3.json")
    replay = _read(args.artifacts_root / "standard.cfo-lift-replay.v3.json")
    final = _read(args.artifacts_root / "standard.final-trajectory-bank.v2.json")
    prefixes = tuple(args.target_prefixes or TARGET_PREFIXES)
    facts = build_facts(pilot, raw, dealiased, replay, final, prefixes)
    facts["verified_artifact_digests"] = verified
    (args.output_root / "facts.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plot_funnel(
        args.output_root / "stream-0-rx1-fixed-axis-funnel.png",
        pilot,
        raw,
        dealiased,
        replay,
        final,
        facts,
    )
    plot_replay_evidence(args.output_root / "target-replay-block-evidence.png", replay, facts)
    plot_policy_before_after(
        args.output_root / "stream-0-rx1-policy-before-after.png",
        pilot,
        dealiased,
        replay,
        final,
        facts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
