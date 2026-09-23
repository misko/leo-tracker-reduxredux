"""Forward-only geometric phase surviving local receiver nuisance fitting."""

import gzip
import json
from pathlib import Path

import numpy as np

from tools.research.fit_independent_phase import (
    FIGURE,
    digest,
    parse_element_sets,
    propagate_candidate_states,
    verify_frozen_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = FIGURE / "geometry-sensitivity"
BASELINE_M = 0.08
C_M_S = 299792458.0


def remove_polynomial(values, times, degree):
    values, times = np.asarray(values), np.asarray(times)
    tau = times - np.mean(times)
    design = np.column_stack([tau**power for power in range(degree + 1)])
    fitted, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    if rank != degree + 1 or len(times) <= rank:
        raise ValueError("insufficient nuisance projection support")
    return values - design @ fitted


def maximum_phase_rms(residual_u, wave_number, length=BASELINE_M):
    return float(
        wave_number
        * length
        * np.linalg.svd(residual_u, compute_uv=False)[0]
        / np.sqrt(len(residual_u))
    )


def provisional_baseline(site):
    lat, lon = np.deg2rad([site["latitude_deg"], site["longitude_deg"]])
    east = np.asarray([-np.sin(lon), np.cos(lon), 0.0])
    north = np.asarray([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    azimuth = np.deg2rad(79.0)
    return BASELINE_M * (np.sin(azimuth) * east + np.cos(azimuth) * north)


def main():
    model_path = FIGURE / "v2/training-model.json"
    frames_path = FIGURE / "train-frames.json.gz"
    artifact = json.loads(model_path.read_text())
    verify_frozen_inputs(artifact)
    with gzip.open(frames_path, "rt") as stream:
        frames = json.load(stream)
    if frames["fresh_held_visits_read"] or frames["old_reserved_visits_read"]:
        raise ValueError("training source claims reserved IQ exposure")
    rows = sorted(frames["rows"], key=lambda row: row["observation"]["time_s"])
    if len(rows) != 15:
        raise ValueError("expected 15 frozen training dwells")
    if len({row["observation"]["source_actual_rf_hz"] for row in rows}) != 1:
        raise ValueError("continuous counterfactual requires the same native RF")
    output = {
        "schema": "independent-phase-geometry-sensitivity/v1",
        "scope": "forward model only; no IQ replay or phase fit; no receiver truth",
        "baseline_m": BASELINE_M,
        "baseline_authority": "nominal mechanical benchmark; not measured RF phase centers",
        "bearing_scenario": "hypothetical horizontal 79 degrees clockwise from north",
        "timing_policy": "all 24 frozen frame opportunities in each of 15 training dwells",
        "model_sha256": digest(model_path),
        "frames_sha256": digest(frames_path),
        "source_sha256": digest(Path(__file__)),
        "models": {},
    }
    for name in ("glrt_candidate", "phase_candidate"):
        model = artifact["selected_models"][name]
        site = artifact["arms"][name]["site"]
        baseline = provisional_baseline(site)
        catalogue = parse_element_sets("\n".join(model["tle_lines"]) + "\n")
        per_dwell = []
        all_u, all_times = [], []
        for row in rows:
            times = np.asarray([frame["session_time_s"] for frame in row["branches"][0]["frames"]])
            if len(times) != 24:
                raise ValueError("frame opportunity population changed")
            position, _velocity, valid = propagate_candidate_states(
                catalogue,
                np.asarray([0]),
                artifact["start_utc_ns"],
                times,
                np.asarray([0.0]),
            )
            if len(valid) != 1:
                raise ValueError("exact propagation failed")
            delta = position[0, 0] - np.asarray(model["receiver_ecef_km"])
            u = delta / np.linalg.norm(delta, axis=1)[:, None]
            f = row["observation"]["source_actual_rf_hz"]
            wave_number = 2 * np.pi * f / C_M_S
            phi = wave_number * (u @ baseline)
            local = {
                "visit_index": row["observation"]["visit_index"],
                "span_s": float(np.ptp(times)),
                "frame_count": len(times),
                "hypothetical_79deg_phase_change_rad": float(np.ptp(phi)),
            }
            for degree in (0, 1, 2):
                residual = remove_polynomial(u, times, degree)
                phase_residual = wave_number * (residual @ baseline)
                local[f"degree_{degree}"] = {
                    "nuisance_rank": degree + 1,
                    "remaining_time_dimensions": len(times) - degree - 1,
                    "orientation_max_rms_rad": maximum_phase_rms(residual, wave_number),
                    "orientation_max_pointwise_rad": float(
                        wave_number * BASELINE_M * np.max(np.linalg.norm(residual, axis=1))
                    ),
                    "hypothetical_79deg_rms_rad": float(np.sqrt(np.mean(phase_residual**2))),
                    "residual_u_singular_values": np.linalg.svd(
                        residual, compute_uv=False
                    ).tolist(),
                }
            per_dwell.append(local)
            all_u.append(u)
            all_times.extend(times)
        all_u = np.concatenate(all_u)
        # Deliberately counterfactual: this requires phase continuity across retunes.
        continuous = {}
        for degree in (1, 2):
            residual = remove_polynomial(all_u, np.asarray(all_times), degree)
            continuous[f"degree_{degree}_orientation_max_rms_rad"] = maximum_phase_rms(
                residual, wave_number
            )
        output["models"][name] = {
            "candidate_norad": model["candidate_norad"],
            "site": site,
            "per_dwell": per_dwell,
            "maximum_local_orientation_rms_rad": {
                str(degree): max(
                    r[f"degree_{degree}"]["orientation_max_rms_rad"] for r in per_dwell
                )
                for degree in (0, 1, 2)
            },
            "counterfactual_continuous_arc": {"span_s": float(np.ptp(all_times)), **continuous},
        }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "results.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                name: {
                    "local": value["maximum_local_orientation_rms_rad"],
                    "continuous_counterfactual": value["counterfactual_continuous_arc"],
                }
                for name, value in output["models"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
