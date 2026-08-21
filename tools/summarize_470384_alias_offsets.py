#!/usr/bin/env python3
"""Produce a bounded audit of the 470384 RX0 apparent CFO-alias pair."""

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

ALIAS_SPACING_HZ = 2_500_000 / 11
ALIAS_GATE_HZ = 2_500.0
X_LIMIT_S = (0.0, 60.0)
Y_LIMIT_HZ = (-520_000.0, 520_000.0)

LOWER_SEED_ID = "sha256:e86860c920fbb8e67820a90e9690021ca55c14f7be29f6d2d29ec45527ebab9a"
UPPER_EARLY_SEED_ID = "sha256:a9aab7e8452218052fbbf2c11735df3202a44d93873bc90370640a6fc8ab785b"
UPPER_LATE_SEED_ID = "sha256:e95d4aa2fa4a0a58079d8af9b9a9d867e91407dd0e29346136210a1b799b4d90"
LOWER_BRANCH_ID = "sha256:e7f9ee27318fb2e61ba6c1b92accabc3f15d5ad5ed90803c34e4971121964f59"
UPPER_EARLY_BRANCH_ID = "sha256:5852a9363eb59b0ebd3f20eb82fc21ef912f1eeeeb1af0c508609d8e1425af30"
UPPER_LATE_BRANCH_ID = "sha256:f1f9282120c94814c2d62016d04a9aa6d49c62fddd66af38a02b2a2314b9d5a9"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
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
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _verify(root: Path, rows: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for row in rows:
        name, separator, digest = row.partition("=")
        if not separator or not name or len(digest) != 64:
            raise ValueError(f"invalid --expected-sha256 value: {row!r}")
        expected[name] = digest
    actual = {name: _sha256(root / name) for name in expected}
    mismatches = sorted(name for name in expected if actual[name] != expected[name])
    if mismatches:
        raise ValueError(f"artifact digest mismatch: {', '.join(mismatches)}")
    return {name: f"sha256:{digest}" for name, digest in sorted(actual.items())}


def _short(identifier: str) -> str:
    return identifier.removeprefix("sha256:")[:8]


def _selected_model(branch: dict[str, Any]) -> dict[str, Any]:
    return next(
        model for model in branch["models"] if model["model_id"] == branch["selected_model_id"]
    )


def _model_frequency(model: dict[str, Any], time_s: np.ndarray | float) -> np.ndarray:
    time = np.asarray(time_s, dtype=float)
    return np.polyval(
        np.asarray(model["coefficients_hz"], dtype=float),
        time - float(model["reference_time_s"]),
    )


def _model_points(model: dict[str, Any], count: int = 300) -> tuple[np.ndarray, np.ndarray]:
    time = np.linspace(float(model["start_s"]), float(model["end_s"]), count)
    return time, _model_frequency(model, time)


def alias_pair_metrics(
    lower_model: dict[str, Any],
    upper_model: dict[str, Any],
    *,
    spacing_hz: float = ALIAS_SPACING_HZ,
    gate_hz: float = ALIAS_GATE_HZ,
    comparison_point_count: int = 128,
) -> dict[str, Any]:
    """Reproduce the persisted exact-spacing, maximum-residual pair rule."""

    overlap_start = max(float(lower_model["start_s"]), float(upper_model["start_s"]))
    overlap_end = min(float(lower_model["end_s"]), float(upper_model["end_s"]))
    if overlap_end <= overlap_start:
        raise ValueError("models do not overlap")
    time = np.linspace(overlap_start, overlap_end, comparison_point_count)
    gap = _model_frequency(upper_model, time) - _model_frequency(lower_model, time)
    alias_index = int(np.rint(float(np.median(gap)) / spacing_hz))
    residual = gap - alias_index * spacing_hz
    maximum = float(np.max(np.abs(residual)))
    return {
        "overlap_start_s": overlap_start,
        "overlap_end_s": overlap_end,
        "overlap_s": overlap_end - overlap_start,
        "alias_index_delta": alias_index,
        "gap_hz_start": float(gap[0]),
        "gap_hz_median": float(np.median(gap)),
        "gap_hz_end": float(gap[-1]),
        "residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "maximum_absolute_residual_hz": maximum,
        "minimum_gate_to_accept_hz": maximum,
        "configured_gate_hz": gate_hz,
        "gate_multiple_required": maximum / gate_hz,
        "accepted": maximum <= gate_hz,
    }


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum": float(np.min(values)),
        "q05": float(np.quantile(values, 0.05)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "q95": float(np.quantile(values, 0.95)),
        "maximum": float(np.max(values)),
        "standard_deviation": float(np.std(values)),
    }


def _raw_points(pilot: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    points = [
        (float(detection["time_s"]), float(score["tracking_cfo_hz"]))
        for detection in pilot["detections"]
        for candidate in detection["candidates"]
        for score in candidate["scores"]
        if score["method"] == "glrt64"
    ]
    return np.asarray([row[0] for row in points]), np.asarray([row[1] for row in points])


def _candidate_for_observation(
    detection: dict[str, Any], observation: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    choices = []
    for candidate in detection["candidates"]:
        score = next(item for item in candidate["scores"] if item["method"] == "glrt64")
        choices.append(
            (
                abs(float(score["tracking_cfo_hz"]) - float(observation["raw_cfo_hz"])),
                candidate,
                score,
            )
        )
    distance, candidate, score = min(choices, key=lambda item: item[0])
    if distance > 1e-6:
        raise ValueError("de-aliased observation is absent from the pilot candidate inventory")
    return candidate, score


def _matched_probe_rows(
    pilot: dict[str, Any], dealiased: dict[str, Any]
) -> list[dict[str, float | int]]:
    branches = {row["branch_id"]: row for row in dealiased["branches"]}
    observations = {row["observation_id"]: row for row in dealiased["observations"]}
    detections = {int(row["sample_start"]): row for row in pilot["detections"]}

    def by_sample(branch_id: str) -> dict[int, dict[str, Any]]:
        return {
            int(observations[identifier]["sample_start"]): observations[identifier]
            for identifier in branches[branch_id]["observation_ids"]
        }

    lower = by_sample(LOWER_BRANCH_ID)
    upper = by_sample(UPPER_EARLY_BRANCH_ID)
    rows: list[dict[str, float | int]] = []
    for sample_start in sorted(set(lower) & set(upper)):
        lower_candidate, lower_score = _candidate_for_observation(
            detections[sample_start], lower[sample_start]
        )
        upper_candidate, upper_score = _candidate_for_observation(
            detections[sample_start], upper[sample_start]
        )
        gap = float(upper[sample_start]["raw_cfo_hz"]) - float(lower[sample_start]["raw_cfo_hz"])
        rows.append(
            {
                "sample_start": sample_start,
                "time_s": float(lower[sample_start]["time_s"]),
                "lower_tracking_cfo_hz": float(lower[sample_start]["raw_cfo_hz"]),
                "upper_tracking_cfo_hz": float(upper[sample_start]["raw_cfo_hz"]),
                "tracking_gap_hz": gap,
                "alias_residual_hz": gap - ALIAS_SPACING_HZ,
                "lower_acquired_cfo_hz": float(lower_candidate["acquired_cfo_hz"]),
                "upper_acquired_cfo_hz": float(upper_candidate["acquired_cfo_hz"]),
                "lower_glrt_residual_cfo_hz": float(lower_score["residual_cfo_hz"]),
                "upper_glrt_residual_cfo_hz": float(upper_score["residual_cfo_hz"]),
                "lower_local_epoch_sample": int(lower_candidate["local_epoch_sample"]),
                "upper_local_epoch_sample": int(upper_candidate["local_epoch_sample"]),
                "lower_glrt_margin": float(lower_score["margin"]),
                "upper_glrt_margin": float(upper_score["margin"]),
                "lower_candidate_rank": int(lower_candidate["rank"]),
                "upper_candidate_rank": int(upper_candidate["rank"]),
            }
        )
    if not rows:
        raise ValueError("target branches have no same-probe overlap")
    return rows


def _same_probe_facts(rows: list[dict[str, float | int]]) -> dict[str, Any]:
    fields = (
        "tracking_gap_hz",
        "alias_residual_hz",
        "lower_acquired_cfo_hz",
        "upper_acquired_cfo_hz",
        "lower_glrt_residual_cfo_hz",
        "upper_glrt_residual_cfo_hz",
        "lower_glrt_margin",
        "upper_glrt_margin",
    )
    result = {field: _stats(np.asarray([float(row[field]) for row in rows])) for field in fields}
    lower_margin = np.asarray([float(row["lower_glrt_margin"]) for row in rows])
    upper_margin = np.asarray([float(row["upper_glrt_margin"]) for row in rows])
    half_spacing = ALIAS_SPACING_HZ / 2.0
    lower_residual = np.asarray([float(row["lower_glrt_residual_cfo_hz"]) for row in rows])
    upper_residual = np.asarray([float(row["upper_glrt_residual_cfo_hz"]) for row in rows])
    result.update(
        {
            "matched_probe_count": len(rows),
            "start_s": float(rows[0]["time_s"]),
            "end_s": float(rows[-1]["time_s"]),
            "upper_margin_win_count": int(np.count_nonzero(upper_margin > lower_margin)),
            "lower_margin_win_count": int(np.count_nonzero(lower_margin > upper_margin)),
            "lower_near_negative_glrt_wrap_count": int(
                np.count_nonzero(np.abs(lower_residual + half_spacing) <= 5_000.0)
            ),
            "upper_near_positive_glrt_wrap_count": int(
                np.count_nonzero(np.abs(upper_residual - half_spacing) <= 5_000.0)
            ),
        }
    )
    return result


def _replay_facts(replay: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    replay_by_id = {row["branch_id"]: row for row in replay["rows"]}
    final_ids = {row["branch_id"] for row in final["trajectories"]}
    result = {}
    for name, branch_id in (
        ("lower", LOWER_BRANCH_ID),
        ("upper_early", UPPER_EARLY_BRANCH_ID),
        ("upper_late", UPPER_LATE_BRANCH_ID),
    ):
        row = replay_by_id[branch_id]
        result[name] = {
            "branch_id": branch_id,
            "tier": row["tier"],
            "automatic_correction_eligible": row["automatic_correction_eligible"],
            "geometry_display_eligible": row["geometry_display_eligible"],
            "evaluated_probe_count": row["evaluated_probe_count"],
            "evaluated_block_count": row["evaluated_block_count"],
            "median_block_corrected_margin": row["median_block_corrected_margin"],
            "median_block_margin_delta": row["median_block_margin_delta"],
            "harmful_block_count": row["harmful_block_count"],
            "maximum_consecutive_harmful_blocks": row["maximum_consecutive_harmful_blocks"],
            "present_in_final_bank": branch_id in final_ids,
        }
    return result


def build_facts(
    pilot: dict[str, Any],
    raw: dict[str, Any],
    alias_map: dict[str, Any],
    dealiased: dict[str, Any],
    replay: dict[str, Any],
    final: dict[str, Any],
) -> dict[str, Any]:
    representatives = {row["trajectory_id"]: row for row in raw["replayed_representatives"]}
    branches = {row["branch_id"]: row for row in dealiased["branches"]}
    decisions = {
        frozenset((row["left_trajectory_id"], row["right_trajectory_id"])): row
        for row in alias_map["pair_decisions"]
    }
    pair_key = frozenset((LOWER_SEED_ID, UPPER_EARLY_SEED_ID))
    persisted_pair = decisions[pair_key]
    reproduced_pair = alias_pair_metrics(
        representatives[LOWER_SEED_ID], representatives[UPPER_EARLY_SEED_ID]
    )
    matched_rows = _matched_probe_rows(pilot, dealiased)
    upper_fragment_pair = alias_pair_metrics(
        representatives[UPPER_EARLY_SEED_ID], representatives[UPPER_LATE_SEED_ID]
    )
    upper_seeded_pair = alias_pair_metrics(
        _selected_model(branches[UPPER_EARLY_BRANCH_ID]),
        _selected_model(branches[UPPER_LATE_BRANCH_ID]),
    )
    return {
        "alias_spacing_hz": ALIAS_SPACING_HZ,
        "alias_half_spacing_hz": ALIAS_SPACING_HZ / 2.0,
        "alias_gate_hz": ALIAS_GATE_HZ,
        "funnel": {
            "pilot_detection_count": len(pilot["detections"]),
            "raw_glrt64_candidate_count": sum(
                1
                for detection in pilot["detections"]
                for candidate in detection["candidates"]
                if any(score["method"] == "glrt64" for score in candidate["scores"])
            ),
            "raw_trajectory_count": len(raw["trajectories"]),
            "raw_family_count": len(raw["families"]),
            "alias_component_count": alias_map["component_count"],
            "alias_equivalent_pair_count": sum(
                row["status"] == "alias_equivalent" for row in alias_map["pair_decisions"]
            ),
            "dealiased_source_branch_count": dealiased["source_branch_count"],
            "dealiased_returned_branch_count": dealiased["returned_branch_count"],
            "dealiased_truncated_branch_count": dealiased["truncated_branch_count"],
            "replay_source_lift_count": replay["source_lift_count"],
            "replay_returned_lift_count": replay["returned_lift_count"],
            "final_returned_trajectory_count": final["returned_trajectory_count"],
        },
        "apparent_alias_pair": {
            "lower_seed_id": LOWER_SEED_ID,
            "upper_seed_id": UPPER_EARLY_SEED_ID,
            "lower_branch_id": LOWER_BRANCH_ID,
            "upper_branch_id": UPPER_EARLY_BRANCH_ID,
            "persisted_decision": persisted_pair,
            "reproduced_model_comparison": reproduced_pair,
            "same_probe": _same_probe_facts(matched_rows),
        },
        "matched_probe_rows": matched_rows,
        "replay": _replay_facts(replay, final),
        "upper_fragmentation": {
            "early_seed_id": UPPER_EARLY_SEED_ID,
            "late_seed_id": UPPER_LATE_SEED_ID,
            "early_branch_id": UPPER_EARLY_BRANCH_ID,
            "late_branch_id": UPPER_LATE_BRANCH_ID,
            "raw_model_comparison": upper_fragment_pair,
            "seeded_model_comparison": upper_seeded_pair,
            "both_automatic_and_final": all(
                item["automatic_correction_eligible"] and item["present_in_final_bank"]
                for item in _replay_facts(replay, final).values()
                if item["branch_id"] in {UPPER_EARLY_BRANCH_ID, UPPER_LATE_BRANCH_ID}
            ),
        },
        "fixed_axes": {"time_s": list(X_LIMIT_S), "cfo_hz": list(Y_LIMIT_HZ)},
    }


def _background(axis: Any, time: np.ndarray, frequency: np.ndarray) -> None:
    axis.scatter(time, frequency / 1_000.0, s=2, alpha=0.09, color="#7c8794", rasterized=True)
    axis.set_xlim(*X_LIMIT_S)
    axis.set_ylim(Y_LIMIT_HZ[0] / 1_000.0, Y_LIMIT_HZ[1] / 1_000.0)
    axis.set_ylabel("CFO (kHz)")
    axis.grid(alpha=0.18)


def plot_stage_audit(
    output: Path,
    pilot: dict[str, Any],
    raw: dict[str, Any],
    dealiased: dict[str, Any],
    final: dict[str, Any],
) -> None:
    time, frequency = _raw_points(pilot)
    representatives = {row["trajectory_id"]: row for row in raw["replayed_representatives"]}
    branches = {row["branch_id"]: row for row in dealiased["branches"]}
    colors = {
        LOWER_BRANCH_ID: "#c026d3",
        UPPER_EARLY_BRANCH_ID: "#2563eb",
        UPPER_LATE_BRANCH_ID: "#f97316",
    }
    seeds = {
        LOWER_BRANCH_ID: LOWER_SEED_ID,
        UPPER_EARLY_BRANCH_ID: UPPER_EARLY_SEED_ID,
        UPPER_LATE_BRANCH_ID: UPPER_LATE_SEED_ID,
    }
    figure, axes = plt.subplots(3, 1, figsize=(16, 13), sharex=True, sharey=True)
    for axis in axes:
        _background(axis, time, frequency)
    for branch_id, seed_id in seeds.items():
        model_time, values = _model_points(representatives[seed_id])
        axes[0].plot(
            model_time,
            values / 1_000.0,
            color=colors[branch_id],
            linewidth=2.8,
            label=f"seed {_short(seed_id)}",
        )
    axes[0].set_title(
        "A · first hard-EM representatives: lower ridge and two upper fragments",
        loc="left",
    )
    axes[0].legend(loc="lower left", ncol=3)

    for branch_id, branch in branches.items():
        model_time, values = _model_points(_selected_model(branch))
        target = branch_id in colors
        axes[1].plot(
            model_time,
            values / 1_000.0,
            color=colors.get(branch_id, "#8b95a1"),
            linewidth=2.8 if target else 1.4,
            linestyle="--" if target else ":",
            alpha=1.0 if target else 0.8,
            label=f"branch {_short(branch_id)}" if target else None,
        )
    axes[1].set_title(
        "B · seeded de-aliased V3: exact-spacing pair rejected; one branch retained per seed",
        loc="left",
    )
    axes[1].legend(loc="lower left", ncol=3)

    for row in final["trajectories"]:
        branch_id = row["branch_id"]
        branch = branches[branch_id]
        model_time, values = _model_points(_selected_model(branch))
        axes[2].plot(
            model_time,
            values / 1_000.0,
            color=colors.get(branch_id, "#475467"),
            linewidth=3.0,
            label=f"final {_short(branch_id)} · {row['replay_tier']}",
        )
    lower_time, lower_values = _model_points(_selected_model(branches[LOWER_BRANCH_ID]))
    axes[2].plot(
        lower_time,
        lower_values / 1_000.0,
        color="#dc2626",
        linestyle=":",
        linewidth=1.8,
        label="e7f9ee27 removed after harmful replay",
    )
    axes[2].set_title(
        "C · final V2: lower ghost removed; two automatic upper seed fragments remain",
        loc="left",
    )
    axes[2].legend(loc="lower left", ncol=3)
    axes[2].set_xlabel("Time from capture start (s)")
    figure.suptitle(
        "470384cc9284 · radio_pluto_5d4d · stream-0/RX0 · fixed 0–60 s and ±520 kHz",
        fontsize=15,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(output, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def plot_alias_diagnostics(
    output: Path,
    raw: dict[str, Any],
    replay: dict[str, Any],
    facts: dict[str, Any],
) -> None:
    representatives = {row["trajectory_id"]: row for row in raw["replayed_representatives"]}
    rows = facts["matched_probe_rows"]
    time = np.asarray([float(row["time_s"]) for row in rows])
    lower = np.asarray([float(row["lower_tracking_cfo_hz"]) for row in rows])
    upper = np.asarray([float(row["upper_tracking_cfo_hz"]) for row in rows])
    residual = np.asarray([float(row["alias_residual_hz"]) for row in rows])
    lower_glrt = np.asarray([float(row["lower_glrt_residual_cfo_hz"]) for row in rows])
    upper_glrt = np.asarray([float(row["upper_glrt_residual_cfo_hz"]) for row in rows])
    lower_model = representatives[LOWER_SEED_ID]
    upper_model = representatives[UPPER_EARLY_SEED_ID]
    dense = np.linspace(time.min(), time.max(), 300)
    model_residual = (
        _model_frequency(upper_model, dense)
        - _model_frequency(lower_model, dense)
        - ALIAS_SPACING_HZ
    )

    figure, axes = plt.subplots(4, 1, figsize=(15, 16), sharex=False)
    axes[0].scatter(time, lower / 1_000.0, s=22, color="#c026d3", label="lower e7f9ee27")
    axes[0].scatter(time, upper / 1_000.0, s=22, color="#2563eb", label="upper 5852a936")
    axes[0].plot(dense, _model_frequency(lower_model, dense) / 1_000.0, color="#c026d3")
    axes[0].plot(dense, _model_frequency(upper_model, dense) / 1_000.0, color="#2563eb")
    axes[0].set_ylabel("Tracking CFO (kHz)")
    axes[0].set_title(
        "A · simultaneous fitted ridges look approximately one symbol rate apart",
        loc="left",
    )
    axes[0].legend()
    axes[0].grid(alpha=0.2)

    half = ALIAS_SPACING_HZ / 2.0
    axes[1].scatter(time, lower_glrt / 1_000.0, s=22, color="#c026d3", label="lower GLRT residual")
    axes[1].scatter(time, upper_glrt / 1_000.0, s=22, color="#2563eb", label="upper GLRT residual")
    axes[1].axhline(-half / 1_000.0, color="#c026d3", linestyle="--", linewidth=1)
    axes[1].axhline(half / 1_000.0, color="#2563eb", linestyle="--", linewidth=1)
    axes[1].set_ylim(-125, 125)
    axes[1].set_ylabel("GLRT residual CFO (kHz)")
    axes[1].set_title("B · GLRT-64 residual estimates straddle the ±1/(2T) FFT wrap", loc="left")
    axes[1].legend(ncol=2)
    axes[1].grid(alpha=0.2)

    axes[2].scatter(time, residual / 1_000.0, s=24, color="#7c3aed", label="same-probe residual")
    axes[2].plot(
        dense,
        model_residual / 1_000.0,
        color="black",
        linewidth=2,
        label="persisted model residual",
    )
    axes[2].axhspan(-2.5, 2.5, color="#16a34a", alpha=0.14, label="accepted ±2.5 kHz")
    axes[2].axhline(0.0, color="#475467", linewidth=0.8)
    axes[2].set_ylabel("(upper − lower − 1/T) (kHz)")
    axes[2].set_title(
        "C · exact symbol-rate lift misses by ≈6.6 kHz, outside the alias gate",
        loc="left",
    )
    axes[2].legend(ncol=3)
    axes[2].grid(alpha=0.2)

    replay_by_id = {row["branch_id"]: row for row in replay["rows"]}
    for branch_id, color, label in (
        (LOWER_BRANCH_ID, "#c026d3", "lower e7f9ee27"),
        (UPPER_EARLY_BRANCH_ID, "#2563eb", "upper 5852a936"),
    ):
        blocks = replay_by_id[branch_id]["blocks"]
        axes[3].plot(
            [row["block_index"] for row in blocks],
            [row["median_corrected_margin"] for row in blocks],
            "o-",
            color=color,
            label=label,
        )
    axes[3].axhline(
        replay["gate_config"]["minimum_median_corrected_margin"],
        color="#15803d",
        linestyle="--",
        label="automatic absolute-margin floor",
    )
    axes[3].set_xlabel("One-second replay block index")
    axes[3].set_ylabel("Corrected exact − control margin")
    axes[3].set_title(
        "D · same-IQ replay independently supports the upper lift and falsifies the lower",
        loc="left",
    )
    axes[3].legend(ncol=3)
    axes[3].grid(alpha=0.2)
    figure.suptitle(
        "Why the apparent alias pair does not collapse · candidate-only diagnostic",
        fontsize=15,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.975))
    figure.savefig(output, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> int:
    args = arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    verified = _verify(args.artifacts_root, args.expected_sha256)
    pilot = _read(args.artifacts_root / "standard.pilot-scan.v3.json")
    raw = _read(args.artifacts_root / "standard.trajectory-bank.v2.json")
    alias_map = _read(args.artifacts_root / "standard.cfo-alias-map.v2.json")
    dealiased = _read(args.artifacts_root / "standard.dealiased-trajectory-bank.v3.json")
    replay = _read(args.artifacts_root / "standard.cfo-lift-replay.v3.json")
    final = _read(args.artifacts_root / "standard.final-trajectory-bank.v2.json")
    facts = build_facts(pilot, raw, alias_map, dealiased, replay, final)
    facts["verified_artifact_digests"] = verified
    (args.output_root / "facts.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plot_stage_audit(args.output_root / "fixed-axis-stage-audit.png", pilot, raw, dealiased, final)
    plot_alias_diagnostics(args.output_root / "alias-decision-diagnostics.png", raw, replay, facts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
