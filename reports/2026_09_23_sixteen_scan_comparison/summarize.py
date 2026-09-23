"""Combine frozen method outputs; reference coordinates are evaluation-only here."""
import csv
import json
import sys
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "tools/research"))
from sixteen_joint_compare import haversine_km


def main():
    points = json.loads((ROOT / "common_finalists.json").read_text())
    stability = json.loads((ROOT / "stability.json").read_text())
    soft = json.loads((ROOT / "soft_orbit/final/results.json").read_text())
    timing = json.loads((ROOT / "timing_robust/results.json").read_text())
    truth = (37.84903264307456, -122.4856541910174)
    for i, point in enumerate(points):
        point["error_km"] = haversine_km((point["latitude_deg"], point["longitude_deg"]), truth)
        point["common_integer_rms_hz"] = stability["full_rms_hz"][i]
    rows = []
    def add(method, lat, lon, objective, value, selection):
        index = min(range(len(points)), key=lambda i: abs(points[i]["latitude_deg"]-lat)+abs(points[i]["longitude_deg"]-lon))
        assert abs(points[index]["latitude_deg"]-lat)+abs(points[index]["longitude_deg"]-lon) < 1e-7
        rows.append(dict(method=method, location_id=points[index]["location_id"],
            latitude_deg=lat, longitude_deg=lon, error_km=points[index]["error_km"],
            common_integer_rms_hz=points[index]["common_integer_rms_hz"],
            native_objective=objective, native_value=value, selection=selection,
            track_count=553, observation_count=14043))
    p = points[0]
    add("Joint integer-timing search", p["latitude_deg"],p["longitude_deg"],
        "Duration-weighted capped RMS (Hz)",p["common_integer_rms_hz"],"Legacy evaluation-selected location and identities")
    for key, value in soft["training_selected_methods"].items():
        metric = ("hard_training_duration_weighted_mean_sse" if key.startswith("hard") else
                  "soft_training_duration_weighted_mean_negative_log_evidence")
        add(key, value["latitude_deg"],value["longitude_deg"],metric,value[metric],
            "Training-selected among five frozen finalists; candidate discovery touched evaluation")
    for method in sorted({r["method"] for r in timing["results"]}):
        value = min((r for r in timing["results"] if r["method"] == method), key=lambda r:r["objective_value"])
        add(method, value["latitude_deg"],value["longitude_deg"],value["objective_name"],value["objective_value"],
            "Five-finalist native-objective selection; see timing report for identity versus location selection")
    for p in points[-2:]:
        add(p["location_id"],p["latitude_deg"],p["longitude_deg"],"Equal-scan coordinate fusion",None,"No observation-level refit")
    result = dict(scope="Conditional prior-union candidates; shared Sac250/Reno500 intersection; not independent-prior global acquisition", points=points, methods=rows)
    (ROOT / "comparison.json").write_text(json.dumps(result,indent=2)+"\n")
    with (ROOT / "comparison.csv").open("w") as handle:
        writer = csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    lines = ["| Approach | Selected finalist | Error (km) | Common integer RMS (Hz) |", "|---|---|---:|---:|"]
    lines += [f"| {r['method']} | {r['location_id']} | {r['error_km']:.3f} | {r['common_integer_rms_hz']:.3f} |" for r in rows]
    (ROOT / "RESULTS_TABLE.md").write_text("\n".join(lines)+"\n")
    fig = Figure(figsize=(12,5),layout="constrained"); axes=fig.subplots(1,2)
    for i,p in enumerate(points):
        north=(p["latitude_deg"]-truth[0])*111.195
        east=(p["longitude_deg"]-truth[1])*111.195*np.cos(np.deg2rad(truth[0]))
        axes[0].scatter(east,north,s=70,label=f"{i+1}: {p['location_id'].replace('_coordinate_mean',' mean').replace('joint_basin_','basin ')}")
        axes[0].annotate(str(i+1),(east,north),xytext=(5,5),textcoords="offset points")
    axes[0].scatter(0,0,marker="*",s=160,c="black",label="Known position (evaluation only)")
    axes[0].set(xlabel="East of reference (km)",ylabel="North of reference (km)",title="All methods choose among the same five finalists")
    axes[0].axis("equal"); axes[0].grid(alpha=.2); axes[0].legend(fontsize=8)
    axes[1].scatter([p["common_integer_rms_hz"] for p in points],[p["error_km"] for p in points],s=70)
    for i,p in enumerate(points): axes[1].annotate(str(i+1),(p["common_integer_rms_hz"],p["error_km"]),xytext=(5,5),textcoords="offset points")
    axes[1].set(xlabel="Same baseline RMS evaluated at each position (Hz)",ylabel="Reference error (km)",title="Small residual differences can hide kilometre shifts")
    axes[1].grid(alpha=.2); fig.savefig(ROOT / "comparison.png",dpi=180)
    print("\n".join(lines))


if __name__ == "__main__": main()
