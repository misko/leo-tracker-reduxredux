#!/usr/bin/env python3
"""Diagnose strong partition-dependent identity changes at one frozen blind location.

This is a descriptive saved-data diagnostic.  It never reads a receiver reference
position and does not treat either candidate as satellite truth.
"""

# ruff: noqa: E402 -- bind numerical thread limits before NumPy/SciPy imports.

from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.propagation import parse_element_sets


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def content_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def replay_module():
    path = Path(__file__).parents[1] / "tools" / "replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("partition_identity_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("regional replay module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def partition_masks(count: int) -> dict[str, np.ndarray]:
    """Return full-data masks for the two frozen response-free partitions."""
    if count < 5:
        raise ValueError("at least five ordered observations are required")
    chronological = np.zeros(count, dtype=bool)
    chronological[: int(np.floor(0.6 * count))] = True
    blocks = np.array_split(np.arange(count), 5)
    five_block = np.zeros(count, dtype=bool)
    five_block[np.concatenate([blocks[index] for index in (0, 2, 4)])] = True
    for mask in (chronological, five_block):
        if min(np.sum(mask), np.sum(~mask)) < 2:
            raise ValueError("partition needs at least two training and held-out observations")
    return {"chronological": chronological, "five_block": five_block}


def fitted_residuals(
    observed_hz: np.ndarray, predicted_hz: np.ndarray, training: np.ndarray
) -> dict[str, object]:
    """Fit one constant on training and score the unchanged full trajectory."""
    observed = np.asarray(observed_hz, dtype=float)
    predicted = np.asarray(predicted_hz, dtype=float)
    training = np.asarray(training)
    if (
        observed.ndim != 1
        or predicted.shape != observed.shape
        or training.shape != observed.shape
        or training.dtype != bool
        or min(np.sum(training), np.sum(~training)) < 1
        or not np.all(np.isfinite(observed))
        or not np.all(np.isfinite(predicted))
    ):
        raise ValueError("finite matching arrays and a valid training mask are required")
    offset = float(np.mean(observed[training] - predicted[training]))
    residual = observed - predicted - offset
    return {
        "offset_hz": offset,
        "training_rms_hz": float(np.sqrt(np.mean(np.square(residual[training])))),
        "heldout_rms_hz": float(np.sqrt(np.mean(np.square(residual[~training])))),
        "residual_hz": residual,
    }


def common_time_shape(
    first_time_s: np.ndarray,
    first_hz: np.ndarray,
    second_time_s: np.ndarray,
    second_hz: np.ndarray,
    *,
    points: int = 128,
) -> dict[str, object]:
    """Compare normalized demeaned shapes by interpolation only on common support."""
    first_time = np.asarray(first_time_s, dtype=float)
    second_time = np.asarray(second_time_s, dtype=float)
    first = np.asarray(first_hz, dtype=float)
    second = np.asarray(second_hz, dtype=float)
    if (
        points < 3
        or first_time.ndim != 1
        or second_time.ndim != 1
        or first.shape != first_time.shape
        or second.shape != second_time.shape
        or min(len(first), len(second)) < 2
        or np.any(np.diff(first_time) <= 0)
        or np.any(np.diff(second_time) <= 0)
    ):
        raise ValueError("ordered finite trajectories and at least three grid points are required")
    start = float(max(first_time[0], second_time[0]))
    stop = float(min(first_time[-1], second_time[-1]))
    if not start < stop:
        raise ValueError("trajectories have no common time support")
    grid = np.linspace(start, stop, points)
    values = []
    for time, observed in ((first_time, first), (second_time, second)):
        interpolated = np.interp(grid, time, observed)
        centered = interpolated - np.mean(interpolated)
        scale = float(np.sqrt(np.mean(np.square(centered))))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("trajectory has no finite shape variation")
        values.append(centered / scale)
    return {
        "common_start_s": start,
        "common_stop_s": stop,
        "grid_point_count": points,
        "correlation": float(np.corrcoef(values[0], values[1])[0, 1]),
        "normalized_rms_difference": float(
            np.sqrt(np.mean(np.square(values[0] - values[1])))
        ),
        "interpretation": (
            "descriptive gross observed-trajectory comparison on common support; dominated by "
            "common Doppler shape, not a residual-independence test, and the different channel "
            "paths are not paired-receiver evidence"
        ),
    }


def strong_changes(comparison: dict) -> list[dict]:
    if comparison.get("schema") != "joint-partition-association-comparison-v1":
        raise ValueError("unexpected association comparison schema")
    if not comparison.get("comparisons"):
        raise ValueError("association comparison has no comparisons")
    first = comparison["comparisons"][0]
    if first.get("left") != "chronological-set" or first.get("right") != "blocked-sac-set":
        raise ValueError("first comparison is not chronological versus five-block Sacramento")
    selected = [
        row
        for row in first["changed_candidate_leaders"]
        if row["left_norad"] is not None
        and row["right_norad"] is not None
        and row["left_weight"] >= 0.9
        and row["right_weight"] >= 0.9
    ]
    if len(selected) != 4:
        raise ValueError("expected exactly four strong contradictory associations")
    return selected


def verify_refinement(path: Path) -> dict:
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if path.with_name("result.sha256").read_text().strip() != checksum:
        raise ValueError("refinement checksum mismatch")
    result = json.loads(raw)
    seal_path = path.with_name("refinement-seal.json")
    seal = json.loads(seal_path.read_text())
    if (
        seal.get("result_digest") != "sha256:" + checksum
        or seal.get("position_truth_used") is not False
        or not seal.get("all_fits_converged")
        or not result.get("complete")
        or result.get("position_truth_used") is not False
        or not result.get("selected", {}).get("converged")
        or result.get("geometry_pair_factor_used") is not False
    ):
        raise ValueError("complete truth-free converged Doppler-only refinement required")
    return result


def source_trajectory(document: dict, episode_id: str) -> dict[str, object]:
    episodes = [row for row in document["episodes"] if row["episode_id"] == episode_id]
    if len(episodes) != 1 or len(episodes[0]["members"]) != 1:
        raise ValueError("diagnostic requires one exact receiver-local track per episode")
    tracklet_id = episodes[0]["members"][0]
    sources = [row for row in document["series"] if row["tracklet_id"] == tracklet_id]
    if len(sources) != 1:
        raise ValueError("episode source is absent or ambiguous")
    source = sources[0]
    times = np.asarray(source["t_s"], dtype=float)
    observed = np.asarray(source["y_hz"], dtype=float)
    identities = list(source["candidate_ids"])
    if (
        len(times) != len(observed)
        or len(times) != len(identities)
        or len(identities) != len(set(identities))
        or not np.all(np.isfinite(times))
        or not np.all(np.isfinite(observed))
    ):
        raise ValueError("invalid or duplicate source trajectory")
    order = np.argsort(times, kind="stable")
    return {
        "tracklet_id": tracklet_id,
        "receiver_id": int(source["receiver_id"]),
        "channel": int(source["channel"]),
        "actual_rf_hz": float(source["actual_rf_hz"]),
        "observation_id": [identities[index] for index in order],
        "source_group_id": [source["paired_visit_ids"][index] for index in order],
        "time_s": times[order],
        "observed_hz": observed[order],
    }


def exact_prediction(
    replay,
    catalogue,
    reference_utc_ns: int,
    time_s: np.ndarray,
    norad: int,
    receiver_ecef_km: np.ndarray,
) -> tuple[np.ndarray, int]:
    numbers = np.asarray(catalogue.satellite_numbers)
    found = np.flatnonzero(numbers == norad)
    if len(found) != 1:
        raise ValueError(f"NORAD {norad} is absent or duplicated in the causal catalogue")
    catalogue_index = int(found[0])
    if int(catalogue.element_epoch_utc_ns()[catalogue_index]) >= reference_utc_ns:
        raise ValueError("candidate element epoch is not causal")
    positions, velocities, retained = replay.state_arrays(
        catalogue, [catalogue_index], reference_utc_ns, time_s
    )
    if len(retained) != 1 or int(retained[0]) != catalogue_index:
        raise ValueError("candidate exact propagation failed")
    delta = positions[0] - receiver_ecef_km
    distance = np.linalg.norm(delta, axis=-1)
    prediction = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * velocities[0], axis=-1)
        / distance
    )
    if not np.all(np.isfinite(prediction)):
        raise ValueError("candidate prediction is non-finite")
    return prediction, int(catalogue.element_epoch_utc_ns()[catalogue_index])


