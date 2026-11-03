"""Exploratory fixed-identity, Cauchy-loss, count-weighted shared RX fit."""

import json
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import models
import numpy as np
from bundle import Data
from evaluate import coordinates, ecef
from investigate_sample import SESSION, save
from selection import ROOT

SCALE_HZ = 500.0
COUNT_CAP = 100


def track_weight(count):
    return np.sqrt(np.minimum(count, COUNT_CAP))


def weighted_median(values, weights):
    order = np.argsort(values, kind="stable")
    return values[order][np.searchsorted(np.cumsum(weights[order]), np.sum(weights) / 2)]


def fit_receiver(blocks, identities, count_weighted=True):
    counts = np.array([len(block["rows"]) for block in blocks])
    if not len(counts):
        raise ValueError("Receiver has no retained track groups")
    owners = np.repeat(np.arange(len(blocks)), counts)
    times = np.concatenate([block["times"] for block in blocks])
    values = np.concatenate(
        [block["residual"][:, identities[block["track_index"]]] for block in blocks]
    )
    visible = np.array([block["visible"][identities[block["track_index"]]] for block in blocks])
    weights = track_weight(counts) if count_weighted else np.ones(len(counts))
    point_weights = (weights / counts)[owners] * visible[owners]
    if not np.any(point_weights):
        return 1e8, np.array([0.0, 0.0])
    centers = np.array([np.mean(block["times"]) for block in blocks])
    medians = np.array(
        [np.median(block["residual"][:, identities[block["track_index"]]]) for block in blocks]
    )
    original_branch = np.rint((medians - models.circular(medians)) / models.ALIAS_HZ)
    medians = models.circular(medians)
    starts = []
    for slope in (-50.0, 0.0, 50.0):
        offsets = medians - slope * centers
        center = weighted_median(offsets[visible], weights[visible])
        offsets = center + models.circular(offsets, center)
        for quantile in (0.1, 0.25, 0.5, 0.75, 0.9):
            starts.append([np.quantile(offsets[visible], quantile), slope])
    lines = np.asarray(starts)
    for _iteration in range(100):
        expected = lines[:, :1] + lines[:, 1:] * times[None, :]
        branch = np.rint(
            (medians[None, :] - lines[:, :1] - lines[:, 1:] * centers[None, :]) / models.ALIAS_HZ
        )
        aligned = values[None, :] - (branch + original_branch[None, :])[:, owners] * models.ALIAS_HZ
        residual = aligned - expected
        robust_weights = point_weights[None, :] / (1 + (residual / SCALE_HZ) ** 2)
        totals = np.sum(robust_weights, axis=1)
        mean_time = np.sum(robust_weights * times, axis=1) / totals
        mean_value = np.sum(robust_weights * aligned, axis=1) / totals
        centered_time = times[None, :] - mean_time[:, None]
        variance = np.sum(robust_weights * centered_time**2, axis=1)
        slopes = np.clip(
            np.sum(robust_weights * centered_time * (aligned - mean_value[:, None]), axis=1)
            / np.maximum(variance, 1e-20),
            -50.0,
            50.0,
        )
        updated = np.column_stack([mean_value - slopes * mean_time, slopes])
        change = np.max(
            np.abs(updated[:, 0] - lines[:, 0]) + 150 * np.abs(updated[:, 1] - lines[:, 1])
        )
        lines = updated
        if change < 0.01:
            break
    scores = []
    for line in lines:
        branch = np.rint((medians - line[0] - line[1] * centers) / models.ALIAS_HZ)
        aligned = values - (branch + original_branch)[owners] * models.ALIAS_HZ
        residual = aligned - line[0] - line[1] * times
        loss = SCALE_HZ**2 * np.log1p((residual / SCALE_HZ) ** 2)
        penalty = np.sum(weights[~visible]) * 1e8
        scores.append((float(np.sum(point_weights * loss)) + penalty) / np.sum(weights))
    best = int(np.argmin(scores))
    return scores[best], lines[best]


def fit_blocks(blocks, identities, count_weighted=True):
    scores, lines, weights = [], {}, []
    for receiver in (0, 1):
        local = [block for block in blocks if block["receiver"] == receiver]
        score, line = fit_receiver(local, identities, count_weighted)
        scores.append(score)
        weights.append(
            sum(track_weight(len(block["rows"])) if count_weighted else 1 for block in local)
        )
        lines[receiver] = line
    return float(np.average(scores, weights=weights)), lines


