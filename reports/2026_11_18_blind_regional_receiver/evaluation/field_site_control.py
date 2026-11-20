"""Post-scoring field diagnostic with a labeled prior from the other field site groups."""

import csv
import json
import math
from itertools import combinations
from pathlib import Path

from score import distance_km, distribution


def centroid(points):
    vectors = []
    for point in points:
        lat, lon = map(math.radians, point)
        cos_lat = math.cos(lat)
        vectors.append((cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat)))
    x, y, z = map(sum, zip(*vectors, strict=True))
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def main():
    lab = Path(__file__).resolve().parents[1]
    if not (lab / "locks" / "prediction-lock.json").exists():
        raise RuntimeError("predictions must be frozen first")
    truth = json.loads((lab / "field_private" / "truth.json").read_bytes())["cases"]
    truth = {r["id"]: r for r in truth if r["condition"] == "present"}
    old = json.loads((lab / "recorded_private" / "truth.json").read_bytes())["cases"][0]["latlon"]
    groups = {}
    for r in truth.values():
        groups.setdefault(r["site_group"], []).append(r["latlon"])
    centers = {g: centroid(points) for g, points in groups.items()}
    with (lab / "results/field/per_query.csv").open(newline="") as stream:
        radio = {r["id"]: float(r["forced_rf_error_km"]) for r in csv.DictReader(stream)
                 if r["condition"] == "present" and r["forced_rf_error_km"]}
    comparisons = []
    for k, r in truth.items():
        other = [c for g, c in centers.items() if g != r["site_group"]]
        comparisons.append({"id": k, "site_group": r["site_group"], "forced_rf_km": radio.get(k),
                            "other_sites_centroid_km": distance_km(centroid(other), r["latlon"]),
                            "development_roof_km": distance_km(old, r["latlon"])})
    prior = [r["other_sites_centroid_km"] for r in comparisons]
    sites = [r["latlon"] for r in truth.values()]
    result = {"site_groups": len(groups), "captures": len(truth),
              "max_between_field_positions_km": max(distance_km(a, b)
                                                     for a, b in combinations(sites, 2)),
              "old_roof_km": distribution(r["development_roof_km"] for r in comparisons),
              "other_sites_centroid_km": distribution(prior),
              "other_sites_centroid_within_5km": sum(x <= 5 for x in prior),
              "forced_rf_closer": sum(r["forced_rf_km"] is not None
                                      and r["forced_rf_km"] < r["other_sites_centroid_km"]
                                      for r in comparisons), "cases": comparisons}
    (lab / "results/field/site-control.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
