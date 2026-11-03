"""Causal regional orbit preparation and bounded fixed-site track association.

Preparation uses a broad declared city prior, never the evaluation coordinate.
Matched c=0/fitted-c and grouped/ungrouped arms use exactly the same points/sky.
This is a fixed-site association diagnostic; it does not estimate a position.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from evaluate_ds22_merged_tracks import json_default

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.track_catalogue_geometry import frequency_grid
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import ElementSetCatalogue

REGION_LATITUDE = 37.5
REGION_LONGITUDE = -122.0


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=json_default) + "\n")


def load_tracks(recording):
    tracks = json.loads((recording / "tracks.json").read_text())
    for track in tracks:
        track["times"] = np.asarray(track["times"], float)
        track["values"] = np.asarray(track["values"], float)
    return tracks


def prepare(recording, output):
    from sgp4.exporter import export_tle

    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader

    receipt = json.loads((recording / "receipt.json").read_text())
    metadata = receipt["metadata"]
    tracks = load_tracks(recording)
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    cutoff = metadata["causal_cutoff_utc_ns"]
    eligible = [
        s
        for s in reader.list_snapshots("space-track")
        if cutoff - 172800_000_000_000 <= s.collected_utc_ns <= cutoff
    ]
    unique = {s.sha256: s for s in eligible}

    class Reader:
        def list_snapshots(self, provider):
            return tuple(unique.values())

        def read(self, snapshot):
            return reader.read(snapshot)

    causal = causal_catalogue(Reader(), cutoff)
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    origin = metadata["anchor_utc_ns"]
    coarse = np.arange(np.floor(times.min()) - 1, np.ceil(times.max()) + 6, 5.0)
    p, v, usable = matching.ecef_states(causal.catalogue, origin, coarse)
    observer = geodetic_to_ecef_km(REGION_LATITUDE, REGION_LONGITUDE, 0.0)
    enu = ecef_to_enu_matrix(REGION_LATITUDE, REGION_LONGITUDE)
    _, elevation, _, _ = look_angles(p, v, observer, enu)
    # Deliberately broad guard around a 250-km city prior, plus 5-s motion.
    selected = np.flatnonzero(usable & (elevation.max(axis=1) >= -12.0))
    cat = causal.catalogue
    chosen = ElementSetCatalogue(
        tuple(cat.names[i] for i in selected),
        tuple(cat.satellite_numbers[i] for i in selected),
        tuple(cat.satellites[i] for i in selected),
    )
    grid = np.arange(np.floor(times.min()) - 1, np.ceil(times.max()) + 2)
    p, v, usable = matching.ecef_states(chosen, origin, grid)
    if not usable.all():
        raise ValueError("selected orbit propagation failed")
    bank = dict(
        time_s=grid, position_km=p, velocity_km_s=v, norad=np.array(chosen.satellite_numbers)
    )
    # Validate the interpolation on response-blind time quantiles, not a guessed
    # accuracy bound. Geographic checks include the prior's cardinal extremes.
    sample = times[np.unique(np.linspace(0, len(times) - 1, min(96, len(times))).astype(int))]
    exact_p, exact_v, _ = matching.ecef_states(chosen, origin, sample)
    errors = []
    for lat, lon in (
        (37.5, -122.0),
        (35.25, -122.0),
        (39.75, -122.0),
        (37.5, -124.85),
        (37.5, -119.15),
    ):
        site = geodetic_to_ecef_km(lat, lon, 0.0)
        rotation = ecef_to_enu_matrix(lat, lon)
        _, _, _, exact_rate = look_angles(exact_p, exact_v, site, rotation)
        predicted, _ = frequency_grid(bank, sample, lat, lon)
        error = np.max(np.abs(predicted + 11.5e9 * exact_rate / 299792.458))
        errors.append(dict(latitude_deg=lat, longitude_deg=lon, maximum_error_hz=float(error)))
    if max(x["maximum_error_hz"] for x in errors) > 5.0:
        raise ValueError(
            "one-second orbit interpolation exceeds the declared 5-Hz qualification gate"
        )
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output / "bank.npz", **bank)
    (output / "selected.tle").write_text(
        "".join(
            f"0 {name}\n{a}\n{b}\n"
            for name, satellite in zip(chosen.names, chosen.satellites, strict=True)
            for a, b in [export_tle(satellite)]
        )
    )
    write(
        output / "receipt.json",
        dict(
            source_id=receipt["source_id"],
            origin_utc_ns=origin,
            cutoff_utc_ns=cutoff,
            catalogue_count=len(cat),
            regional_candidates=len(selected),
            regional_center=[REGION_LATITUDE, REGION_LONGITUDE],
            radius_km=250.0,
            candidate_selection_uses_evaluation_position=False,
            interpolation_checks=errors,
            provenance=[causal.provenance[i] for i in selected],
            bank_sha256=hashlib.sha256((output / "bank.npz").read_bytes()).hexdigest(),
            tracks_sha256=hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest(),
        ),
    )
    print(
        json.dumps(
            dict(
                source_id=receipt["source_id"],
                candidates=len(selected),
                maximum_interpolation_error_hz=max(x["maximum_error_hz"] for x in errors),
            )
        ),
        flush=True,
    )


def solve_bias(stats, initial, sigma_hz, budget=160):
    if sigma_hz == 0:
        return matching.solve(stats, initial, budget)
    winner = None
    for seed in matching.seed_calibrations(stats, initial, budget):
        beta = seed
        for gate in (4000.0, 2000.0, 1000.0, 600.0, 450.0):
            for _ in range(3):
                terms = profile_component_bias(stats, beta, bias_sigma_hz=sigma_hz)
                adjusted = dict(stats, mean=stats["mean"] - terms.bias_hz[stats["ci"]])
                new, ranks = matching.fit_shared(
                    adjusted, terms.best, terms.rms_hz, terms.aliases, beta, gate
                )
                change = np.max(np.abs(new - beta))
                beta = new
                if change < 0.01:
                    break
        terms = profile_component_bias(stats, beta, bias_sigma_hz=sigma_hz)
        active = np.flatnonzero(stats["active"])
        score = np.sum(
            np.minimum(stats["count"][active], 50)
            * np.minimum(terms.score[active, terms.best[active]], 900.0**2)
        )
        score += 150.0**2 * np.sum((beta[4:8] / (150 * matching.DRIFT_SIGMA_HZ_S)) ** 2)
        if winner is None or score < winner[0]:
            winner = (score, beta.copy(), ranks)
    return winner[1], winner[2]


def associate(recording, inputs, output, latitude, longitude, bias_sigma_hz=0.0):
    receipt = json.loads((inputs / "receipt.json").read_text())
    if hashlib.sha256((inputs / "bank.npz").read_bytes()).hexdigest() != receipt["bank_sha256"]:
        raise ValueError("orbit bank digest mismatch")
    if (
        hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest()
        != receipt["tracks_sha256"]
    ):
        raise ValueError("Graph membership changed after orbit preparation")
    with np.load(inputs / "bank.npz") as archive:
        sky = {key: archive[key] for key in archive.files}
    tracks = load_tracks(recording)
    merged = json.loads((recording / "merged.json").read_text())
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    frequency, elevation = frequency_grid(sky, times, latitude, longitude)
    bank = dict(time_s=times, doppler_0=frequency, elevation_deg=elevation, norad=sky["norad"])
    output.mkdir(parents=True, exist_ok=False)
    write(output / "orbit-receipt.json", receipt)
    receipt_reference = dict(
        path="orbit-receipt.json",
        sha256=hashlib.sha256((output / "orbit-receipt.json").read_bytes()).hexdigest(),
    )
    summaries = []
    for grouped in (False, True):
        groups = {}
        for track in tracks:
            owner = merged["result"]["ownership"][track["key"]] if grouped else track["key"]
            groups.setdefault(owner, []).append(track)
        groups = sorted(groups.items())
        stats = matching.statistics(groups, bank, {str(t["channel"]): 0.0 for t in tracks})
        for fitted_c in (False, True):
            initial = np.array(merged["calibration"]["beta"])
            if fitted_c:
                initial = np.r_[initial, 0.0]
            beta, ranks = solve_bias(stats, initial, bias_sigma_hz, budget=160)
            terms = profile_component_bias(stats, beta, bias_sigma_hz=bias_sigma_hz)
            best, rms, lifts, mse = terms.best, terms.rms_hz, terms.aliases, terms.residual_mse
            rows = []
            for ci, (key, members) in enumerate(groups):
                satellite = int(best[ci])
                checks = []
                for fi in np.flatnonzero(stats["ci"] == ci):
                    track = stats["fragments"][fi]
                    indexes = np.searchsorted(times, track["times"])
                    g = matching.group(track)
                    cal = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
                    if fitted_c:
                        cal += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
                    residual = track["values"] + lifts[fi, satellite] * matching.PERIOD - cal
                    residual -= track["rf_hz"] / 11.5e9 * frequency[satellite, indexes]
                    residual -= terms.bias_hz[ci, satellite]
                    checks.append(
                        matching.noise_screen(residual, track["times"])["noise_screen_pass"]
                    )
                visible = bool(stats["component_visible"][ci, satellite])
                runner_up = np.argsort(terms.score[ci])[1]
                second = float(np.sqrt(mse[ci, runner_up]))
                bias = float(terms.bias_hz[ci, satellite])
                rows.append(
                    dict(
                        component=key,
                        points=int(stats["count"][ci]),
                        fragments=len(members),
                        candidate_norad=int(sky["norad"][satellite]),
                        rms_hz=float(rms[ci]),
                        second_rms_hz=second,
                        visible=visible,
                        noise_screen_pass=all(checks),
                        compatible=bool(
                            visible
                            and rms[ci] <= 450
                            and all(checks)
                            and (bias_sigma_hz == 0 or abs(bias) <= 3 * bias_sigma_hz)
                        ),
                        component_bias_hz=bias,
                        penalized_frequency_score=float(terms.score[ci, satellite]),
                        active_curvature=bool(stats["active"][ci]),
                    )
                )
            summary = dict(
                source_id=receipt["source_id"],
                grouped=grouped,
                fitted_c=fitted_c,
                position_mode="fixed supplied evaluation site; not an estimated position",
                latitude_deg=latitude,
                longitude_deg=longitude,
                components=len(groups),
                graph_points=int(sum(stats["count"])),
                compatible_components=sum(r["compatible"] for r in rows),
                compatible_points=sum(r["points"] for r in rows if r["compatible"]),
                beta=beta.tolist(),
                calibration_ranks=ranks,
                drift_bound_hz_s=matching.DRIFT_BOUND_HZ_S,
                seed_budget=160,
                independent_identity_labels=False,
                position_error_km=None,
                component_bias_sigma_hz=bias_sigma_hz,
            )
            name = f"{'merged' if grouped else 'fragments'}_{'fitted_c' if fitted_c else 'c0'}"
            write(
                output / f"{name}.json",
                dict(summary=summary, components=rows, orbit_receipt=receipt_reference),
            )
            summaries.append(summary)
            print(json.dumps(summary), flush=True)
    write(output / "summary.json", summaries)
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summaries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "associate"))
    parser.add_argument("--recording", required=True, type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--component-bias-sigma-hz", type=float, default=0.0)
    args = parser.parse_args()
    if (
        args.output.resolve() == Path("/mnt/qnap01")
        or Path("/mnt/qnap01") in args.output.resolve().parents
    ):
        parser.error("QNAP is read-only")
    if args.action == "prepare":
        prepare(args.recording, args.output)
    else:
        if args.inputs is None or args.latitude is None or args.longitude is None:
            parser.error("association requires inputs and explicit evaluation coordinates")
        associate(
            args.recording,
            args.inputs,
            args.output,
            args.latitude,
            args.longitude,
            args.component_bias_sigma_hz,
        )
