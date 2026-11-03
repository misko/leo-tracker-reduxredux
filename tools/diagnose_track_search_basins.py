"""Separate geographic coverage, observation compression and calibration budget.

The supplied site is a diagnostic point only. No point or fitted state from
this experiment is provided to a subsequent blind geographic initializer.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, solve_bias, write
from localize_merged_track_catalogue import discovery_subset, raw_curvature

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.track_catalogue_geometry import frequency_grid

ROOT = Path(__file__).resolve().parents[1]


def score(stats, beta):
    terms = profile_component_bias(stats, beta, bias_sigma_hz=1000.0)
    active = np.flatnonzero(stats["active"])
    result = np.sum(
        np.minimum(stats["count"][active], 50)
        * np.minimum(terms.score[active, terms.best[active]], 900.0**2)
    )
    result += 150.0**2 * np.sum((beta[4:8] / (150 * matching.DRIFT_SIGMA_HZ_S)) ** 2)
    return float(result)


def run(recording, inputs, output):
    output.mkdir(parents=True, exist_ok=False)
    with np.load(inputs / "bank.npz") as archive:
        sky = {key: archive[key] for key in archive.files}
    tracks = load_tracks(recording)
    merged = json.loads((recording / "merged.json").read_text())
    groups = {}
    for t in tracks:
        owner = merged["result"]["ownership"][t["key"]]
        groups.setdefault(owner, []).append(t)
    groups = sorted(groups.items())
    subsets = discovery_subset(groups)
    old = ROOT / "reports/2026_10_17_ds22_merged_satellites"
    endpoint = json.loads((old / "position_pilot/c0/fit.json").read_text())["endpoint"]
    sites = [
        ("regional_center", 37.5, -122.0),
        ("failed_endpoint", endpoint["latitude_deg"], endpoint["longitude_deg"]),
        ("supplied_evaluation_site", 37.849061591561885, -122.48574968092912),
    ]
    flags = np.array([raw_curvature(t) for _, members in groups for t in members])
    active = np.array([any(raw_curvature(t) for t in members) for _, members in groups])
    rows = []
    for name, lat, lon in sites:
        for full, selected in ((False, subsets), (True, groups)):
            times = np.unique(
                np.concatenate([t["times"] for _, members in selected for t in members])
            )
            started = time.monotonic()
            frequency, elevation = frequency_grid(sky, times, lat, lon)
            geometry_s = time.monotonic() - started
            started = time.monotonic()
            bank = dict(
                time_s=times, doppler_0=frequency, elevation_deg=elevation, norad=sky["norad"]
            )
            stats = matching.statistics(selected, bank, {str(t["channel"]): 0.0 for t in tracks})
            stats["active"] = active.copy()
            stats["fragment_active"] = flags.copy()
            stats_s = time.monotonic() - started
            for fitted_c in (False, True):
                initial = np.array(merged["calibration"]["beta"])
                if fitted_c:
                    initial = np.r_[initial, 0.0]
                for budget in (4, 160):
                    started = time.monotonic()
                    beta, ranks = solve_bias(stats, initial, 1000.0, budget)
                    row = dict(
                        site=name,
                        latitude_deg=lat,
                        longitude_deg=lon,
                        full_data=full,
                        fitted_c=fitted_c,
                        seed_budget=budget,
                        score=score(stats, beta),
                        points=int(sum(stats["count"])),
                        geometry_s=geometry_s,
                        statistics_s=stats_s,
                        fit_s=time.monotonic() - started,
                        beta=beta.tolist(),
                        ranks=ranks,
                    )
                    rows.append(row)
                    write(output / "results.json", rows)
                    print(
                        json.dumps(
                            {
                                k: row[k]
                                for k in (
                                    "site",
                                    "full_data",
                                    "fitted_c",
                                    "seed_budget",
                                    "score",
                                    "geometry_s",
                                    "statistics_s",
                                    "fit_s",
                                )
                            }
                        ),
                        flush=True,
                    )
    for fitted_c in (False, True):
        arm = "fitted_c" if fitted_c else "c0"
        for name in ("failed_endpoint", "supplied_evaluation_site"):
            row = next(
                r
                for r in rows
                if r["site"] == name
                and r["full_data"]
                and r["fitted_c"] == fitted_c
                and r["seed_budget"] == 160
            )
            if name == "failed_endpoint":
                reference = json.loads((old / f"position_pilot/{arm}/fit.json").read_text())[
                    "score"
                ]
            else:
                source = json.loads(
                    (old / f"catalogue/DS22-001/bias_1000/merged_{arm}.json").read_text()
                )
                b = np.array(source["summary"]["beta"])
                reference = sum(
                    min(r["points"], 50) * min(r["penalized_frequency_score"], 900**2)
                    for r in source["components"]
                    if r["active_curvature"]
                )
                reference += 150**2 * sum((b[4:8] / 300) ** 2)
            if not np.isclose(row["score"], reference, rtol=1e-10):
                raise ValueError(f"saved scientific score does not replay: {name} {arm}")
    write(
        output / "receipt.json",
        dict(
            saved_scores_replayed=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            use="diagnostic only; not a geographic initializer",
            points=sites,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.recording, a.inputs, a.output)
