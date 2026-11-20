"""Read-only evaluation after inference. Errors use the campaign's spherical distance."""

from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np

import cold_replay as cold


ROOT = Path(__file__).resolve().parent
ARMS = ("c0", "fitted_c")
REFERENCE = cold.read(Path("/srv/bulk/leo/research/ds26-20261030/evaluation-site.json"))
TARGET = REFERENCE["latitude_deg"], REFERENCE["longitude_deg"]
RESULTS = cold.WORK / "results"


def distance(latlon):
    a,b = np.deg2rad(latlon)
    c,d = np.deg2rad(TARGET)
    h = np.sin((a-c)/2)**2+np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2
    return float(12742.0176*np.arcsin(np.sqrt(h)))


def score_xy(xy):
    return distance((cold.CENTER[0]+xy[1]/111.,cold.CENTER[1]+xy[0]/(111.32*np.cos(np.deg2rad(cold.CENTER[0])))))


def distribution(numbers):
    if not len(numbers):
        return None
    values = np.array(numbers,float)
    assert np.isfinite(values).all()
    return dict(n=len(values), mean=float(np.mean(values)),median=float(np.median(values)),
                p95=float(np.percentile(values,95)),maximum=float(values.max()),minimum=float(values.min()))


def summarize(records,labels):
    out = {}
    for method in sorted({method for label in labels for method in records[label]}):
        out[method] = {}
        for arm in ARMS:
            rows = [records[label][method][arm] for label in labels if method in records[label]
                    and records[label][method][arm].get("status")=="estimate"]
            if not rows:
                continue
            out[method][arm] = dict(errors_km=distribution([r["error_km"] for r in rows]),
                                    rf_rms_hz=distribution([r["rms_hz"] for r in rows]),
                                    boundary=sum(r.get("on_boundary",False) for r in rows),
                                    over5km=sum(r["error_km"]>5 for r in rows),
                                    tracks=distribution([r["tracks"] for r in rows]))
    return out


def main():
    saved = cold.read(ROOT/"cold-panel.json")
    panel = saved["cases"]
    rows = list(saved["rows"])
    if (ROOT/"cold-remainder.json").exists():
        rows.extend(cold.read(ROOT/"cold-remainder.json")["rows"])
    extra = {r["case"]:r for r in cold.read(ROOT/"alternative-panel.json")["rows"]}
    if (ROOT/"alternative-remainder.json").exists():
        rest = cold.read(ROOT/"alternative-remainder.json")["rows"]
        assert not set(extra).intersection(r["case"] for r in rest)
        extra.update({r["case"]:r for r in rest})
    hist = cold.read(RESULTS/"repeat-comparison.json")
    common = set(hist["same_successful_cases"])
    statuses = {(r["case"],r["repetition"]):r["status"] for r in hist["coverage"] if r["role"]=="baseline"}
    records = {}
    agreements = Counter()
    times = defaultdict(list)
    work = []
    prep = []
    for r in rows:
        case = r["case"]
        assert case not in records
        methods = dict(r.get("results",{}))
        methods.update(extra.get(case,{}).get("results",{}))
        if r["status"]=="processed":
            for arms in methods.values():
                for arm in ARMS:
                    row = arms[arm]
                    if row["status"]=="estimate":
                        row["error_km"] = score_xy(row["xy"])
        if statuses.get((case,0))=="complete":
            path = RESULTS / f"{case}-r0/baseline/worker-result.json"
            v5 = cold.read(path)["arms"]
            methods["v5"] = {}
            for arm in ARMS:
                a = v5[arm]
                methods["v5"][arm] = dict(status="estimate",error_km=distance(a["endpoint_latlon"]),
                                          tracks=a["tracks"],rms_hz=a["residual_rms_hz"])
            if r["status"]=="processed" and case in panel:
                doc = cold.read(cold.GRAPHS / f"{case}.json")
                known = v5["c0"]["owners"]
                nominated = dict(zip(r["traces"]["joint"]["tracks"],r["traces"]["joint"]["ids"]))
                for ti,ids in zip(r["shortlist"]["tracks"],r["shortlist"]["ids"]):
                    names = [known.get(j) for j in doc["tracks"][ti]["observation_ids"]]
                    owner,count = Counter(names).most_common(1)[0]
                    if owner is not None and count/len(names)>=.8:
                        agreements["strong_v5_tracks"] += 1
                        agreements["in_top12"] += int(owner in ids)
                        if ti in nominated:
                            agreements["selected_strong_v5_tracks"] += 1
                            agreements["selected_same_id"] += int(owner==nominated[ti])
        records[case] = methods
    for case in sorted(common):
        for repeat in (0,1):
            trial = cold.read(RESULTS/f"{case}-r{repeat}/baseline/worker-result.json")
            clock = cold.read(RESULTS/f"{case}-r{repeat}/baseline-execution.json")["process"]["wall_seconds"]
            work.append(clock)
            for entry in trial["stage_timings"]:
                times[entry["stage"]].append(entry["seconds"])
    for row in rows:
        if row["status"]=="processed":
            prep.append(row["bank"])
    pcommon = [c for c in panel if all(a.get("fitted_c",{}).get("status")=="estimate"
                                       for a in records[c].values()) and "v5" in records[c]
               and len(records[c])==6]
    sorted_cases = sorted(records)
    v5common = [c for c in sorted_cases if "v5" in records[c] and "joint" in records[c]
                and records[c]["joint"]["fitted_c"]["status"]=="estimate"]
    no_v5 = [c for c in sorted_cases if "v5" not in records[c]]
    output = dict(panel=panel,all_labels=sorted_cases,panel_common_all_six=pcommon,
                  v5_joint_common=v5common,alt_timing={k:distribution([r["seconds"][k] for r in extra.values()
                    if "seconds" in r]) for k in ("soft_grid","consensus")},
                  stage_seconds={k:distribution(v) for k,v in times.items()},wall=distribution(work),
                  bank={k:distribution([r[k] for r in prep]) for k in ("regional","eligible","knots",
                       "float32_bytes","center_p95_hz","corners_p95_hz")},
                  shortlist_v5_agreement=agreements,center_only_error_km=distance(cold.CENTER),
                  panel_all_available=summarize(records,panel),panel_matched=summarize(records,pcommon),
                  full_available=summarize(records,sorted_cases),common_v5_joint=summarize(records,v5common),
                  without_v5=summarize(records,no_v5),
                  status_counts=dict(Counter(r["status"] for r in rows)),
                  per_case=records)
    (ROOT/"evaluation.json").write_text(json.dumps(output,allow_nan=False))


if __name__=="__main__":
    main()
