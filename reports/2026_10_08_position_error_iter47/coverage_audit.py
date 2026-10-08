"""Post-hoc spatial coverage audit of newly consumed DS16-046; no new fits."""

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter30"))
from audit import distance, reference_xy  # noqa: E402

from leo.analysis.regional_position_search import (  # noqa: E402
    SpatialEvaluation,
    SpatialSearch,
    distinct_basins,
)
from leo.contracts.regional_position import RegionalPrior  # noqa: E402


def main():
    sources = {
        kind: REPORTS / f"2026_10_08_position_error_iter45/{kind}/DS16-046.json"
        for kind in ("baselines", "regions", "results")
    }
    docs = {key: json.loads(path.read_text()) for key, path in sources.items()}
    doc = docs["baselines"]
    prior = RegionalPrior()
    ref = reference_xy(prior, doc)
    points = sorted(
        doc["methods"][0]["points"],
        key=lambda r: (
            r["objective"] if r["objective"] is not None else 1e100,
            r["east_km"],
            r["north_km"],
        ),
    )
    for rank, row in enumerate(points, 1):
        row.update(rank=rank, error_km=distance(prior, [row["east_km"], row["north_km"]], doc))
    search = SpatialSearch(
        tuple(
            SpatialEvaluation(r["east_km"], r["north_km"], r["spacing_km"], r["objective"])
            for r in points
            if r["objective"] is not None
        ),
        0,
        "post-hoc audit",
    )
    simulations = {}
    for separation in (12.5, 25, 40, 50, 75, 100, 150):
        selected = distinct_basins(search, count=3, minimum_separation_km=separation)
        simulations[str(separation)] = [
            dict(**asdict(r), error_km=distance(prior, [r.east_km, r.north_km], doc))
            for r in selected
        ]
    for sep, key in ((12.5, "baselines"), (25, "regions")):
        saved = docs[key]["diagnostics"]["retained_basins"]
        assert [(r["east_km"], r["north_km"]) for r in simulations[str(sep)]] == [
            (r["east_km"], r["north_km"]) for r in saved
        ]
    assert sorted((r["east_km"], r["north_km"], r["spacing_km"]) for r in points) == sorted(
        (r["east_km"], r["north_km"], r["spacing_km"])
        for r in docs["regions"]["methods"][0]["points"]
    )
    nearest = min(points, key=lambda r: r["error_km"])
    best_near = next(r for r in points if r["error_km"] < 25)
    output = dict(
        scope="Post-hoc consumed-case audit; no fit or benchmark replacement",
        input_sha256={
            str(p.relative_to(REPORTS)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources.values()
        },
        points=points,
        reference_xy_km=ref.tolist(),
        nearest=nearest,
        best_within25km=best_near,
        retention_simulations=simulations,
    )
    (HERE / "audit.json").write_text(json.dumps(output, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    xy = np.array([[r["east_km"], r["north_km"]] for r in points])
    for ax in axes:
        artist = ax.scatter(
            xy[:, 0], xy[:, 1], c=[r["rank"] for r in points], cmap="viridis_r", s=15
        )
        ax.scatter(*ref, color="black", marker="*", s=140, label="Reference: audit only")
        for separation, marker, color in (
            (12.5, "s", "red"),
            (25, "+", "orange"),
            (50, "o", "blue"),
        ):
            chosen = np.array([[r["east_km"], r["north_km"]] for r in simulations[str(separation)]])
            ax.scatter(
                chosen[:, 0],
                chosen[:, 1],
                marker=marker,
                facecolors="none",
                edgecolors=color,
                s=100,
                label=f"Separation {separation:g} km",
            )
        ax.set(xlabel="East of prior km", ylabel="North of prior km", aspect="equal")
        ax.grid(alpha=0.2)
    axes[0].set_title("All 400 sampled points")
    axes[0].legend(fontsize=7)
    axes[1].set(xlim=(-115, -65), ylim=(-110, -60), title="Correct region was refined to 5 km")
    fig.colorbar(artist, ax=axes, label="Coarse score rank")
    fig.savefig(HERE / "coverage.png", dpi=160)
    text = """# Iteration 47: DS16-046 sampled the correct region, then discarded it

**The new 265 km failure is a region-retention failure, not simply a missing-grid
or numerical-convergence failure.** DS16-046 (`scan-fw-c6c51bfeb6a7c3d9`) lies
outside the earlier 48-member DS16 subset. Its bounded-recovery baseline error is
265.277 km fitted-c / 264.604 km zero-c; the frozen research candidate produces
265.789 / 261.743 km. Every research stage passes its convergence check.

![Grid coverage and retained regions](coverage.png)

The 400-point grid samples and refines the correct neighborhood through 40, 20,
10 and 5 km spacing. Its nearest evaluated point is 3.521 km from the reference
and converged. A converged point at (−90,−90) km, only 9.484 km from the reference,
ranks **13th** among all sampled points. The nearest 5 km point ranks 136th.

However, all three ordinary retained regions are near (30,170) km, far to the
northeast. The existing 25 km separation replay still retains three regions in
that same distant area. The later local fits cannot bridge roughly 265 km with
25 km local search disks. Timing pruning and clock refinements optimize this
already wrong branch; they do not recover the discarded region.

## Post-hoc retention replay, without fitting

The production `distinct_basins` function is replayed on exactly the saved scores.
The 12.5 and 25 km outputs exactly reproduce the archived retained regions.
Larger spacings below are exploratory diagnostics on this consumed case, not
independent validation and not localization results.

| Minimum separation km | Retained centers east,north km | Closest center to reference km |
|---:|---|---:|
"""
    for sep, rows in simulations.items():
        centers = "; ".join(f"({r['east_km']:g},{r['north_km']:g})" for r in rows)
        text += f"| {sep} | {centers} | {min(r['error_km'] for r in rows):.3f} |\n"
    text += """
At 40 km separation, the correct neighborhood enters the third slot; at 50 km
it enters the second. This identifies a concrete candidate experiment: preserve
the existing regions and add widely separated regions through complete fitting,
then select by a matched model score. Merely preserving a good neighborhood does
not prove the final likelihood will select it, as the DS18 diagnostic shows.

No reference coordinates enter the replay's ranking or selection; they only
measure the audit distances afterward. The spacing sweep is informed by the
observed failure and must not be called a fresh validation. All c=0/fitted-c
benchmark values remain unchanged. No new fits, production changes or RF
collection occurred. Full-dataset completion continues in iteration45.

[audit.json](audit.json) contains every point, score, convergence flag, rank and
input digest. This audit explains where the accurate region was lost; it does
not yet explain why its coarse score was worse or guarantee an operational fix.
"""
    (HERE / "README.md").write_text(text)


if __name__ == "__main__":
    main()
