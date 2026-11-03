"""Retrospective field substitution: which TLE change reduces the fitted rate?"""

import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from fit_s01_69333_tle_parameter import OUTPUT, PRIOR, SOURCE, common_epoch_elements, perturb
from inventory_clipped_phase_cohort import load_study
from sgp4.api import Satrec

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.sky.propagation import ElementSetCatalogue

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run():
    source = json.loads((SOURCE / "bracketing_tles.json").read_text())
    base = Satrec.twoline2rv(*source["past"]["69333"]["lines"])
    later = Satrec.twoline2rv(*source["first_future_epoch"]["69333"]["lines"])
    epoch_ns = int(round(((base.jdsatepoch - 2440587.5) + base.jdsatepochF) * 86400e9))
    later_mean = common_epoch_elements(later, epoch_ns)
    dx = later_mean["e_cos_omega"] - base.ecco * np.cos(base.argpo)
    dy = later_mean["e_sin_omega"] - base.ecco * np.sin(base.argpo)
    variants = {
        "causal": base,
        "replace_e_cos_only": perturb(base, "e_cos_omega", dx),
        "replace_e_sin_only": perturb(base, "e_sin_omega", dy),
        "replace_both_e_components": perturb(perturb(base, "e_cos_omega", dx), "e_sin_omega", dy),
        "full_later_tle": later,
    }
    arms = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        fit = json.loads((PRIOR / arm / "fit_cap_2.7.json").read_text())
        old = json.loads((SOURCE / arm / "shared_shape_diagnostics.json").read_text())[
            "all_curves/shared_linear_rate"]
        keys = {r["component"] for r in old["rows"]}
        tracks = [t for t in study.tracks if t["key"] in keys]
        beta = np.array(fit["beta"])
        measurements = []
        for t in tracks:
            g = matching.group(t)
            hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
            if len(beta) == 9:
                hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            measurements.append(t["values"] - hw)
        arms[arm] = dict(tracks=tracks, y=measurements)
    tracks = arms["c0"]["tracks"]
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    phases = np.linspace(-15, 15, 3001)
    knots = np.arange(np.floor(min(times)) - 17, np.ceil(max(times)) + 18)
    summary = []
    for name, sat in variants.items():
        cat = ElementSetCatalogue(("STARLINK-37818",), (69333,), (sat,))
        p, v, usable = matching.ecef_states(cat, source["anchor_utc_ns"], knots)
        assert usable.all()
        sky = dict(time_s=knots, position_km=np.broadcast_to(p, (len(phases), len(knots), 3)),
                   velocity_km_s=np.broadcast_to(v, (len(phases), len(knots), 3)))
        geom = prepare_phase_geometry(sky, times, phases)
        f, *_ = phase_linear_frequency(geom, matching.LATITUDE, matching.LONGITUDE)
        for arm, data in arms.items():
            xy, xx = np.zeros(len(phases)), 0.0
            centered = []
            for t, y in zip(data["tracks"], data["y"], strict=True):
                q = t["rf_hz"] / 11.5e9
                r = y - q * f[:, np.searchsorted(times, t["times"])]
                r -= r.mean(axis=1)[:, None]
                x = q * (t["times"] - 65)
                x -= x.mean()
                centered.append((r, x))
                xy += r @ x
                xx += x @ x
            rate = xy / xx
            rss = sum(np.sum((r - rate[:, None] * x)**2, axis=1) for r, x in centered)
            best = int(np.argmin(rss))
            summary.append(dict(arm=arm, variant=name, rate_hz_s=float(rate[best]),
                                phase_s=float(phases[best]),
                                rms_hz=float(np.sqrt(rss[best] / 254))))
    write(OUTPUT / "retrospective_e_vector_substitution.json", dict(
        interpretation="fixed field substitutions from later TLE, not causal fitted corrections",
        eccentricity_components_compared_at_causal_epoch=True,
        delta_e_cos_omega=float(dx), delta_e_sin_omega=float(dy),
        mean_argument_latitude_preserved_at_causal_epoch=True,
        shared_phase_and_rate_reprofiled_identically=True,
        hardware_frozen=True, observations_and_bounds_matched=True,
        curved_tracks=9, curved_points=254, results=summary,
    ))
    print(json.dumps(summary), flush=True)
    render(summary)


def render(summary):
    rows = [r for r in summary if r["arm"] == "fitted_c"]
    labels = ["Causal TLE", "Change only\ne cos ω", "Change only\ne sin ω",
              "Change both\ne components", "Full later TLE"]
    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
    values = [r["rate_hz_s"] for r in rows]
    bars = ax.bar(labels, values, color=["steelblue", "teal", "teal", "teal", "darkorange"])
    ax.bar_label(bars, labels=[f"{v:+.2f}" for v in values], padding=4)
    ax.axhline(0, color="black", lw=0.8)
    ax.set(ylabel="Remaining shared frequency rate at 11.5 GHz (Hz/s)",
           title="69333: which later-TLE changes reduce the empirical slope?\n"
                 "Retrospective substitutions at the same epoch; same 9 curved tracks and hardware")
    ax.grid(axis="y", alpha=0.2)
    ax.set_ylim(min(0, min(values)) - 1, max(values) + 2)
    fig.savefig(OUTPUT / "eccentricity_update_attribution.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
