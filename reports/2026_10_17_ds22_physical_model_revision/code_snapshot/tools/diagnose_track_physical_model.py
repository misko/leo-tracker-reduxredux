"""Diagnostic-only paired carrier-bias / bounded-UTC experiment at two fixed sites.

The supplied GPS and a previously sealed blind endpoint are scoring locations,
not seeds for a future search. No position-accuracy improvement is claimed.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, solve_bias, write

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.rf_scaled_component_bias import profile_rf_scaled_bias
from leo.analysis.research.track_catalogue_geometry import frequency_grid


def objective(stats, beta, terms):
    active = np.flatnonzero(stats["active"])
    frequency = float(
        np.sum(
            np.minimum(stats["count"][active], 50)
            * np.minimum(terms.score[active, terms.best[active]], 900.0**2)
        )
    )
    return frequency + 150.0**2 * float(
        np.sum((beta[4:8] / (150 * matching.DRIFT_SIGMA_HZ_S)) ** 2)
    )


def solve_rf_bias(stats, initial, budget=160):
    winner = None
    for seed in matching.seed_calibrations(stats, initial, budget):
        beta = seed
        for gate in (4000.0, 2000.0, 1000.0, 600.0, 450.0):
            for _ in range(3):
                terms = profile_rf_scaled_bias(stats, beta, bias_sigma_hz=1000)
                adjusted = dict(
                    stats, mean=stats["mean"] - stats["q"][:, None] * terms.bias_hz[stats["ci"]]
                )
                new, ranks = matching.fit_shared(
                    adjusted, terms.best, terms.rms_hz, terms.aliases, beta, gate
                )
                change = np.max(np.abs(new - beta))
                beta = new
                if change < 0.01:
                    break
        terms = profile_rf_scaled_bias(stats, beta, bias_sigma_hz=1000)
        score = objective(stats, beta, terms)
        if winner is None or score < winner[0]:
            winner = (score, beta.copy(), ranks)
    return winner[1], winner[2]


def run(recording, inputs, previous_fit, output, reference):
    output.mkdir(parents=True, exist_ok=False)
    receipt = json.loads((recording / "receipt.json").read_text())
    sky_receipt = json.loads((inputs / "receipt.json").read_text())
    for path, expected in (
        (inputs / "bank.npz", sky_receipt["bank_sha256"]),
        (recording / "tracks.json", sky_receipt["tracks_sha256"]),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("scientific input changed")
    previous = json.loads(previous_fit.read_text())["endpoint"]
    sites = [
        ("supplied_evaluation_site", *reference),
        ("previous_blind_endpoint", previous["latitude_deg"], previous["longitude_deg"]),
    ]
    half_width = (
        receipt["metadata"]["anchor_utc_ns"] - receipt["metadata"]["causal_cutoff_utc_ns"]
    ) / 1e9
    if not 0 <= half_width <= 1:
        raise ValueError("invalid declared UTC bracket")
    tracks = load_tracks(recording)
    merged = json.loads((recording / "merged.json").read_text())
    groups = {}
    for track in tracks:
        groups.setdefault(merged["result"]["ownership"][track["key"]], []).append(track)
    groups = sorted(groups.items())
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    with np.load(inputs / "bank.npz") as archive:
        sky = {k: archive[k] for k in archive.files}
    sources = [
        Path(__file__),
        Path(matching.__file__),
        Path(__file__).with_name("associate_merged_track_catalogue.py"),
        Path(__file__).resolve().parents[1]
        / "src/leo/analysis/research/rf_scaled_component_bias.py",
    ]
    write(
        output / "protocol.json",
        dict(
            source_id=receipt["source_id"],
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            bank_sha256=sky_receipt["bank_sha256"],
            tracks_sha256=sky_receipt["tracks_sha256"],
            previous_fit_sha256=hashlib.sha256(previous_fit.read_bytes()).hexdigest(),
            use="diagnostic only; neither sites nor fitted states initialize a subsequent search",
            sites=sites,
            time_shifts_s=[-half_width, 0, half_width],
            grouping="frozen merged",
            bias_sigma_hz_at_reference=1000,
            bias_reference_rf_hz=11.5e9,
            carrier_hardware_gauge="zero-mean Gaussian component-bias prior; imposed assumption",
            drift_prior_sigma_hz_s=matching.DRIFT_SIGMA_HZ_S,
            drift_bound_hz_s=matching.DRIFT_BOUND_HZ_S,
            seed_budget=160,
            independent_identity_labels=False,
            position_estimate=False,
        ),
    )
    rows = []
    for name, lat, lon in sites:
        for shift in (-half_width, 0, half_width):
            frequency, elevation = frequency_grid(sky, times + shift, lat, lon)
            stats = matching.statistics(
                groups,
                dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
                {str(t["channel"]): 0.0 for t in tracks},
            )
            for family in ("native", "rf_scaled"):
                for fitted_c in (False, True):
                    initial = np.asarray(merged["calibration"]["beta"])
                    if fitted_c:
                        initial = np.r_[initial, 0.0]
                    started = time.monotonic()
                    if family == "native":
                        beta, ranks = solve_bias(stats, initial, 1000, 160)
                        terms = profile_component_bias(stats, beta, bias_sigma_hz=1000)
                    else:
                        beta, ranks = solve_rf_bias(stats, initial)
                        terms = profile_rf_scaled_bias(stats, beta, bias_sigma_hz=1000)
                    row = dict(
                        site=name,
                        latitude_deg=lat,
                        longitude_deg=lon,
                        utc_shift_s=shift,
                        family=family,
                        fitted_c=fitted_c,
                        beta=beta.tolist(),
                        score=objective(stats, beta, terms),
                        points=int(sum(stats["count"])),
                        ranks=ranks,
                        solve_seconds=time.monotonic() - started,
                        candidate_norads=[int(sky["norad"][i]) for i in terms.best],
                    )
                    rows.append(row)
                    write(output / "results.json", rows)
                    print(
                        json.dumps(
                            {
                                k: row[k]
                                for k in ("site", "utc_shift_s", "family", "fitted_c", "score")
                            }
                        ),
                        flush=True,
                    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--previous-fit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reference-latitude", type=float, required=True)
    p.add_argument("--reference-longitude", type=float, required=True)
    a = p.parse_args()
    run(
        a.recording,
        a.inputs,
        a.previous_fit,
        a.output,
        (a.reference_latitude, a.reference_longitude),
    )