def mask_digest(observation_ids: list[str], training: np.ndarray) -> str:
    return content_digest(
        [
            {"observation_id": identity, "partition": "training" if selected else "heldout"}
            for identity, selected in zip(observation_ids, training, strict=True)
        ]
    )


def plot_results(episodes: list[dict], output: Path) -> None:
    figure, axes = plt.subplots(4, 2, figsize=(14, 14), sharex=False, sharey=False)
    colors = {"chronological_leader": "#3569b7", "five_block_leader": "#db6b2d"}
    for row_index, episode in enumerate(episodes):
        time_s = np.asarray(episode["time_s"], dtype=float)
        elapsed = time_s - time_s[0]
        for column, partition in enumerate(("chronological", "five_block")):
            axis = axes[row_index, column]
            training = np.asarray(episode["partitions"][partition]["training_mask"], dtype=bool)
            for role in ("chronological_leader", "five_block_leader"):
                candidate = episode["candidates"][role]
                residual = np.asarray(candidate["fits"][partition]["residual_hz"], dtype=float)
                axis.plot(elapsed, residual, color=colors[role], alpha=0.72, linewidth=1.2)
                axis.scatter(
                    elapsed[training],
                    residual[training],
                    s=22,
                    color=colors[role],
                    marker="o",
                    label=role.replace("_", " ") if row_index == 0 and column == 0 else None,
                )
                axis.scatter(
                    elapsed[~training],
                    residual[~training],
                    s=28,
                    color=colors[role],
                    marker="x",
                )
            axis.axhline(0, color="black", linewidth=0.8, alpha=0.55)
            old = episode["candidates"]["chronological_leader"]["fits"][partition]
            new = episode["candidates"]["five_block_leader"]["fits"][partition]
            axis.set_title(
                f"{partition.replace('_', ' ')} mask\n"
                f"old {old['training_rms_hz']:.0f}/{old['heldout_rms_hz']:.0f} Hz; "
                f"new {new['training_rms_hz']:.0f}/{new['heldout_rms_hz']:.0f} Hz"
            )
            axis.set_xlabel("Elapsed time (s)")
            axis.set_ylabel("CFO residual (Hz)")
            axis.grid(alpha=0.2)
        axes[row_index, 0].text(
            0.01,
            0.98,
            (
                f"{episode['episode_id'].removeprefix('sha256:')[:10]} · "
                f"RX{episode['receiver_id']} ch{episode['channel']} · "
                f"{episode['candidates']['chronological_leader']['norad']}→"
                f"{episode['candidates']['five_block_leader']['norad']}"
            ),
            transform=axes[row_index, 0].transAxes,
            ha="left",
            va="top",
            fontsize=9,
        )
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.96),
        ncol=2,
        frameon=False,
    )
    figure.suptitle(
        "Partition-dependent candidate residuals at the frozen five-block Sacramento mode\n"
        "circles: training; crosses: held out; offsets refit from each panel's training mask",
        y=0.998,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.92))
    figure.savefig(output, dpi=170)
    plt.close(figure)


