"""Check exact elapsed-time Doppler-rate separation for frozen episode 443."""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import replay_regional_doppler as replay  # noqa: E402

import leo.analysis.research.formal_orbit as formal_orbit_module  # noqa: E402
from leo.analysis.research.formal_orbit import doppler_hz  # noqa: E402
from leo.sky.frames import geodetic_to_ecef_km  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402

ARTIFACT = ROOT / "reports/artifacts/2026_09_21_shared_identity_orbit"
SESSION = "scan-fw-f0af018448538a4c"
EPISODE_INDEX = 443
STEP_S = 0.1


def rms(value: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(value) ** 2)))


def main() -> None:
    cache_path = ARTIFACT / "candidate-phase-states.npz"
    tle_path = ARTIFACT / "audit.retained-tles.json.gz"
    fit_path = ARTIFACT / "fit.json"
    output_path = ARTIFACT / "episode443-phase-rate-feasibility.json"
    with np.load(cache_path, allow_pickle=False) as opened:
        cache = {key: opened[key] for key in opened.files if key.endswith(f"_{EPISODE_INDEX}")}
    fit = json.loads(fit_path.read_text())
    model = next(row for row in fit["models"] if row["identity_model"] == "joint_candidate_mixture")
    latitude, longitude = model["latitude_deg"], model["longitude_deg"]
    receiver = geodetic_to_ecef_km(latitude, longitude, 0.0)
    lat, lon = np.deg2rad([latitude, longitude])
    up = np.asarray([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    with gzip.open(tle_path, "rt") as stream:
        retained = json.load(stream)[SESSION]
    norad = cache[f"norad_{EPISODE_INDEX}"].astype(int)
    tle_text = "".join(retained["records"][str(value)] for value in norad)
    catalogue = parse_element_sets(tle_text)
    times = cache[f"time_s_{EPISODE_INDEX}"]
    capture_ns = int(cache[f"capture_start_utc_ns_{EPISODE_INDEX}"])
    states = {}
    for label, shift in (("minus", -STEP_S), ("centre", 0.0), ("plus", STEP_S)):
        p, v, valid = replay.state_arrays(
            catalogue, list(range(len(norad))), capture_ns, times, clock_s=shift
        )
        if not np.array_equal(valid, np.arange(len(norad))):
            raise ValueError("nominal TLE propagation omitted a candidate")
        states[label] = (p, v)
    exact_rate = (
        doppler_hz(receiver, *states["plus"]) - doppler_hz(receiver, *states["minus"])
    ) / (2 * STEP_S)
    cache_rate = (
        doppler_hz(
            receiver,
            cache[f"p_plus_{EPISODE_INDEX}"],
            cache[f"v_plus_{EPISODE_INDEX}"],
        )
        - doppler_hz(
            receiver,
            cache[f"p_minus_{EPISODE_INDEX}"],
            cache[f"v_minus_{EPISODE_INDEX}"],
        )
    ) / 2
    delta = states["centre"][0] - receiver
    ranges = np.linalg.norm(delta, axis=-1)
    elevations = np.rad2deg(np.arcsin(np.sum(delta * up, axis=-1) / ranges))
    speeds = np.linalg.norm(states["centre"][1], axis=-1)
    winner = int(cache[f"winner_norad_{EPISODE_INDEX}"])
    winner_index = int(np.flatnonzero(norad == winner)[0])
    centred_rate = exact_rate - exact_rate.mean(axis=1, keepdims=True)
    rows = []
    for index, candidate in enumerate(norad):
        difference = exact_rate[index] - exact_rate[winner_index]
        rows.append(
            {
                "norad": int(candidate),
                "range_km_min_max": [float(ranges[index].min()), float(ranges[index].max())],
                "elevation_deg_min_max": [
                    float(elevations[index].min()),
                    float(elevations[index].max()),
                ],
                "ecef_speed_km_s_min_max": [float(speeds[index].min()), float(speeds[index].max())],
                "exact_elapsed_rate_hz_s_min_median_max": [
                    float(exact_rate[index].min()),
                    float(np.median(exact_rate[index])),
                    float(exact_rate[index].max()),
                ],
                "cache_orbit_phase_rate_hz_s_rms_difference": rms(
                    exact_rate[index] - cache_rate[index]
                ),
                "winner_rate_difference_hz_s_raw_rms": rms(difference),
                "winner_rate_difference_hz_s_after_common_constant": rms(
                    difference - difference.mean()
                ),
            }
        )
    observed = cache[f"observed_{EPISODE_INDEX}"]
    observed_fit = np.polyfit(times, observed, 1)
    payload = {
        "scope": "conditional numerical feasibility; no identity or position claim",
        "session_id": SESSION,
        "episode_index": EPISODE_INDEX,
        "episode_id": str(cache[f"episode_id_{EPISODE_INDEX}"].item()),
        "candidate_count": len(norad),
        "observation_count": len(times),
        "observation_span_s": float(times.max() - times.min()),
        "receiver_reference": {
            "kind": "frozen RF-derived joint-candidate fit; not receiver truth",
            "latitude_deg": latitude,
            "longitude_deg": longitude,
        },
        "derivative": {
            "method": (
                "nominal causal TLE exact SGP4 at receive UTC +/-0.1 s; Earth rotation advanced"
            ),
            "step_s": STEP_S,
            "rf_hz": 11_200_000_000.0,
        },
        "observed_glrt_affine_slope_hz_s": float(observed_fit[0]),
        "observed_glrt_affine_residual_rms_hz": rms(observed - np.polyval(observed_fit, times)),
        "candidate_pointwise_rate_range_hz_s_min_median_max": [
            float(np.ptp(exact_rate, axis=0).min()),
            float(np.median(np.ptp(exact_rate, axis=0))),
            float(np.ptp(exact_rate, axis=0).max()),
        ],
        "candidate_pointwise_centred_rate_range_hz_s_min_median_max": [
            float(np.ptp(centred_rate, axis=0).min()),
            float(np.median(np.ptp(centred_rate, axis=0))),
            float(np.ptp(centred_rate, axis=0).max()),
        ],
        "candidates": rows,
        "input_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (cache_path, tle_path, fit_path)
        },
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "formal_orbit_source_sha256": hashlib.sha256(
            Path(formal_orbit_module.__file__).read_bytes()
        ).hexdigest(),
    }
    output_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