def main():
    directory = ROOT / "scans" / SESSION
    output = ROOT / f"investigation-{SESSION}"
    data = Data(directory)
    fits = json.loads((directory / "fits.json").read_text())["models"]
    identities = {
        row["track_index"]: row["satellite_index"] for row in fits["track_independent"]["tracks"]
    }
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))

    def blocks_at(point):
        prediction, visible = context.cache.get(point)
        return models._track_blocks(context, prediction, visible)

    def evaluate(point):
        return fit_blocks(blocks_at(point), identities)

    started = time.monotonic()
    search = models._search_position(
        evaluate, fits["track_independent"]["parameters"][:2], time.monotonic() + 180
    )
    parameters = np.zeros(70)
    parameters[:2] = search["point"]
    for receiver, line in search["details"].items():
        parameters[2 + 2 * receiver : 4 + 2 * receiver] = line
    experiments = {}
    for location, point in (
        ("old_shared_position", fits["track_linear"]["parameters"][:2]),
        ("new_position", parameters[:2]),
    ):
        blocks = blocks_at(point)
        _, lines = fit_blocks(blocks, identities)
        _, unweighted = fit_blocks(blocks, identities, count_weighted=False)
        trials = {0: [], 1: []}
        for omitted in blocks:
            receiver = omitted["receiver"]
            local = [
                block
                for block in blocks
                if block["receiver"] == receiver and block["track_index"] != omitted["track_index"]
            ]
            _, line = fit_receiver(local, identities)
            trials[receiver].append(line.tolist())
        experiments[location] = {
            "lines": {str(key): value.tolist() for key, value in lines.items()},
            "equal_track_weight_lines": {
                str(key): value.tolist() for key, value in unweighted.items()
            },
            "leave_one_out_lines": {str(key): value for key, value in trials.items()},
        }
    truth = json.loads((directory / "evaluation.json").read_text())["reference_site"]
    error = float(
        np.linalg.norm(
            ecef(*coordinates(parameters[:2])) - ecef(truth["latitude_deg"], truth["longitude_deg"])
        )
    )
    receipt = {
        "session_id": SESSION,
        "success": search["success"],
        "status": search["status"],
        "parameters": parameters.tolist(),
        "reference_error_km": error,
        "objective": search["objective"],
        "runtime_s": time.monotonic() - started,
        "search": {key: search[key] for key in ("grid_best", "local_runs")},
        "definition": "Fixed independent-model satellite IDs; Cauchy scale 500 Hz; "
        "track weight sqrt(min(unique source groups,100)), divided among track points; "
        "RX slopes bounded +/-50.0 Hz/s. No satellite timing adjustments.",
        "caveat": "Exploratory variant after inspecting this scan, not independent validation. "
        "Changes identities policy, robust loss, and weights together. "
        "Leave-one-out holds position fixed; not joint position uncertainty.",
        "sensitivity": experiments,
    }
    (output / "robust-weighted-drift.json").write_text(json.dumps(receipt, indent=2) + "\n")
    figure, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True, constrained_layout=True)
    blocks = blocks_at(parameters[:2])
    times = np.linspace(0, 300, 301)
    for receiver, axis in enumerate(axes):
        for block in blocks:
            if block["receiver"] != receiver:
                continue
            values = block["residual"][:, identities[block["track_index"]]]
            center = (min(block["times"]) + max(block["times"])) / 2 + 150
            expected = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (center - 150)
            offset = expected + models.circular(np.median(values), expected)
            axis.scatter(
                center, offset / 1000, s=5 * track_weight(len(values)), alpha=0.65, color="#0072b2"
            )
        line = parameters[2 + 2 * receiver : 4 + 2 * receiver]
        trials = np.asarray(experiments["new_position"]["leave_one_out_lines"][str(receiver)])
        curves = trials[:, :1] + trials[:, 1:] * (times[None, :] - 150)
        axis.fill_between(
            times,
            curves.min(axis=0) / 1000,
            curves.max(axis=0) / 1000,
            alpha=0.25,
            color="#cc79a7",
            label="Leave-one-track-out range",
        )
        axis.plot(
            times,
            (line[0] + line[1] * (times - 150)) / 1000,
            color="black",
            label=f"New line: {line[1]:+.2f} Hz/s",
        )
        axis.set(title=f"RX{receiver}", ylabel="Constant offset (kHz)", xlim=(0, 300))
        axis.grid(alpha=0.2)
        axis.legend()
    axes[-1].set_xlabel("Scan time (s)")
    figure.suptitle(
        f"Robust count-weighted prototype — reference error {error:.2f} km\n"
        "Fixed satellite identities; point area follows capped sqrt(GLRT count)"
    )
    save(figure, output, "07-robust-weighted-drift")
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in ("success", "parameters", "reference_error_km", "runtime_s")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