def run(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise ValueError("fresh output directory required")
    comparison = json.loads(args.comparison.read_text())
    changes = strong_changes(comparison)
    refinement = verify_refinement(args.refinement)
    expected_refinement = comparison["inputs"][comparison["comparisons"][0]["right"]]["sha256"]
    if digest(args.refinement) != expected_refinement:
        raise ValueError("comparison does not bind the supplied five-block refinement")
    if refinement.get("position_truth_used") is not False:
        raise ValueError("reference-position input is prohibited")
    inventory_path = args.evidence / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if inventory.get("known_position_used") is not False or inventory.get(
        "prior_matched_norads_used", False
    ):
        raise ValueError("truth- or site-conditioned evidence is prohibited")
    replay = replay_module()
    region = Region(**refinement["region"])
    grid = region.points(
        [refinement["selected"]["east_km"]], [refinement["selected"]["north_km"]]
    )
    args.output.mkdir(parents=True)
    episodes = []
    csv_rows = []
    document_cache: dict[str, tuple[dict, object, Path]] = {}
    for change in changes:
        session = change["session_id"]
        if session not in document_cache:
            evidence_path = args.evidence / "evidence" / f"{session}.json"
            document = json.loads(evidence_path.read_text())
            provenance = refinement["provenance"][session]
            if digest(evidence_path) != provenance["rf_digest"]:
                raise ValueError("RF evidence binding mismatch")
            metadata = document["inventory"]
            tle_name = metadata["tle_file"]
            if Path(tle_name).name != tle_name:
                raise ValueError("unsafe TLE basename")
            tle_path = evidence_path.parent / tle_name
            if digest(tle_path) != metadata["tle_digest"] or digest(tle_path) != provenance[
                "tle_digest"
            ]:
                raise ValueError("TLE evidence binding mismatch")
            if metadata["tle_collected_ns"] >= metadata["reference_utc_ns"] - 5_000_000_000:
                raise ValueError("noncausal TLE snapshot")
            document_cache[session] = (document, parse_element_sets(tle_path.read_text()), tle_path)
        document, catalogue, tle_path = document_cache[session]
        trajectory = source_trajectory(document, change["episode_id"])
        time_s = np.asarray(trajectory["time_s"])
        observed = np.asarray(trajectory["observed_hz"])
        masks = partition_masks(len(time_s))
        candidates = {}
        for role, key in (
            ("chronological_leader", "left_norad"),
            ("five_block_leader", "right_norad"),
        ):
            norad = int(change[key])
            predicted, epoch_ns = exact_prediction(
                replay,
                catalogue,
                int(document["inventory"]["reference_utc_ns"]),
                time_s,
                norad,
                grid.ecef_km[0],
            )
            fits = {}
            for partition, mask in masks.items():
                fitted = fitted_residuals(observed, predicted, mask)
                fits[partition] = {
                    "offset_hz": fitted["offset_hz"],
                    "training_rms_hz": fitted["training_rms_hz"],
                    "heldout_rms_hz": fitted["heldout_rms_hz"],
                    "residual_hz": np.asarray(fitted["residual_hz"]).tolist(),
                }
                csv_rows.append(
                    {
                        "session_id": session,
                        "episode_id": change["episode_id"],
                        "candidate_role": role,
                        "norad": norad,
                        "partition": partition,
                        "training_count": int(np.sum(mask)),
                        "heldout_count": int(np.sum(~mask)),
                        "offset_hz": fitted["offset_hz"],
                        "training_rms_hz": fitted["training_rms_hz"],
                        "heldout_rms_hz": fitted["heldout_rms_hz"],
                    }
                )
            candidates[role] = {
                "norad": norad,
                "comparison_weight": change[
                    "left_weight" if role == "chronological_leader" else "right_weight"
                ],
                "tle_element_epoch_utc_ns": epoch_ns,
                "predicted_hz": predicted.tolist(),
                "fits": fits,
            }
        episodes.append(
            {
                "session_id": session,
                "episode_id": change["episode_id"],
                "tracklet_id": trajectory["tracklet_id"],
                "receiver_id": trajectory["receiver_id"],
                "channel": trajectory["channel"],
                "actual_rf_hz": trajectory["actual_rf_hz"],
                "observation_count": len(time_s),
                "observation_id": trajectory["observation_id"],
                "source_group_id": trajectory["source_group_id"],
                "time_s": time_s.tolist(),
                "observed_hz": observed.tolist(),
                "partitions": {
                    name: {
                        "training_count": int(np.sum(mask)),
                        "heldout_count": int(np.sum(~mask)),
                        "mask_digest": mask_digest(trajectory["observation_id"], mask),
                        "training_mask": mask.tolist(),
                    }
                    for name, mask in masks.items()
                },
                "candidates": candidates,
            }
        )
    repeated = [
        episode
        for episode in episodes
        if episode["session_id"] == "scan-fw-e201d79ba3234e2e"
        and episode["candidates"]["chronological_leader"]["norad"] == 69332
        and episode["candidates"]["five_block_leader"]["norad"] == 64943
    ]
    if len(repeated) != 2:
        raise ValueError("expected two independent e201 69332-to-64943 trajectories")
    repeated_shape = common_time_shape(
        np.asarray(repeated[0]["time_s"]),
        np.asarray(repeated[0]["observed_hz"]),
        np.asarray(repeated[1]["time_s"]),
        np.asarray(repeated[1]["observed_hz"]),
    )
    repeated_shape.update(
        {
            "episode_ids": [episode["episode_id"] for episode in repeated],
            "receiver_ids": [episode["receiver_id"] for episode in repeated],
            "channels": [episode["channel"] for episode in repeated],
            "same_receiver": repeated[0]["receiver_id"] == repeated[1]["receiver_id"],
            "same_channel": repeated[0]["channel"] == repeated[1]["channel"],
            "shared_source_group_count": len(
                set(repeated[0]["source_group_id"]) & set(repeated[1]["source_group_id"])
            ),
        }
    )
    result = {
        "schema": "partition-dependent-identity-diagnostic/v1",
        "diagnostic_only": True,
        "reference_position_accessed": False,
        "satellite_truth_available": False,
        "candidate_selection_reused_these_observations": True,
        "inputs": {
            "association_comparison": {
                "path": str(args.comparison),
                "digest": digest(args.comparison),
            },
            "five_block_refinement": {
                "path": str(args.refinement),
                "digest": digest(args.refinement),
            },
            "five_block_refinement_seal": {
                "path": str(args.refinement.with_name("refinement-seal.json")),
                "digest": digest(args.refinement.with_name("refinement-seal.json")),
            },
            "evidence_inventory": {"path": str(inventory_path), "digest": digest(inventory_path)},
            "source": {"path": str(Path(__file__)), "digest": digest(Path(__file__))},
            "regional_replay_source": {
                "path": str(Path(replay.__file__)),
                "digest": digest(Path(replay.__file__)),
            },
        },
        "frozen_location": {
            "latitude_deg": refinement["latitude_deg"],
            "longitude_deg": refinement["longitude_deg"],
            "east_km": refinement["selected"]["east_km"],
            "north_km": refinement["selected"]["north_km"],
            "selection": "training-selected five-block blind Sacramento set refinement",
        },
        "protocol": {
            "candidate_set": "four first-comparison leader changes with both weights >= 0.9",
            "orbit": "exact nominal causal TLE propagation at each observation time",
            "nuisance": (
                "one candidate-specific constant fitted from each evaluated partition's "
                "training mask"
            ),
            "metrics": "ordinary RMS on identical observations under each partition mask",
            "frequency_scale": (
                "predicted Doppler and residual metrics use the canonical 11.2 GHz analysis "
                "carrier, not each channel's native RF"
            ),
        },
        "episodes": episodes,
        "repeated_e201_shape_diagnostic": repeated_shape,
        "limitations": [
            "candidate selection used these RF trajectories, so residual comparisons are "
            "descriptive and not identity validation",
            "the frozen receiver location was selected from the same five-block training evidence",
            "candidate weights are uncalibrated composite weights, not correctness probabilities",
            "chronological heldout scores forecast the tail; five-block heldout scores "
            "interpolate within the same time span",
            "constant frequency offsets remove absolute frequency and leave only trajectory shape",
            "nominal causal TLEs are used without orbit correction or transmitter truth",
        ],
    }
    result["content_digest"] = content_digest(result)
    result_path = args.output / "results.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    csv_path = args.output / "metrics.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    png_path = args.output / "partition-identity-residuals.png"
    plot_results(episodes, png_path)
    manifest = {
        "schema": "partition-dependent-identity-diagnostic-manifest/v1",
        "files": {
            path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
            for path in (result_path, csv_path, png_path)
        },
    }
    manifest["content_digest"] = content_digest(manifest)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
