"""Cheap position-only fusion controls, not a joint observation fit."""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from matplotlib.figure import Figure


def distance(a, b):
    a, b = np.deg2rad(a), np.deg2rad(b)
    d = b - a
    return float(12742.0176*np.arcsin(np.sqrt(np.clip(
        np.sin(d[0]/2)**2 + np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2, 0, 1))))


def main():
    out = Path(__file__).resolve().parent
    scans = json.loads((out.parent / "2026_09_23_sixteen_scan_position_resolution/scans.json").read_text())
    rows = []
    for prior, centre in (("sacramento", (38.5816, -121.4944)), ("reno", (39.5296, -119.8138))):
        scale = np.array([111.195, 111.195*np.cos(np.deg2rad(centre[0]))])
        for count in (1, 2, 4, 8, 16):
            subset = scans[:count]
            ll = np.array([[s["priors"][prior]["selected"]["latitude_deg"],
                            s["priors"][prior]["selected"]["longitude_deg"]] for s in subset])
            xy = (ll - centre)*scale
            for method in ("equal_scan_mean", "equal_scan_geometric_median"):
                if method == "equal_scan_mean" or count <= 2:
                    fit = xy.mean(axis=0)
                else:
                    result = minimize(lambda p: np.linalg.norm(xy-p, axis=1).sum(),
                                      np.median(xy, axis=0), method="Powell",
                                      options={"xtol": 1e-9, "ftol": 1e-10})
                    fit = result.x
                location = fit/scale + centre
                rows.append(dict(method=method, prior=prior, scan_count=count,
                    latitude_deg=float(location[0]), longitude_deg=float(location[1]),
                    track_count=sum(s["priors"][prior]["accounting"]["eligible_track_count"] for s in subset),
                    observation_count=sum(s["priors"][prior]["accounting"]["eligible_observation_count"] for s in subset),
                    scope="Position-only fusion of independently selected solutions; not an observation-level joint fit",
                    scatter_rms_km=float(np.sqrt(np.mean(np.sum((xy-fit)**2, axis=1))))))
    # Inference is complete before reference coordinates are introduced.
    reference = (37.84903264307456, -122.4856541910174)
    for row in rows:
        row["error_km"] = distance((row["latitude_deg"], row["longitude_deg"]), reference)
    (out / "ensemble_control.json").write_text(json.dumps(rows, indent=2)+"\n")
    fig = Figure(figsize=(10, 4), layout="constrained")
    axes = fig.subplots(1, 2)
    for ax, prior in zip(axes, ("sacramento", "reno")):
        for method in ("equal_scan_mean", "equal_scan_geometric_median"):
            data = [r for r in rows if r["prior"] == prior and r["method"] == method]
            ax.plot([r["scan_count"] for r in data], [r["error_km"] for r in data],
                    "o-", label=method.replace("equal_scan_", "").replace("_", " "))
        ax.set(title=prior.title()+" · position-only control", xlabel="Scans accumulated",
               ylabel="Reference error (km)", xticks=[1, 2, 4, 8, 16])
        ax.grid(alpha=.2); ax.legend()
    fig.savefig(out / "ensemble_control.png", dpi=160)
    print(json.dumps([r for r in rows if r["scan_count"] == 16], indent=2))


if __name__ == "__main__":
    main()
