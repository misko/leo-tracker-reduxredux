"""Matched all-basin joint receiver-identity experiment."""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np

from objective import PairedObjective
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
spec = importlib.util.spec_from_file_location("frequency_continuation", PARENT/"annealing/experiment.py")
previous = importlib.util.module_from_spec(spec); spec.loader.exec_module(previous)
loader, controls = previous.loader, previous.controls


def pool_for(case, old):
    rows = previous.source_pool(case, old)
    for folder in ("annealing", "timing_search"):
        doc = json.loads((PARENT/folder/f"{case}.json").read_text())
        assert doc["status"] == "complete"
        rows += [dict(r, source=folder) for r in doc["candidates"]]
    unique = {}
    for row in rows:
        if row.get("feasible", True):
            key = row["basin"], row["arm"], controls.vector_digest(row["vector"])
            unique.setdefault(key, row)
    return list(unique.values())


def pair_clock(obs, objective, vector, pairs):
    from leo.analysis.regional_position_score import circular
    left, right = pairs.T
    assert np.all(obs.receiver[left] == 0) and np.all(obs.receiver[right] == 1)
    nuisance = objective.design @ np.asarray(vector)[2:7] + objective.baseline
    residual = circular(obs.measured_hz[right]-obs.measured_hz[left] - nuisance[right]+nuisance[left])
    center = float(np.median(residual))
    residual = center + circular(residual-center)
    times = (obs.times_s[left]+obs.times_s[right])/2
    centered = times-times.mean()
    x = np.column_stack([*[(obs.channel[left] == c) for c in np.unique(obs.channel[left])], centered])
    beta = np.linalg.lstsq(x, np.full(len(residual), center), rcond=None)[0]
    for _ in range(60):
        weights = np.minimum(1., 100/np.maximum(abs(residual-x@beta), 1e-12))
        new = np.linalg.lstsq(x*np.sqrt(weights[:,None]), residual*np.sqrt(weights), rcond=None)[0]
        if np.max(abs(new-beta)) < 1e-8:
            beta = new; break
        beta = new
    return dict(count=len(pairs), median_absolute_residual_hz=float(np.median(abs(residual))),
                p90_absolute_residual_hz=float(np.quantile(abs(residual), .9)),
                robust_residual_slope_hz_s=float(beta[-1]),
                channel_offsets_hz=beta[:-1].tolist())


