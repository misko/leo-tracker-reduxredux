"""Independently score geographic outputs, explicit non-fixes and RF fit."""

from collections import Counter, defaultdict
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
from statistics import mean, median

import numpy as np

HERE = Path(__file__).resolve().parent
PILOTS = HERE.parent / "2026_11_18_embedded_prototypes"


def read(path):
    return json.loads(path.read_bytes())


def distance(a, b):
    lat, other = map(math.radians, (a[0], b[0]))
    dlon = math.radians(b[1]-a[1])
    q = math.sin((lat-other)/2)**2 + math.cos(lat)*math.cos(other)*math.sin(dlon/2)**2
    return 12742.0176 * math.asin(math.sqrt(min(1., q)))


def stats(values):
    values = [q for q in values if q is not None]
    if not values:
        return {"n": 0, "median": None, "p90": None, "max": None}
    return dict(n=len(values), median=median(values), p90=float(np.percentile(values, 90)), max=max(values))


def require_complete(rows, keys, expected):
    observed = Counter(tuple(row[key] if not isinstance(row[key], list) else tuple(row[key]) for key in keys)
                       for row in rows)
    if observed != Counter(expected):
        raise ValueError(f"Incomplete or duplicate {keys} scenarios")


def score_rows(predictions, scenario, real_ref=None):
    scored = []
    for r in predictions:
        truth = real_ref if real_ref is not None else r["truth"]
        location = r["tile"] if real_ref is not None else r["region"]
        offset = "real" if real_ref is not None else ",".join(map(str, r["offset"]))
        for method, experiment in r["methods"].items():
            assert set(experiment["arms"]) == {"c0", "fitted_c"}
            for arm, fit in experiment["arms"].items():
                estimate = fit["status"] == "estimate"
                if estimate:
                    assert all(math.isfinite(x) for x in fit["latlon"])
                scored.append(dict(scenario=scenario, case=r["case"], location=location, offset=offset, orbit=r.get("orbit_mode", "real"),
                                   height_km=r.get("altitude_km"), west_only=r.get("west_only"), method=method, arm=arm,
                                   status=fit["status"], error_km=distance(fit["latlon"], truth) if estimate else None,
                                   rms_hz=fit.get("rms_hz"), interior=max(abs(v) for v in fit["xy"]) < 12.49 if estimate else None,
                                   clean_assigned=experiment.get("clean_assigned"),
                                   correct_clean_ids=experiment.get("correct_clean_ids")))
    return scored


def metrics(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["method"], r["arm"]].append(r)
    result = {}
    for (method, arm), group in grouped.items():
        errors = stats(r["error_km"] for r in group)
        trials = len(group)
        rms = stats(r["rms_hz"] for r in group)
        within = sum(r["error_km"] is not None and r["error_km"] <= 5. for r in group)
        denominator = sum(r["clean_assigned"] or 0 for r in group)
        correct = sum(r["correct_clean_ids"] or 0 for r in group)
        result.setdefault(method, {})[arm] = dict(attempts=trials, geo_km=errors, within_5km=within,
                                                   selected_rf_rms_hz=rms, matched_id_numerator=correct,
                                                   matched_id_denominator=denominator)
    return result


def verify_original(predictions):
    coreset = read(PILOTS / "06_coreset/result.json")
    networks = read(PILOTS / "10_network/result.json")
    max_delta = 0.
    for row in [r for r in predictions if r["tile"] == "original"]:
        case = row["case"]
        base = coreset["checks"]["case_checks"][case]["comparison"]
        ml = next(r for r in networks["cases"] if r["case"] == case)
        for arm in ("c0", "fitted_c"):
            controls = {n: base[s]["arms"][arm]["latlon"] for n,s in (
                ("geometry12", "geometry12"), ("full", "full"), ("longest12", "longest12"))}
            controls.update(coordinate_network=ml["arms"][arm]["latlon"], shape_grid=ml["grid_peak_latlon"])
            for method, previous in controls.items():
                delta = distance(row["methods"][method]["arms"][arm]["latlon"], previous)
                max_delta = max(max_delta, delta)
    assert max_delta < 1.e-5, max_delta
    return max_delta


