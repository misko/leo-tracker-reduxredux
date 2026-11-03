"""Extend frozen causal states and derive a declared along-track phase prior.

Successive-TLE disagreement sets a sensitivity scale, not truth covariance.
No receiver position or measured CFO enters the phase prior.
"""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets


def run(recording, inputs, previous, output):
    receipt = json.loads((inputs / "receipt.json").read_text())
    if (
        hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest()
        != receipt["tracks_sha256"]
    ):
        raise ValueError("original Graph population changed")
    if hashlib.sha256((inputs / "bank.npz").read_bytes()).hexdigest() != receipt["bank_sha256"]:
        raise ValueError("original causal bank changed")
    tracks = load_tracks(recording)
    current = parse_element_sets((inputs / "selected.tle").read_text())
    old = parse_element_sets(previous.read_text())
    old_map = {n: i for i, n in enumerate(old.satellite_numbers)}
    selected = [i for i, n in enumerate(current.satellite_numbers) if n in old_map]
    subset_new = ElementSetCatalogue(
        tuple(current.names[i] for i in selected),
        tuple(current.satellite_numbers[i] for i in selected),
        tuple(current.satellites[i] for i in selected),
    )
    old_indexes = [old_map[n] for n in subset_new.satellite_numbers]
    subset_old = ElementSetCatalogue(
        tuple(old.names[i] for i in old_indexes),
        subset_new.satellite_numbers,
        tuple(old.satellites[i] for i in old_indexes),
    )
    t = np.array([0.0, 150.0, 300.0])
    pn, vn, good_new = matching.ecef_states(subset_new, receipt["origin_utc_ns"], t)
    po, _, good_old = matching.ecef_states(subset_old, receipt["origin_utc_ns"], t)
    if not good_new.all() or not good_old.all():
        raise ValueError("unusable causal element in prior comparison")
    direction = vn.copy()
    direction[:, :, 0] -= EARTH_ROTATION_RAD_S * pn[:, :, 1]
    direction[:, :, 1] += EARTH_ROTATION_RAD_S * pn[:, :, 0]
    displacement = po - pn
    phase = np.sum(displacement * direction, axis=2) / np.sum(direction**2, axis=2)
    remaining = displacement - phase[:, :, None] * direction
    sigma = np.ones(len(current))  # Declared fallback when a previous epoch is unavailable.
    sigma[selected] = np.clip(np.abs(np.median(phase, axis=1)), 0.1, 5.0)
    bounds = np.minimum(3 * sigma, 15.0)
    times = np.unique(np.concatenate([track["times"] for track in tracks]))
    grid = np.arange(np.floor(times.min()) - 17, np.ceil(times.max()) + 18)
    p, v, usable = matching.ecef_states(current, receipt["origin_utc_ns"], grid)
    if not usable.all():
        raise ValueError("expanded phase bank contains unusable propagation")
    with np.load(inputs / "bank.npz") as original:
        indexes = np.searchsorted(grid, original["time_s"])
        if not (
            np.array_equal(grid[indexes], original["time_s"])
            and np.array_equal(original["norad"], current.satellite_numbers)
        ):
            raise ValueError("original candidate or time inventory changed")
        parity = max(
            float(np.max(np.abs(p[:, indexes] - original["position_km"]))),
            float(np.max(np.abs(v[:, indexes] - original["velocity_km_s"]))),
        )
        if parity > 1e-9:
            raise ValueError("original sampled states changed")
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(
        output / "bank.npz",
        time_s=grid,
        position_km=p,
        velocity_km_s=v,
        norad=np.asarray(current.satellite_numbers),
        phase_sigma_s=sigma,
        phase_bound_s=bounds,
    )
    write(
        output / "receipt.json",
        dict(
            source_id=receipt["source_id"],
            origin_utc_ns=receipt["origin_utc_ns"],
            cutoff_utc_ns=receipt["cutoff_utc_ns"],
            regional_center=receipt["regional_center"],
            radius_km=receipt["radius_km"],
            original_bank_sha256=receipt["bank_sha256"],
            tracks_sha256=receipt["tracks_sha256"],
            bank_sha256=hashlib.sha256((output / "bank.npz").read_bytes()).hexdigest(),
            latest_tle_sha256=hashlib.sha256((inputs / "selected.tle").read_bytes()).hexdigest(),
            previous_tle_sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            phase_prior="zero mean; sigma=clip(abs(median old-minus-new along-track seconds),0.1,5); fallback1s; bounds3sigma max15s",
            phase_prior_is_calibrated_covariance=False,
            reference_position_used=False,
            original_state_max_difference=parity,
            candidates=len(current),
            previous_candidates=len(selected),
            median_unmodeled_cross_track_disagreement_km=float(
                np.median(np.linalg.norm(remaining, axis=2))
            ),
        ),
    )
    print(
        json.dumps(
            dict(
                source_id=receipt["source_id"],
                candidates=len(current),
                median_phase_sigma_s=float(np.median(sigma)),
                original_state_max_difference=parity,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.recording, a.inputs, a.previous, a.output)