def run(case):
    from leo.analysis.regional_position_score import PositionObjective, coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    target = HERE/f"{case}.json"
    if target.exists(): raise FileExistsError(target)
    begun=time.monotonic()
    doc, old, obs, prior, bank, cp, prefix = loader.load(case)
    paired_path=PARENT/"identity/paired_topone.json"
    admitted=json.loads(paired_path.read_text())["cases"][case]["100ns"]["rows"]
    pairs=np.asarray([[r["row0"],r["row1"]] for r in admitted])
    for row,(i,j) in zip(admitted,pairs,strict=True):
        assert abs(row["epoch_difference_ns"]) <= 100
        assert obs.measured_hz[i] == row["cfo0_hz"] and obs.measured_hz[j] == row["cfo1_hz"]
        assert obs.rf_hz[i] == obs.rf_hz[j] == row["rf_hz"]
    pool=pool_for(case,old)
    score=replace(PositionScore(**doc["configuration"]["scores"]["V16"]),relative_sigma_s=1.)
    sources=[Path(__file__),HERE/"objective.py",HERE/"protocol.txt",paired_path,
             PARENT/"annealing"/f"{case}.json",PARENT/"timing_search"/f"{case}.json"]
    output=dict(case=case,session_id=old["session_id"],status="running",sigma_s=1.,rho=.9,
                pair_count=len(pairs),pair_rows=pairs.tolist(),evidence_sha256=doc["evidence_sha256"],
                source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                basins={},runs=[],candidates=[],primary_selections=[],selections=[],gradient_checks=[])
    contexts={}

    def save(): target.write_text(json.dumps(output,indent=2,default=controls.encode)+"\n")

    def record(vector,option,arm,basin,origin,**extra):
        obj,base,center,radius,penalty=contexts[basin][option]
        value,gradient,terms=obj.evaluate(np.asarray(vector))
        _,_,uniform=base.evaluate(np.asarray(vector))
        mass=float(terms.responsibilities.sum())
        audit=controls.audit(vector,gradient,obj.basis,arm,prior.radius_km,center,radius,
                             max(-20.,obj.bank.nodes_s[0]-obs.times_s.min()),
                             min(20.,obj.bank.nodes_s[-1]-obs.times_s.max()))
        if arm=="zero-c":assert vector[6]==0.
        return dict(option=option,arm=arm,basin=basin,origin=origin,vector=np.asarray(vector).tolist(),
                    objective=float(value),selection_score=float(value+penalty),calibration_penalty=penalty,
                    data_nll=float(terms.nll),uniform_frequency_data_nll=float(uniform.nll),
                    timing_penalty=float(value-terms.nll),signal_fraction=mass/len(obs.window_ids),
                    posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),
                    **audit,**extra)

    for basin,region in old["basins"].items():
        center=np.asarray(region["center"])
        radius=region["radius_km"] if case=="1939" else max(25.,2*region["radius_km"])
        assoc=cp.get(prefix+":"+basin+":association")["result"]
        cal=cp.get(prefix+":"+basin+":calibration")["result"]
        subset=bank.select(assoc["selected_indices"])
        baseline=np.asarray(cal["receiver_baseline_hz"])
        saved=[r for r in pool if r["basin"]==basin]
        penalty=saved[0]["calibration_penalty"]
        base=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=baseline)
        contexts[basin]={}
        seeds={arm:min((r for r in saved if r["arm"]==arm),key=lambda r:r["objective"]) for arm in controls.ARMS}
        output["basins"][basin]=dict(center=center.tolist(),radius_km=radius,numbers=subset.numbers.tolist(),
            baseline_sha256=controls.vector_digest(baseline),
            seeds={arm:dict(source=r["source"],vector_sha256=controls.vector_digest(r["vector"])) for arm,r in seeds.items()})
        for option,rho in (("control",0.),("paired",.9)):
            obj=PairedObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,pairs=pairs,rho=rho)
            contexts[basin][option]=(obj,base,center,radius,penalty)
            if option=="paired" and not output["gradient_checks"]:
                v=np.asarray(seeds["fitted-c"]["vector"])
                _,gradient,_=obj.evaluate(v)
                for index,h in ((0,.001),(1,.001),(2,.001),(4,.001),(6,.001),(7,1e-5),(12,1e-5)):
                    delta=np.zeros(obj.size);delta[index]=h
                    numerical=(obj.evaluate(v+delta)[0]-obj.evaluate(v-delta)[0])/(2*h)
                    err=abs(numerical-gradient[index])
                    output["gradient_checks"].append(dict(index=index,analytic=float(gradient[index]),numerical=float(numerical),absolute_error=float(err)))
                    assert err < .01+.0001*abs(numerical)
            for row in saved:
                r=record(row["vector"],option,row["arm"],basin,"saved:"+row["source"])
                if option=="control":assert abs(r["objective"]-row["objective"])<1e-6
                if r["feasible"]:output["candidates"].append(r)
            for arm in controls.ARMS:
                seed=previous.inside_seed(seeds[arm]["vector"],center,radius,prior.radius_km)
                fit=fit_position(obj,seed,rf_arm=arm,maximum_seconds=20.,maximum_iterations=400,
                                 local_center=center,local_radius_km=radius)
                r=record(fit.vector,option,arm,basin,"primary",elapsed_s=fit.elapsed_s,
                         stop_reason=fit.stop_reason,evaluations=fit.evaluations,
                         seed_sha256=controls.vector_digest(seed))
                output["runs"].append(r)
                if r["feasible"]:output["candidates"].append(r)
                save();print(case,basin,option,arm,round(r["selection_score"],3),r["converged"],flush=True)
    for option in ("control","paired"):
        for arm in controls.ARMS:
            selected=min((r for r in output["candidates"] if r["option"]==option and r["arm"]==arm),key=lambda r:r["selection_score"])
            output["primary_selections"].append(selected)
            basin=selected["basin"];obj,base,center,radius,_=contexts[basin][option]
            seed=previous.inside_seed(selected["vector"],center,radius,prior.radius_km)
            fit=fit_position(obj,seed,rf_arm=arm,maximum_seconds=20.,maximum_iterations=400,
                             local_center=center,local_radius_km=radius)
            r=record(fit.vector,option,arm,basin,"polish",elapsed_s=fit.elapsed_s,
                     stop_reason=fit.stop_reason,evaluations=fit.evaluations,
                     seed_sha256=controls.vector_digest(seed))
            output["runs"].append(r)
            if r["feasible"]:output["candidates"].append(r)
            selected=min((r for r in output["candidates"] if r["option"]==option and r["arm"]==arm),key=lambda r:r["selection_score"])
            output["selections"].append(selected)
            selected["pair_clock"]=pair_clock(obs,contexts[selected["basin"]][option][0],selected["vector"],pairs)
            save()
    for row in output["candidates"]:
        lat,lon=np.radians(coordinates(prior,row["vector"][:2]))
        a,b=np.radians([doc["reference_latitude_deg"],doc["reference_longitude_deg"]])
        h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row["horizontal_error_m"]=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    output.update(status="complete",elapsed_s=time.monotonic()-begun,fit_elapsed_s=sum(r["elapsed_s"] for r in output["runs"]))
    save()
    for r in output["selections"]:print("SELECTED",case,r["option"],r["arm"],r["horizontal_error_m"],r["selection_score"],r["converged"],r["pair_clock"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--case",choices=("1939","2139"),required=True)
    run(parser.parse_args().case)