def real_diagnostics(rows, cases, real_ref):
    policy_diagnostics = defaultdict(dict)
    arm_names = ("c0", "fitted_c")
    for method in rows[0]["methods"]:
        for arm in arm_names:
            spreads, remote_errors = [], []
            interiors = 0
            for case in cases:
                same = [r for r in rows if r["case"] == case]
                near = [r["methods"][method]["arms"][arm] for r in same if not r["tile"].endswith("150")]
                if all(x["status"]=="estimate" for x in near):
                    spread = max(distance(a["latlon"], b["latlon"]) for a,b in itertools.combinations(near,2))
                    spreads.append({"case":case,"km":spread})
                for r in (r for r in same if r["tile"].endswith("150")):
                    f = r["methods"][method]["arms"][arm]
                    if f["status"]=="estimate":
                        remote_errors.append(distance(f["latlon"], real_ref))
                        interiors += max(map(abs, f["xy"])) < 12.49
            policy_diagnostics[method][arm] = dict(per_case_near_spread=spreads, near_spread_km=stats(x["km"] for x in spreads),
                                                   wrong_attempts=2*len(cases), wrong_published=len(remote_errors),
                                                   wrong_interior=interiors, wrong_error_km=stats(remote_errors))
    contests = {}
    for method in ("geometry12","full"):
        contests[method] = {}
        for arm in arm_names:
            results = []
            for case in cases:
                scores = {r["tile"]:r["time_holdout"]["scores"].get(method,{}).get(arm) for r in rows
                          if r["case"]==case and "time_holdout" in r}
                rivals = [v for k,v in scores.items() if k!="original" and v is not None]
                gap = scores["original"] - max(rivals) if scores["original"] is not None and rivals else None
                results.append(dict(case=case,scores=scores,margin=gap))
            contests[method][arm] = dict(cases=results, correct_top=sum(r["margin"] is not None and r["margin"]>0 for r in results),
                                         all_three_scored=sum(all(v is not None for v in r["scores"].values()) for r in results),
                                         margin=stats(r["margin"] for r in results))
    return dict(methods=policy_diagnostics, time_holdout=contests)


def calibration(rows):
    pairs = defaultdict(dict)
    for r in rows:
        pairs[r["case"],r["location"],r["offset"],r["method"]][r["arm"]] = r
    result = defaultdict(lambda: defaultdict(list))
    for (*_, method), a in pairs.items():
        for key in ("error_km", "rms_hz"):
            if all(row[key] is not None for row in a.values()):
                result[method][key].append(a["fitted_c"][key]-a["c0"][key])
    return {m:{k:dict(n=len(v), median_change=median(v), improved=sum(d<0 for d in v))
               for k,v in fields.items()} for m,fields in result.items()}


