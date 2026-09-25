#!/usr/bin/env python3
"""Ablate PSS support and carrier precision in conditional TLE identification.

This is a candidate-ranking experiment, not an identity declaration.  Track
selection is frozen upstream without TLE or PSS identity information.  Every
arm uses the same causal catalogue, conditional observer, chronological folds,
and constant-CFO nuisance model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import MINIMUM_PLAUSIBLE_ALTITUDE_KM, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset

SESSION_ID = "scan-fw-d6704a759a9ec176"
FIRST_SAMPLE_UTC_NS = 1_790_343_002_110_006_009
CAUSAL_CLEARANCE_NS = 500_000_000_000
TRAIN_FRACTION = 0.60
SITE_NAME = "spinnaker-sausalito"
GLRT_RF_HZ = {4: 10_940_000_000.0, 5: 11_190_000_000.0, 7: 11_690_000_000.0}
PSS_RF_HZ = {4: 10_825_117_187.5, 5: 11_075_117_187.5, 7: 11_575_117_187.5}


def arguments() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, default=here)
    parser.add_argument("--glrt", type=Path, default=here / "glrt-all-points.json")
    parser.add_argument(
        "--precision",
        type=Path,
        default=here.parent / "2026_09_25_pss_precision_lock" / "precision-lock-points.csv",
    )
    return parser.parse_args()


def iso_utc(utc_ns: int) -> str:
    seconds, nanoseconds = divmod(utc_ns, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return prefix + f".{nanoseconds:09d}Z"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def grid(times_s: np.ndarray) -> SamplingGrid:
    utc = tuple(FIRST_SAMPLE_UTC_NS + round(float(value) * 1e9) for value in times_s)
    spacing = float(np.median(np.diff(times_s))) if len(times_s) > 1 else 0.001
    return SamplingGrid(utc_ns=utc, anchor_index=len(utc) // 2, spacing_s=spacing)


def fold_scores(observed: np.ndarray, predictions: np.ndarray, train: np.ndarray) -> dict:
    residual = observed[None, :] - predictions
    offsets = np.mean(residual[:, train], axis=1)
    centered = residual - offsets[:, None]
    evaluation = ~train
    train_rms = np.sqrt(np.mean(centered[:, train] ** 2, axis=1))
    holdout_rms = np.sqrt(np.mean(centered[:, evaluation] ** 2, axis=1))
    order = np.argsort(train_rms, kind="stable")
    null_offset = float(np.mean(observed[train]))
    null_holdout_rms = float(np.sqrt(np.mean((observed[evaluation] - null_offset) ** 2)))
    return {
        "order": order,
        "train_rms": train_rms,
        "holdout_rms": holdout_rms,
        "null_holdout_rms": null_holdout_rms,
        "offsets": offsets,
    }


def score_arm(
    *,
    arm: str,
    times_s: np.ndarray,
    observed_hz: np.ndarray,
    prediction_hz: np.ndarray,
    candidate_indices: np.ndarray,
    catalogue,
) -> dict:
    order = np.argsort(times_s, kind="stable")
    times_s = times_s[order]
    observed_hz = observed_hz[order]
    prediction_hz = prediction_hz[:, order]
    count = len(times_s)
    training_count = math.ceil(TRAIN_FRACTION * count)
    indexes = np.arange(count)
    folds = []
    ledgers = []
    for label, train in (
        ("forward", indexes < training_count),
        ("reverse", indexes >= count - training_count),
    ):
        scored = fold_scores(observed_hz, prediction_hz, train)
        ranked = scored["order"]
        best_row, runner_row = int(ranked[0]), int(ranked[1])
        best_index = int(candidate_indices[best_row])
        runner_index = int(candidate_indices[runner_row])
        best_train = float(scored["train_rms"][best_row])
        best_holdout = float(scored["holdout_rms"][best_row])
        runner_train = float(scored["train_rms"][runner_row])
        null_holdout = float(scored["null_holdout_rms"])
        folds.append(
            {
                "fold": label,
                "train_count": int(np.count_nonzero(train)),
                "holdout_count": int(np.count_nonzero(~train)),
                "winner_norad": int(catalogue.satellite_numbers[best_index]),
                "winner_name": catalogue.names[best_index],
                "winner_train_rms_hz": best_train,
                "winner_holdout_rms_hz": best_holdout,
                "runner_norad": int(catalogue.satellite_numbers[runner_index]),
                "runner_name": catalogue.names[runner_index],
                "runner_train_rms_hz": runner_train,
                "runner_margin_hz": runner_train - best_train,
                "candidates_within_100_hz": int(
                    np.count_nonzero(scored["train_rms"] <= best_train + 100.0)
                ),
                "candidates_within_500_hz": int(
                    np.count_nonzero(scored["train_rms"] <= best_train + 500.0)
                ),
                "constant_cfo_null_holdout_rms_hz": null_holdout,
                "holdout_mse_gain_over_constant": float(1.0 - (best_holdout / null_holdout) ** 2),
            }
        )
        for rank, row in enumerate(ranked[:25], 1):
            catalogue_index = int(candidate_indices[int(row)])
            ledgers.append(
                {
                    "arm": arm,
                    "fold": label,
                    "rank": rank,
                    "norad": int(catalogue.satellite_numbers[catalogue_index]),
                    "name": catalogue.names[catalogue_index],
                    "train_rms_hz": float(scored["train_rms"][row]),
                    "holdout_rms_hz": float(scored["holdout_rms"][row]),
                }
            )
    return {
        "arm": arm,
        "point_count": count,
        "span_s": float(times_s[-1] - times_s[0]),
        "folds": folds,
        "same_winner_both_directions": folds[0]["winner_norad"] == folds[1]["winner_norad"],
        "quadratic_mean_selected_holdout_rms_hz": float(
            np.sqrt(np.mean([item["winner_holdout_rms_hz"] ** 2 for item in folds]))
        ),
        "median_runner_margin_hz": float(np.median([item["runner_margin_hz"] for item in folds])),
        "median_candidates_within_100_hz": float(
            np.median([item["candidates_within_100_hz"] for item in folds])
        ),
        "ledger": ledgers,
    }


def main() -> None:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    all_glrt = json.loads(args.glrt.read_text())
    precision = read_csv(args.precision)

    archive = TleArchiveReader(args.tle_root)
    snapshot = archive.select_latest_before(
        FIRST_SAMPLE_UTC_NS - CAUSAL_CLEARANCE_NS, provider="space-track"
    )
    catalogue = parse_element_sets(archive.read(snapshot))
    element_epochs = np.asarray(catalogue.element_epoch_utc_ns(), dtype=np.int64)

    union_times = np.asarray(
        sorted(
            {float(row["time_s"]) for row in all_glrt}
            | {float(row["time_s"]) for row in precision}
        ),
        dtype=float,
    )
    observation_grid = grid(union_times)
    sky = observe_grid(
        propagate_grid(catalogue, observation_grid),
        resolve_preset(SITE_NAME),
        observation_grid,
    )
    causal = element_epochs <= FIRST_SAMPLE_UTC_NS
    plausible = sky.usable & causal & (
        np.min(sky.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )

    time_lookup = {float(value): index for index, value in enumerate(union_times)}
    results = []
    all_ledger = []
    for track_rank in range(1, 6):
        glrt_rows = [row for row in all_glrt if int(row["track_rank"]) == track_rank]
        pss_rows = [row for row in precision if int(row["track_rank"]) == track_rank]
        target_index = int(glrt_rows[0]["target_index"])
        full_times = np.asarray([float(row["time_s"]) for row in glrt_rows])
        full_positions = np.asarray([time_lookup[float(value)] for value in full_times])
        visible = plausible & (np.max(sky.elevation_deg[:, full_positions], axis=1) > 0.0)
        candidates = np.flatnonzero(visible)
        track_result = {
            "track_rank": track_rank,
            "target_index": target_index,
            "visible_candidate_count": int(len(candidates)),
            "arms": [],
        }
        arms = [
            (
                "glrt_all",
                full_times,
                np.asarray([float(row["cfo_hz"]) for row in glrt_rows]),
                GLRT_RF_HZ[target_index],
            )
        ]
        if pss_rows:
            pss_times = np.asarray([float(row["time_s"]) for row in pss_rows])
            arms.extend(
                [
                    (
                        "glrt_pss_gated",
                        pss_times,
                        np.asarray([float(row["glrt_cfo_hz"]) for row in pss_rows]),
                        GLRT_RF_HZ[target_index],
                    ),
                    (
                        "pss_precise",
                        pss_times,
                        np.asarray([float(row["precise_pss_cfo_hz"]) for row in pss_rows]),
                        PSS_RF_HZ[target_index],
                    ),
                ]
            )
        for arm_name, times, observed, rf_hz in arms:
            positions = np.asarray([time_lookup[float(value)] for value in times])
            predicted = np.asarray(
                doppler_shift_hz(rf_hz, sky.range_rate_km_s[candidates][:, positions]), dtype=float
            )
            scored = score_arm(
                arm=arm_name,
                times_s=times,
                observed_hz=observed,
                prediction_hz=predicted,
                candidate_indices=candidates,
                catalogue=catalogue,
            )
            all_ledger.extend({"track_rank": track_rank, **row} for row in scored.pop("ledger"))
            track_result["arms"].append(scored)
        results.append(track_result)

    recovered = [item for item in results if len(item["arms"]) == 3]
    summaries = {}
    for arm_name in ("glrt_all", "glrt_pss_gated", "pss_precise"):
        arms = [next(arm for arm in track["arms"] if arm["arm"] == arm_name) for track in recovered]
        summaries[arm_name] = {
            "track_count": len(arms),
            "stable_winner_count": sum(arm["same_winner_both_directions"] for arm in arms),
            "median_selected_holdout_rms_hz": float(
                np.median([arm["quadratic_mean_selected_holdout_rms_hz"] for arm in arms])
            ),
            "median_runner_margin_hz": float(
                np.median([arm["median_runner_margin_hz"] for arm in arms])
            ),
            "median_candidates_within_100_hz": float(
                np.median([arm["median_candidates_within_100_hz"] for arm in arms])
            ),
        }
    baseline = summaries["glrt_all"]
    for arm_name in ("glrt_pss_gated", "pss_precise"):
        item = summaries[arm_name]
        item["holdout_rms_change_vs_glrt_all_fraction"] = float(
            1.0
            - item["median_selected_holdout_rms_hz"]
            / baseline["median_selected_holdout_rms_hz"]
        )
        item["runner_margin_ratio_vs_glrt_all"] = float(
            item["median_runner_margin_hz"] / baseline["median_runner_margin_hz"]
        )

    output = {
        "schema_version": "org.leo.research.pss-identification-gain/v1",
        "source": {
            "session_id": SESSION_ID,
            "first_sample_estimate_utc": iso_utc(FIRST_SAMPLE_UTC_NS),
            "first_sample_bracket_width_ms": 363.719394,
            "glrt_points_sha256": "sha256:" + sha256(args.glrt),
            "precision_points_sha256": "sha256:" + sha256(args.precision),
            "tle_provider": snapshot.provider,
            "tle_collected_utc": iso_utc(snapshot.collected_utc_ns),
            "tle_age_at_first_sample_s": (FIRST_SAMPLE_UTC_NS - snapshot.collected_utc_ns) / 1e9,
            "tle_sha256": snapshot.digest,
            "conditional_site": SITE_NAME,
        },
        "method": {
            "arms": {
                "glrt_all": "all frozen GLRT track points",
                "glrt_pss_gated": (
                    "GLRT CFO only where the independently formed PSS timing track exists"
                ),
                "pss_precise": "inter-frame-phase refined PSS CFO on the same PSS support",
            },
            "catalogue": (
                "same causal Space-Track snapshot; elements causal to measurement; "
                "geometrically visible above 0 degrees during each GLRT arc"
            ),
            "fit": (
                "bidirectional chronological 60/40; one constant CFO offset fit on "
                "training; candidate selected on training only"
            ),
            "claim_boundary": (
                "conditional candidate-ranking ablation; no verified satellite labels "
                "and no identity claim"
            ),
        },
        "summary_recovered_tracks_2_to_5": summaries,
        "results": results,
    }
    (args.output / "summary.json").write_text(json.dumps(output, indent=2) + "\n")

    fields = [
        "track_rank",
        "arm",
        "fold",
        "rank",
        "norad",
        "name",
        "train_rms_hz",
        "holdout_rms_hz",
    ]
    with (args.output / "candidate-ledger-top25.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_ledger)

    labels = ["GLRT all", "GLRT, PSS gated", "PSS precise"]
    arm_names = ["glrt_all", "glrt_pss_gated", "pss_precise"]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
    x = np.arange(2, 6)
    for label, arm_name in zip(labels, arm_names, strict=True):
        arms = [next(arm for arm in track["arms"] if arm["arm"] == arm_name) for track in recovered]
        axes[0].plot(
            x,
            [arm["quadratic_mean_selected_holdout_rms_hz"] for arm in arms],
            "o-",
            label=label,
        )
        axes[1].plot(
            x,
            [arm["median_candidates_within_100_hz"] for arm in arms],
            "o-",
            label=label,
        )
    axes[0].set_title("Selected candidate: held-out RMS", loc="left")
    axes[0].set_xlabel("frozen GLRT track rank")
    axes[0].set_ylabel("quadratic-mean bidirectional RMS (Hz)")
    axes[0].set_yscale("log")
    axes[1].set_title("Candidate ambiguity near the winner", loc="left")
    axes[1].set_xlabel("frozen GLRT track rank")
    axes[1].set_ylabel("median candidates within +100 Hz training RMS")
    axes[1].set_yscale("log")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    fig.suptitle("PSS satellite-candidate ablation · conditional site · no identity truth")
    fig.tight_layout()
    fig.savefig(args.output / "pss-identification-gain.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
