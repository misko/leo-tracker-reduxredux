"""Post-outcome diagnostic of the catastrophic validation case; no inference change."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from scipy.optimize import root

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
document = json.loads(
    (HERE.parent / "2026_10_08_position_error_iter01/baseline/DS17-008.json").read_text()
)
prior = RegionalPrior()
reference = root(
    lambda x: (
        np.asarray(coordinates(prior, x))
        - [document["reference_latitude_deg"], document["reference_longitude_deg"]]
    ),
    [-87, -81],
)
assert reference.success
method = document["methods"][0]
points = method["points"]
coarse = sorted(
    [p for p in points if p["spacing_km"] == 40 and p["converged"]], key=lambda p: p["objective"]
)
nearest = min(
    coarse, key=lambda p: np.linalg.norm(np.array([p["east_km"], p["north_km"]]) - reference.x)
)
distances = [np.linalg.norm(np.array([p["east_km"], p["north_km"]]) - reference.x) for p in points]
receipt = dict(
    session_id=document["session_id"],
    reference_chart_km=reference.x.tolist(),
    nearest_converged_coarse=nearest,
    nearest_coarse_rank=coarse.index(nearest) + 1,
    converged_coarse_count=len(coarse),
    nearest_sample_distance_km=float(min(distances)),
    points_within_30km=[p for p, d in zip(points, distances, strict=True) if d < 30],
    retained_basins=document["diagnostics"]["retained_basins"],
    search_stop_reason=method["search_stop_reason"],
    deferred_cells=method["deferred_cells"],
    recovery_attempted=document["diagnostics"]["recovery"]["attempted_points"],
    recovery_converged=document["diagnostics"]["recovery"]["converged_points"],
    reference_use="post-outcome visualization and search-coverage diagnosis only",
)
counterfactual = {}
for separation in (12.5, 25.0, 50.0, 80.0):
    retained = []
    for point in sorted(points, key=lambda p: (p["objective"], p["east_km"], p["north_km"])):
        if point["objective"] >= 1e90:
            continue
        xy = np.array([point["east_km"], point["north_km"]])
        if all(np.linalg.norm(xy - [p["east_km"], p["north_km"]]) >= separation for p in retained):
            retained.append(point)
        if len(retained) == 3:
            break
    counterfactual[str(separation)] = retained
receipt["diagnostic_only_basin_separation_counterfactuals"] = counterfactual
(HERE / "DS17-008-search.json").write_text(json.dumps(receipt, indent=2) + "\n")
valid = [p for p in points if p["converged"] and p["objective"] < 1e90]
fig, ax = plt.subplots(figsize=(8, 7), layout="constrained")
scatter = ax.scatter(
    [p["east_km"] for p in valid],
    [p["north_km"] for p in valid],
    c=[p["objective"] for p in valid],
    s=18,
    cmap="viridis_r",
)
fig.colorbar(scatter, ax=ax, label="Coarse/fine profile objective (lower is better)")
ax.scatter(*reference.x, marker="*", s=180, color="red", label="Reference (diagnosis only)")
basins = receipt["retained_basins"]
ax.scatter(
    [p["east_km"] for p in basins],
    [p["north_km"] for p in basins],
    facecolors="none",
    edgecolors="black",
    s=120,
    label="Three retained basins",
)
ax.set(
    title="DS17-008: selected basins cluster in the wrong region",
    xlabel="East of search prior (km)",
    ylabel="North of search prior (km)",
    aspect="equal",
)
ax.legend(fontsize=8)
ax.grid(alpha=0.2)
fig.savefig(HERE / "DS17-008-search.png", dpi=160)
plt.close(fig)
print(json.dumps(receipt, indent=2))
