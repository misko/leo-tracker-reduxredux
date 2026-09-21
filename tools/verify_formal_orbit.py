"""Verify a sealed formal fit's phase interpolation against exact SGP4."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import state_arrays

from leo.analysis.research.formal_orbit import doppler_hz
from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify(
    states_path,
    fit_path,
    prior_path,
    reranking_path,
    region,
    tolerance_hz=0.2,
    *,
    allow_unfitted_sources=False,
):
    if not np.isfinite(tolerance_hz) or tolerance_hz <= 0:
        raise ValueError("positive finite verification tolerance required")
    prior = json.loads(prior_path.read_text())
    strict = json.loads(reranking_path.read_text())
    if not strict.get("strictly_causal") or strict.get("evaluation_location_used"):
        raise ValueError("strict causal location-blind reranking required")
    if not prior.get("strictly_causal") or prior.get("future_tles_used_to_choose_model"):
        raise ValueError("strict causal orbital prior required")
    fit = json.loads(fit_path.read_text())
    result = fit.get("result", fit)
    step = fit.get("configuration", {}).get("phase_sensitivity_step_s", 1.0)
    if not result["converged"]:
        raise ValueError("cannot certify an unconverged fit")
    with np.load(states_path, allow_pickle=False) as archive:
        states = {key: archive[key] for key in archive.files}
    if str(states["schema"].item()) != "formal-orbit-phase-state-v1":
        raise ValueError("wrong phase-state schema")
    if str(states["prior_analysis_digest"].item()) != digest(prior_path):
        raise ValueError("prior digest mismatch")
    if str(states["strict_reranking_digest"].item()) != digest(reranking_path):
        raise ValueError("reranking digest mismatch")
    lookup = {(row["session_id"], row["episode_id"]): row for row in strict["rows"]}
    receiver = region.points([result["x_km"][0]], [result["x_km"][1]]).ecef_km[0]
    errors, rows = [], []
    seen = np.zeros(len(states["y_hz"]), bool)
    for index, target in enumerate(prior["targets"]):
        row = lookup[(target["session_id"], target["episode_id"])]
        mask = states["track"] == index
        if not np.any(mask):
            continue
        norad = int(target["norad"])
        if norad != int(row["best_norad"]) or np.any(states["source"][mask] != norad):
            raise ValueError("phase-state identity mismatch")
        capture = row["capture_start_utc_ns"]
        if max(row["winning_epoch_utc_ns"], row["winning_collected_utc_ns"]) >= capture:
            raise ValueError("noncausal TLE")
        age = (capture - row["winning_epoch_utc_ns"]) / 3_600_000_000_000
        np.testing.assert_allclose(states["age_h"][mask], age, atol=1e-12, rtol=0)
        rates = result["rate_corrections_s_h"]
        rate = rates.get(str(norad), 0.0) if allow_unfitted_sources else rates[str(norad)]
        correction = age * rate
        p, v, valid = state_arrays(
            parse_element_sets(row["winning_tle_text"]),
            [0],
            capture,
            states["time_s"][mask],
            clock_s=0,
            orbit_time_s=target["predicted_phase_s"] + correction,
        )
        if len(valid) != 1:
            raise ValueError("exact propagation failed")
        u = correction / step
        approximate = []
        for centre, minus, plus in (
            ("p_km", "phase_p_minus_km", "phase_p_plus_km"),
            ("v_km_s", "phase_v_minus_km_s", "phase_v_plus_km_s"),
        ):
            c, m, q = (states[key][mask] for key in (centre, minus, plus))
            approximate.append(c + 0.5 * u * (q - m) + 0.5 * u * u * (q - 2 * c + m))
        error = doppler_hz(receiver, *approximate) - doppler_hz(receiver, p[0], v[0])
        errors.extend(error.tolist())
        seen |= mask
        rows.append(
            {
                "session_id": target["session_id"],
                "episode_id": target["episode_id"],
                "norad": norad,
                "observations": int(mask.sum()),
                "rms_hz": float(np.sqrt(np.mean(error**2))),
                "maximum_absolute_hz": float(np.max(np.abs(error))),
            }
        )
    if not np.all(seen):
        raise ValueError("some phase-state observations were not checked")
    error = np.asarray(errors)
    maximum = float(np.max(np.abs(error)))
    return {
        "schema": "formal-orbit-exact-verification-v1",
        "observations": len(errors),
        "rms_hz": float(np.sqrt(np.mean(error**2))),
        "maximum_absolute_hz": maximum,
        "p99_absolute_hz": float(np.quantile(np.abs(error), 0.99)),
        "tolerance_hz": tolerance_hz,
        "passed": maximum <= tolerance_hz,
        "unfitted_sources_default_zero": allow_unfitted_sources,
        "inputs": {
            name: digest(path)
            for name, path in (
                ("states", states_path),
                ("fit", fit_path),
                ("prior", prior_path),
                ("reranking", reranking_path),
            )
        },
        "episodes": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("states", "fit", "prior", "reranking", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--region", required=True, help="JSON Region configuration")
    parser.add_argument("--tolerance-hz", type=float, default=0.2)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh verification output required")
    result = verify(
        args.states,
        args.fit,
        args.prior,
        args.reranking,
        Region(**json.loads(args.region)),
        args.tolerance_hz,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "episodes"}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