def write_csv(name, rows):
    with (HERE/name).open("w", newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def synthetic_summary(scores, regions, modes):
    summary = {}
    for mode in modes:
        rows = [r for r in scores if r["orbit"]==mode]
        summary[mode] = dict(overall=metrics(rows),calibration=calibration(rows),
            by_region={region:metrics(r for r in rows if r["location"]==region) for region in regions},
            by_height={str(h):metrics(r for r in rows if r["height_km"]==h) for h in (0.,1.2)},
            by_sky={str(s):metrics(r for r in rows if r["west_only"]==s) for s in (True,False)})
    return summary


def main():
    config = read(HERE/"protocol.json")
    real = read(HERE/"real-predictions.json")
    synth = read(HERE/"synthetic-predictions.json")
    updated = read(HERE/"updated-orbit-predictions.json")
    confirmation = read(HERE/"confirmation-predictions.json")
    site26 = read(PILOTS/"scoring-reference.json")
    reference = [site26["latitude_deg"],site26["longitude_deg"]]
    ds29file = Path("/srv/bulk/leo-dev/ds29-20261113/snapshot/evaluation-references.json")
    ds29 = read(ds29file)
    sites29 = Counter((r["latitude_deg"], r["longitude_deg"]) for r in ds29.values())
    require_complete(real, ("case","tile"), itertools.product(config["real_cases"],config["real_tile_offsets_east_north_km"]))
    for group in (synth,updated):
        require_complete(group, ("case","region","offset","orbit_mode"),
                         itertools.product(config["synthetic_cases"],config["synthetic_centers_latlon"],
                                           map(tuple,config["synthetic_offsets_east_north_km"]),config["synthetic_orbits"]))
    check_groups=defaultdict(list)
    for r in confirmation:
        check_groups[r["case"],r["region"],r["orbit_mode"]].append(np.sign(r["offset"]).tolist())
    assert set(check_groups)==set(itertools.product(config["confirmation_cases"],config["confirmation_centers_latlon"],config["synthetic_orbits"]))
    assert all(sorted(v)==[[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]] for v in check_groups.values())
    points={m:{tuple(r["truth"]) for r in confirmation if r["orbit_mode"]==m} for m in config["synthetic_orbits"]}
    assert len(points["causal"])==32 and points["causal"]==points["later"]
    training = read(PILOTS/"10_network/result.json")["checks"]
    ml_inputs = {r["snapshot"].split("-")[1] for k in ("training_snapshots","validation_snapshots") for r in training[k]}
    assert not any(r["solver_snapshot"].split("-")[1] in ml_inputs for r in synth+confirmation)
    origin_delta = verify_original(real)
    local = [r for r in real if not r["tile"].endswith("150")]
    for r in local:
        lat, lon = r["center"]
        assert abs(reference[0]-lat)*111 <= 12.5
        assert abs(reference[1]-lon)*111.32*math.cos(math.radians(lat)) <= 12.5
    assert all(r["simulation"]["generated"] == 48 for r in synth+updated+confirmation)
    real_scores = score_rows(real, "recorded", reference)
    synth_scores = score_rows(synth, "first_later_file")
    updated_scores = score_rows(updated, "updated_elements")
    confirmation_scores = score_rows(confirmation, "new_regions_and_offsets")
    write_csv("geographic-scores.csv",real_scores+synth_scores+updated_scores+confirmation_scores)
    results = dict(inventory=dict(ds26_reference=site26["authority"],ds29_scans=len(ds29),ds29_unique_locations=len(sites29),
                                  ds26_constant_error_on_ds29_m=[1000*distance(reference,list(ll)) for ll in sites29],
                                  ds29_reference_sha256=hashlib.sha256(ds29file.read_bytes()).hexdigest()),
                   original_max_reproduction_error_km=origin_delta,
                   real=real_diagnostics(real, config["real_cases"], reference),
                   real_original=metrics(r for r in real_scores if r["location"]=="original"),
                   protocol_sha256=hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest())
    guard=read(HERE/"time-shift-guard.json")
    require_complete(guard,("case",),[(c,) for c in config["real_cases"]])
    results["time_shift_guard"]={}
    for policy in ("geometry12","full"):
        results["time_shift_guard"][policy]={}
        for a in ("c0","fitted_c"):
            by_mode={}
            for scenario in ("true_offered","true_omitted"):
                items=[r["decisions"][policy][a][scenario] for r in guard]
                published=[distance(r["regional_fits"][item["winner"]][policy][a]["latlon"],reference)
                           for r,item in zip(guard,items,strict=True) if item["accepted"]]
                by_mode[scenario]=dict(attempts=len(items), accepted=sum(x["accepted"] for x in items),
                                       correct_accepted=sum(x["accepted"] and x["winner"]=="original" for x in items),
                                       wrong_accepted=sum(x["accepted"] and x["winner"]!="original" for x in items),
                                       abstentions=sum(not x["accepted"] for x in items),
                                       published_early_position_error_km=stats(published))
            results["time_shift_guard"][policy][a]=by_mode
    for key, scored, regions in (("synthetic",synth_scores,config["synthetic_centers_latlon"]),
                                 ("updated_synthetic",updated_scores,config["synthetic_centers_latlon"]),
                                 ("confirmation",confirmation_scores,config["confirmation_centers_latlon"])):
        results[key]=synthetic_summary(scored,regions,config["synthetic_orbits"])
    files = list(HERE.glob("*predictions.json")) + [HERE/"time-shift-guard.json",PILOTS/"06_coreset/coreset.py", PILOTS/"support/cold_replay.py",
                                                     PILOTS/"10_network/weights.npy",PILOTS/"10_network/network.py"]
    results["input_sha256"]={str(f.relative_to(HERE.parent)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)}
    (HERE/"summary.json").write_text(json.dumps(results,indent=1,allow_nan=False)+"\n")


if __name__=="__main__":
    main()
