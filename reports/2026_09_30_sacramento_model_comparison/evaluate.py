"""Evaluator-only geographic scoring after all planned attempts are terminal."""
from __future__ import annotations
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
# User-supplied DMS coordinate; unsurveyed and rounded to whole arcseconds.
REFERENCE = (37 + 50/60 + 57/3600, -(122 + 29/60 + 9/3600))
CENTER = (38.5816, -121.4944)
EARTH_KM = 6371.0088
MAP_RADIUS_KM = 6371.007180918475

def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

def destination(east, north):
    lat, lon = map(math.radians, CENTER)
    arc = math.hypot(east, north)/MAP_RADIUS_KM
    az = math.atan2(east, north)
    lat2 = math.asin(math.sin(lat)*math.cos(arc)+math.cos(lat)*math.sin(arc)*math.cos(az))
    lon2 = lon+math.atan2(math.sin(az)*math.sin(arc)*math.cos(lat), math.cos(arc)-math.sin(lat)*math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)

def distance_m(a, b):
    la, lo, lb, lob = map(math.radians, (*a,*b))
    h = math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lob-lo)/2)**2
    return 2000*EARTH_KM*math.asin(min(1., math.sqrt(h)))

def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    x = (len(values)-1)*q
    i = math.floor(x)
    return values[i] + (x-i)*(values[min(i+1,len(values)-1)]-values[i])

def summarize(rows):
    qualified = [r["error_m"] for r in rows if r["qualified"] and r["error_m"] is not None]
    diagnostic = [r["error_m"] for r in rows if r["error_m"] is not None]
    return {"planned": len(rows), "qualified": len(qualified), "returned_points": len(diagnostic),
            "statuses": dict(Counter(r["status"] for r in rows)),
            "median_m": quantile(qualified,.5), "p90_m": quantile(qualified,.9),
            "worst_m": max(qualified) if qualified else None,
            "sub_km_qualified_over_planned": sum(v<1000 for v in qualified)/len(rows) if rows else None,
            "diagnostic_returned_point_median_m": quantile(diagnostic,.5),
            "median_wall_s": quantile([r["seconds"] for r in rows],.5)}

def evaluate():
    freeze = json.loads((HERE / "execution-freeze.json").read_text())
    for path, expected in freeze["sources"].items():
        if digest(path) != expected:
            raise ValueError(f"source changed after freeze: {path}")
    rows = []
    for unit in freeze["units"]:
        for arm in freeze["arms"]:
            output = HERE / "runs" / f"{unit}-{arm}.json"
            receipt = output.with_suffix(".launch.json")
            if not receipt.exists():
                raise ValueError(f"planned attempt not terminal: {unit}/{arm}")
            launch = json.loads(receipt.read_text())
            row = {"unit": unit, "dataset": unit.split('-')[0], "arm": arm,
                   "status": launch["status"], "seconds": launch["seconds"],
                   "qualified": False, "error_m": None, "east_km": None, "north_km": None}
            if output.exists():
                seal = output.with_suffix(".seal.json")
                if not seal.exists() or json.loads(seal.read_text())["prediction_sha256"] != digest(output):
                    raise ValueError(f"prediction seal mismatch: {output}")
                pred = json.loads(output.read_text())
                if pred.get("reference_coordinate_accessed") is not False:
                    raise ValueError("missing explicit truth isolation declaration")
                point = pred.get("point_estimate")
                row["qualified"] = launch["returncode"] == 0 and pred["status"] in ("complete", "qualified", "completed") and pred.get("qualified", True)
                if point is None:
                    point = pred.get("diagnostic_unqualified_point")
                if point is not None:
                    east,north = float(point["east_km"]),float(point["north_km"])
                    if not math.isfinite(east+north) or math.hypot(east,north)>250.000001:
                        raise ValueError("nonfinite or outside-prior point estimate")
                    row.update(east_km=east,north_km=north,error_m=distance_m(destination(east,north),REFERENCE))
            rows.append(row)
    summary = {"schema": "sacramento-model-results/v1", "reference_latlon": REFERENCE,
               "reference_provenance": "User supplied 37 50 57 N, 122 29 9 W; unsurveyed, whole-arcsecond rounding; installation continuity assumed across DS9-DS11",
               "prior_center_error_m": distance_m(CENTER,REFERENCE),
               "execution_freeze_sha256": digest(HERE / "execution-freeze.json"),
               "overall": {}, "by_dataset": {}}
    baseline = {r["unit"]:r for r in rows if r["arm"] == "C1"}
    for arm in freeze["arms"]:
        selected = [r for r in rows if r["arm"] == arm]
        value = summarize(selected)
        pairs = [(r,baseline[r["unit"]]) for r in selected if r["qualified"] and baseline[r["unit"]]["qualified"]
                 and r["error_m"] is not None and baseline[r["unit"]]["error_m"] is not None]
        value["paired_qualified_vs_C1"] = len(pairs)
        value["paired_wins_vs_C1"] = sum(a["error_m"]<b["error_m"] for a,b in pairs)
        value["median_paired_delta_m"] = quantile([a["error_m"]-b["error_m"] for a,b in pairs],.5)
        summary["overall"][arm] = value
        summary["by_dataset"][arm] = {ds:summarize([r for r in selected if r["dataset"]==ds]) for ds in ("DS9","DS10","DS11")}
    with (HERE / "per-scan.csv").open("x") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (HERE / "summary.json").open("x") as stream:
        json.dump(summary,stream,indent=2,allow_nan=False);stream.write("\n")
    def fmt(x): return "—" if x is None else f"{x:,.0f}"
    lines = ["| Arm | Qualified / planned | Median m | P90 m | Returned-point median m (diagnostic) | Status counts |",
             "|---|---:|---:|---:|---:|---|"]
    for arm,value in summary["overall"].items():
        status = "; ".join(f"{k}: {v}" for k,v in value["statuses"].items())
        lines.append(f"| {arm} | {value['qualified']}/{value['planned']} | {fmt(value['median_m'])} | {fmt(value['p90_m'])} | {fmt(value['diagnostic_returned_point_median_m'])} | {status} |")
    with (HERE / "TABLE.md").open("x") as stream:
        stream.write("\n".join(lines)+"\n")
    print(json.dumps(summary,indent=2))

if __name__ == "__main__": evaluate()
