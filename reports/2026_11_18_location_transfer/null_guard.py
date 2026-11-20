"""Attempt to reject unsupported regions using only held-out tracks and shifted-time controls."""

import json

import numpy as np

from models import (ARMS, CONFIG, HERE, bench, cold, coreset, latlon, physics_fit, save,
                    tile, whole_track_split)


def shifted(test, end, index):
    if not index:
        return test
    tracks = list(test["tracks"])
    for i in test["curved_indices"]:
        track = tracks[i]
        t = np.asarray(track["times"])
        width = max(0.,end-150.-np.ptp(t))
        if width <= 1.e-7:
            continue
        start = 150. + (t[0]-150. + index*width/20.) % width
        tracks[i] = dict(track, times=t-t[0]+start)
    return dict(tracks=tracks,curved_indices=test["curved_indices"])


def decision(series):
    valid = {k:v for k,v in series.items() if v[0] is not None}
    if not valid:
        return dict(accepted=False,winner=None,null_exceedances=None)
    winner = max(valid,key=lambda k:valid[k][0])
    observed = valid[winner][0]
    nulls = [max((v[j] for v in valid.values() if v[j] is not None),default=None) for j in range(1,20)]
    if any(value is None for value in nulls):
        return dict(accepted=False,winner=winner,null_exceedances=None)
    exceedances = sum(v>=observed for v in nulls)
    return dict(accepted=exceedances==0, winner=winner, observed=observed, largest_null=max(nulls),
                null_exceedances=exceedances)


def run():
    real=json.loads((HERE/"real-predictions.json").read_bytes())
    rows=[]
    for case in CONFIG["real_cases"]:
        graph=cold.read(cold.GRAPHS/f"{case}.json")
        train,test=whole_track_split(graph)
        count=min(64,len(test["curved_indices"]))
        meta=graph["metadata"]
        variants=[shifted(test,meta["duration_s"],i) for i in range(20)]
        scores={p:{a:{} for a in ARMS} for p in ("geometry12","full")}
        regional_fits={}
        for name in ("original","east150","north150"):
            center=latlon(bench.PANEL["search_center_latlon"],CONFIG["real_tile_offsets_east_north_km"][name])
            with tile(center):
                bank,_=cold.build_bank(case,meta,check_approximation=False)
            train_d=cold.descriptors(train,bank)
            bias=cold.bias_vote(train_d)
            candidates={"geometry12":coreset.select_tracks(train_d,bias)[0],"full":np.arange(len(train_d["ti"]))}
            fits={p:physics_fit(train_d,bias,selected,center)["arms"] for p,selected in candidates.items()}
            regional_fits[name]=fits
            original=next(r["time_holdout"]["scores"] for r in real if r["case"]==case and r["tile"]==name)
            for p in fits:
                for a in ARMS:
                    scores[p][a][name]=[]
            for i,variant in enumerate(variants):
                d=cold.descriptors(variant,bank)
                for p,arms in fits.items():
                    for a,fit in arms.items():
                        value=None
                        if d is not None and fit["status"]=="estimate" and count:
                            cost=cold.phase_cost(d["mean"],d["cov"],*fit["xy"],0.,shape_only=True)
                            value=float((1./(1.+cost.min(axis=1)/4.)).sum()/count)
                        if i==0:
                            previous=original.get(p,{}).get(a)
                            assert (value is None and previous is None) or abs(value-previous)<1.e-9
                        scores[p][a][name].append(value)
        decisions={}
        for p,arms in scores.items():
            decisions[p]={}
            for a,series in arms.items():
                decisions[p][a]=dict(true_offered=decision(series),
                                     true_omitted=decision({k:v for k,v in series.items() if k!="original"}))
        rows.append(dict(case=case, decisions=decisions, scores=scores,regional_fits=regional_fits))
        print(case,flush=True)
    save("time-shift-guard.json",rows)


if __name__=="__main__":
    run()
