from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.sky.frames import (  # noqa: E402
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid  # noqa: E402
from leo.sky.sampling import SamplingGrid  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent
SELECTION_PATH = REPORT_DIR / "selection.json"
PHASE_RESULTS_PATH = (
    REPORT_DIR.parent / "2026_09_25_cross_track_adjacent_dwell_replication" / "results.json"
)
TRACKING_ROOT = Path("/srv/bulk/leo/scanner-shared-tracking-v14")
BASELINE_M = 0.08
SPEED_OF_LIGHT_M_S = 299_792_458.0
OBSERVER = {
    "latitude_deg": 37.858988,
    "longitude_deg": -122.478103,
    "altitude_m": -29.0,
}


def kappa_from_resultant(resultant: float) -> float:
    """Standard circular-statistics approximation for A1 inverse."""
    if resultant < 0.53:
        return 2 * resultant + resultant**3 + 5 * resultant**5 / 6
    if resultant < 0.85:
        return -0.4 + 1.39 * resultant + 0.43 / (1 - resultant)
    return 1 / (resultant**3 - 4 * resultant**2 + 3 * resultant)


def von_mises_log_bayes_factor(phase_rad: np.ndarray, kappa: float) -> float:
    """Log likelihood ratio of zero-centered von Mises versus uniform phase."""
    log_i0 = math.log(float(np.i0(kappa)))
    return float(np.sum(kappa * np.cos(phase_rad) - log_i0))


@cache
def load_tracking_manifest(session_id: str) -> dict:
    return json.loads((TRACKING_ROOT / session_id / "manifest.json").read_text())[
        "document"
    ]


def load_reviews(track: dict) -> tuple[dict, dict]:
    document = load_tracking_manifest(track["session_id"])
    by_name = {row["artifact_name"]: row for row in document["track_reviews"]}
    return by_name[track["rx0_review"]], by_name[track["rx1_review"]]


@cache
def load_catalogue(path_text: str):
    return parse_element_sets(Path(path_text).read_text())


def east_west_phase_changes_deg(
    tle_path: str, catalog_numbers: list[int], utc_pair: list[int], rf_hz: float
) -> dict[int, float]:
    midpoint = (int(utc_pair[0]) + int(utc_pair[1])) // 2
    utc_ns = (int(utc_pair[0]), midpoint, int(utc_pair[1]))
    spacing_s = (utc_ns[-1] - utc_ns[0]) / 2e9
    grid = SamplingGrid(utc_ns, 0, spacing_s)
    catalogue = load_catalogue(tle_path)
    indices = [catalogue.satellite_numbers.index(value) for value in catalog_numbers]
    propagated = propagate_grid(catalogue, grid, indices=indices)
    julian_day, fraction = julian_day_from_utc_ns(np.asarray(utc_ns, dtype=np.int64))
    gmst = greenwich_mean_sidereal_time_rad(julian_day, fraction)
    receiver_ecef = geodetic_to_ecef_km(**OBSERVER)
    rotation = ecef_to_enu_matrix(
        OBSERVER["latitude_deg"], OBSERVER["longitude_deg"]
    )
    scale_deg = 360.0 * rf_hz * BASELINE_M / SPEED_OF_LIGHT_M_S
    changes = {}
    for row_index, catalog_number in enumerate(catalog_numbers):
        if not bool(propagated.usable[row_index]):
            raise RuntimeError(f"TLE propagation failed for {catalog_number}")
        position_ecef, _ = teme_to_ecef(
            propagated.position_teme_km[row_index],
            propagated.velocity_teme_km_s[row_index],
            gmst,
        )
        relative_ecef = position_ecef - receiver_ecef
        enu = relative_ecef @ rotation.T
        unit_enu = enu / np.linalg.norm(enu, axis=1)[:, None]
        changes[catalog_number] = float(scale_deg * (unit_enu[-1, 0] - unit_enu[0, 0]))
    return changes


def common_candidates(rx0: dict, rx1: dict) -> list[int]:
    right = {int(row["catalog_number"]) for row in rx1["candidates"]}
    return [
        int(row["catalog_number"])
        for row in rx0["candidates"]
        if int(row["catalog_number"]) in right
    ]


def doppler_costs(rx0: dict, rx1: dict, candidates: list[int]) -> dict[int, float]:
    lookup = []
    for review in (rx0, rx1):
        lookup.append(
            {
                int(row["catalog_number"]): float(row["randomized_evaluation_rms_hz"])
                for row in review["candidates"]
            }
        )
    return {
        candidate: (
            int(rx0["observation_count"]) * math.log(lookup[0][candidate])
            + int(rx1["observation_count"]) * math.log(lookup[1][candidate])
        )
        for candidate in candidates
    }


def analyze() -> dict:
    selection = json.loads(SELECTION_PATH.read_text())
    phase_results = json.loads(PHASE_RESULTS_PATH.read_text())
    calibration_r = float(selection["phase_calibration"]["modeled_boundary_resultant"])
    kappa = kappa_from_resultant(calibration_r)
    phase_by_track = {
        track: [row for row in phase_results["pairs"] if row["track"] == track]
        for track in {row["track"] for row in phase_results["pairs"]}
    }

    prepared = []
    for track in selection["tracks"]:
        rx0, rx1 = load_reviews(track)
        candidates = common_candidates(rx0, rx1)
        costs = doppler_costs(rx0, rx1, candidates)
        leader = min(costs, key=costs.get)
        edges = phase_by_track[track["track"]]
        predictions = {
            candidate: [] for candidate in candidates
        }
        for edge in edges:
            changes = east_west_phase_changes_deg(
                track["tle_path"],
                candidates,
                edge["boundary_window_center_utc_ns"],
                float(track["rf_hz"]),
            )
            for candidate, change in changes.items():
                predictions[candidate].append(change)
        prepared.append(
            {
                "track": track,
                "rx0": rx0,
                "rx1": rx1,
                "candidates": candidates,
                "doppler_costs": costs,
                "doppler_leader": leader,
                "edges": edges,
                "predictions": predictions,
            }
        )

    sign_scores = {}
    for sign in (-1, 1):
        score = 0.0
        for row in prepared:
            observed = np.radians(
                [edge["held_boundary_residual_deg"] for edge in row["edges"]]
            )
            predicted = np.radians(row["predictions"][row["doppler_leader"]])
            score += float(np.sum(kappa * np.cos(observed - sign * predicted)))
        sign_scores[sign] = score
    selected_sign = max(sign_scores, key=sign_scores.get)

    track_rows = []
    for row in prepared:
        observed = np.radians(
            [edge["held_boundary_residual_deg"] for edge in row["edges"]]
        )
        pairing_log_bf = von_mises_log_bayes_factor(observed, kappa)
        phase_log_likelihood = {}
        for candidate in row["candidates"]:
            predicted = np.radians(row["predictions"][candidate])
            phase_log_likelihood[candidate] = float(
                np.sum(kappa * np.cos(observed - selected_sign * predicted))
            )
        combined_cost = {
            candidate: row["doppler_costs"][candidate]
            - phase_log_likelihood[candidate]
            for candidate in row["candidates"]
        }
        doppler_order = sorted(row["candidates"], key=row["doppler_costs"].get)
        combined_order = sorted(row["candidates"], key=combined_cost.get)
        doppler_margin = (
            row["doppler_costs"][doppler_order[1]]
            - row["doppler_costs"][doppler_order[0]]
        )
        combined_margin = (
            combined_cost[combined_order[1]] - combined_cost[combined_order[0]]
        )
        all_changes = [
            value
            for candidate in row["candidates"]
            for value in row["predictions"][candidate]
        ]
        track_rows.append(
            {
                "track": row["track"]["track"],
                "session_id": row["track"]["session_id"],
                "edge_count": len(row["edges"]),
                "candidate_count": len(row["candidates"]),
                "phase_pairing_log_bayes_factor": pairing_log_bf,
                "phase_pairing_bayes_factor": math.exp(pairing_log_bf),
                "doppler_leader": doppler_order[0],
                "phase_assisted_leader": combined_order[0],
                "leader_changed": combined_order[0] != doppler_order[0],
                "doppler_runner_log_cost_margin": doppler_margin,
                "phase_assisted_runner_log_cost_margin": combined_margin,
                "runner_margin_change": combined_margin - doppler_margin,
                "candidate_phase_log_likelihood_spread": (
                    max(phase_log_likelihood.values())
                    - min(phase_log_likelihood.values())
                ),
                "predicted_boundary_phase_change_range_deg": [
                    min(all_changes),
                    max(all_changes),
                ],
                "candidate_scores": [
                    {
                        "catalog_number": candidate,
                        "doppler_log_cost": row["doppler_costs"][candidate],
                        "phase_log_likelihood": phase_log_likelihood[candidate],
                        "phase_assisted_log_cost": combined_cost[candidate],
                        "predicted_boundary_phase_change_deg": row["predictions"][candidate],
                    }
                    for candidate in row["candidates"]
                ],
            }
        )

    return {
        "schema_version": 1,
        "method": {
            "phase_calibration_resultant": calibration_r,
            "phase_calibration_kappa": kappa,
            "phase_model": "zero-centered von Mises; no phase intercept",
            "baseline": "8 cm horizontal east-west",
            "receiver_order_sign_policy": "one global sign across all tracks",
            "selected_receiver_order_sign": selected_sign,
            "sign_scores_without_normalization": sign_scores,
            "doppler_fusion_cost": (
                "sum over RX of observation_count * log(randomized evaluation RMS Hz)"
            ),
        },
        "summary": {
            "track_count": len(track_rows),
            "phase_validated_pair_count": int(
                np.sum([row["phase_pairing_log_bayes_factor"] > 0 for row in track_rows])
            ),
            "leader_change_count": int(np.sum([row["leader_changed"] for row in track_rows])),
            "maximum_candidate_phase_log_likelihood_spread": max(
                row["candidate_phase_log_likelihood_spread"] for row in track_rows
            ),
            "maximum_absolute_runner_margin_change": max(
                abs(row["runner_margin_change"]) for row in track_rows
            ),
            "receiver_order_sign_score_difference": abs(
                sign_scores[1] - sign_scores[-1]
            ),
        },
        "tracks": track_rows,
    }


def plot(result: dict) -> None:
    rows = result["tracks"]
    labels = [row["track"] for row in rows]
    x = np.arange(len(rows))
    log10_bf = np.asarray(
        [row["phase_pairing_log_bayes_factor"] / math.log(10) for row in rows]
    )
    phase_spread = np.asarray(
        [row["candidate_phase_log_likelihood_spread"] for row in rows]
    )
    margin_change = np.asarray([row["runner_margin_change"] for row in rows])
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.2))
    axes[0].bar(x, log10_bf)
    axes[0].axhline(0.0, color="0.2", linewidth=0.8)
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("log10 Bayes factor: same emitter vs random reset")
    axes[0].set_title("Phase validates each dual-RX track pairing")
    axes[0].grid(axis="y", alpha=0.22)

    width = 0.36
    axes[1].bar(x - width / 2, phase_spread, width, label="phase log-likelihood spread")
    axes[1].bar(x + width / 2, abs(margin_change), width, label="runner-margin change")
    axes[1].set_yscale("log")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("candidate-specific score change")
    axes[1].set_title("Sub-ms phase geometry is too small to rerank TLEs")
    axes[1].legend(frameon=False)
    axes[1].grid(axis="y", alpha=0.22)
    figure.suptitle("What the current phase estimate adds to satellite association")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "phase-assisted-association.png", dpi=180, facecolor="white")
    plt.close(figure)


def main() -> None:
    result = analyze()
    (REPORT_DIR / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    plot(result)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
