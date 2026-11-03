"""Bounded receiver-clock/association intervention with unchanged sigma1."""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import numpy as np
from objective import BackgroundObjective
from leo.analysis.regional_position_score import circular

HERE=Path(__file__).resolve().parent;PARENT=HERE.parent
spec=importlib.util.spec_from_file_location("anneal_helpers_background",PARENT/"annealing/experiment.py")
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
loader,controls=previous.loader,previous.controls


def clock_seed(obs,base,vector,pairs):
    """Change only differential RX affine terms; paired differences use no orbit."""
    v=np.asarray(vector,float).copy();i,j=pairs.T
    assert np.all(obs.receiver[i]==0) and np.all(obs.receiver[j]==1)
    mean_a=(v[2]+v[4])/2;mean_b=(v[3]+v[5])/2
    x=np.column_stack([np.ones(len(i)),(obs.times_s[i]+obs.times_s[j])/2-obs.time_center_s])
    y=circular(obs.measured_hz[j]-obs.measured_hz[i]-base.baseline[j]+base.baseline[i]-mean_b*(obs.times_s[j]-obs.times_s[i]))
    center=float(np.median(y));y=center+circular(y-center)
    beta=np.array([center,0.])
    for _ in range(100):
        weight=np.minimum(1.,100/np.maximum(abs(y-x@beta),1e-12))
        new=np.linalg.lstsq(x*np.sqrt(weight[:,None]),y*np.sqrt(weight),rcond=None)[0]
        if np.max(abs(new-beta))<1e-8:beta=new;break
        beta=new
    v[2],v[4]=mean_a-beta[0]/2,mean_a+beta[0]/2
    v[3],v[5]=mean_b-beta[1]/2,mean_b+beta[1]/2
    np.testing.assert_array_equal(v[:2],np.asarray(vector)[:2]);np.testing.assert_array_equal(v[6:],np.asarray(vector)[6:])
    return v,dict(differential_offset_hz=float(beta[0]),differential_slope_hz_s=float(beta[1]),
                  initializer_residual_median_hz=float(np.median(abs(y-x@beta))))


def clock_metrics(obs,base,vector,pairs):
    i,j=pairs.T;nuisance=base.design@np.asarray(vector)[2:7]+base.baseline
    residual=circular(obs.measured_hz[j]-obs.measured_hz[i]-nuisance[j]+nuisance[i])
    t=(obs.times_s[i]+obs.times_s[j])/2
    x=np.column_stack([*[(obs.channel[i]==c) for c in np.unique(obs.channel[i])],t-t.mean()])
    center=float(np.median(residual));residual=center+circular(residual-center)
    beta=np.linalg.lstsq(x,np.full(len(residual),center),rcond=None)[0]
    for _ in range(100):
        w=np.minimum(1.,100/np.maximum(abs(residual-x@beta),1e-12))
        new=np.linalg.lstsq(x*np.sqrt(w[:,None]),residual*np.sqrt(w),rcond=None)[0]
        if np.max(abs(new-beta))<1e-8:beta=new;break
        beta=new
    return dict(median_absolute_residual_hz=float(np.median(abs(residual))),
                p90_absolute_residual_hz=float(np.quantile(abs(residual),.9)),
                robust_residual_slope_hz_s=float(beta[-1]))


def run(case):
    from leo.analysis.regional_position_score import PositionObjective,coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    target=HERE/f"{case}.json"
    if target.exists():raise FileExistsError(target)
    begun=time.monotonic();doc,old,obs,prior,bank,cp,prefix=loader.load(case)
    prior_path=PARENT/"paired_identity"/f"{case}.json"
    prior_doc=json.loads(prior_path.read_text());assert prior_doc["status"]=="complete"
    paired_path=PARENT/"identity/paired_topone.json"
    assert hashlib.sha256(paired_path.read_bytes()).hexdigest()==prior_doc["source_hashes"][str(paired_path)]
    pairs=np.asarray(prior_doc["pair_rows"])
    basins=sorted({r["basin"] for r in prior_doc["selections"] if r["option"]=="paired"})
    saved=[r for r in prior_doc["candidates"] if r["option"]=="paired" and r["basin"] in basins and r["feasible"]]
    score=replace(PositionScore(**doc["configuration"]["scores"]["V16"]),relative_sigma_s=1.)
    output=dict(case=case,status="running",session_id=old["session_id"],sigma_s=1.,rho=.9,eta=.9,
                selected_basins=basins,pair_count=len(pairs),evidence_sha256=doc["evidence_sha256"],
                source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/"objective.py",HERE/"protocol.txt",prior_path,paired_path]},
                basins={},runs=[],candidates=[],primary_selections=[],selections=[])
    contexts={}
    def save():target.write_text(json.dumps(output,indent=2,default=controls.encode)+"\n")
    def record(vector,basin,option,arm,origin,**extra):
        obj,base,center,radius,penalty=contexts[basin][option]
        value,grad,terms=obj.evaluate(np.asarray(vector));diagnostic=dict(obj.last_background)
        uniform_value,_,uniform=base.evaluate(np.asarray(vector));mass=float(terms.responsibilities.sum())
        audit=controls.audit(vector,grad,obj.basis,arm,prior.radius_km,center,radius,
                             max(-20.,obj.bank.nodes_s[0]-obs.times_s.min()),min(20.,obj.bank.nodes_s[-1]-obs.times_s.max()))
        if arm=="zero-c":assert vector[6]==0.
        return dict(basin=basin,option=option,arm=arm,origin=origin,vector=np.asarray(vector).tolist(),
                    objective=float(value),selection_score=float(value+penalty),calibration_penalty=penalty,
                    data_nll=float(terms.nll),uniform_frequency_data_nll=float(uniform.nll),
                    timing_penalty=float(value-terms.nll),signal_fraction=mass/len(obs.window_ids),
                    posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)),
                    mean_common_unidentified_pair_probability=float(np.mean(diagnostic["common_background_probability"])),
                    pair_clock=clock_metrics(obs,base,vector,pairs),**audit,**extra)
    for basin in basins:
        region=old["basins"][basin];center=np.asarray(region["center"])
        radius=region["radius_km"] if case=="1939" else max(25.,2*region["radius_km"])
        assoc=cp.get(prefix+":"+basin+":association")["result"];cal=cp.get(prefix+":"+basin+":calibration")["result"]
        subset=bank.select(assoc["selected_indices"]);baseline=np.asarray(cal["receiver_baseline_hz"])
        base=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=baseline)
        rows=[r for r in saved if r["basin"]==basin];penalty=rows[0]["calibration_penalty"]
        seeds={arm:min((r for r in rows if r["arm"]==arm),key=lambda r:r["objective"]) for arm in controls.ARMS}
        output["basins"][basin]=dict(center=center.tolist(),radius_km=radius,numbers=subset.numbers.tolist(),
            seeds={arm:dict(vector_sha256=controls.vector_digest(r["vector"])) for arm,r in seeds.items()})
        contexts[basin]={}
        for option,eta in (("control",0.),("background",.9)):
            obj=BackgroundObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,pairs=pairs,rho=.9,eta=eta)
            contexts[basin][option]=(obj,base,center,radius,penalty)
            for row in rows:
                r=record(row["vector"],basin,option,row["arm"],"prior-paired")
                if option=="control":assert abs(r["objective"]-row["objective"])<1e-6
                if r["feasible"]:output["candidates"].append(r)
            for arm in controls.ARMS:
                incumbent=previous.inside_seed(seeds[arm]["vector"],center,radius,prior.radius_km)
                initialized,meta=clock_seed(obs,base,incumbent,pairs)
                for start,seed in (("own-state",incumbent),("paired-clock",initialized)):
                    fit=fit_position(obj,seed,rf_arm=arm,maximum_seconds=20.,maximum_iterations=400,
                                     local_center=center,local_radius_km=radius)
                    r=record(fit.vector,basin,option,arm,start,elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,
                             evaluations=fit.evaluations,seed_sha256=controls.vector_digest(seed),clock_seed=meta)
                    output["runs"].append(r)
                    if r["feasible"]:output["candidates"].append(r)
                    save();print(case,option,arm,start,round(r["selection_score"],3),r["converged"],r["pair_clock"],flush=True)
    for option in ("control","background"):
        for arm in controls.ARMS:
            selected=min((r for r in output["candidates"] if r["option"]==option and r["arm"]==arm),key=lambda r:r["selection_score"])
            output["primary_selections"].append(selected)
            basin=selected["basin"];obj,base,center,radius,penalty=contexts[basin][option]
            seed=previous.inside_seed(selected["vector"],center,radius,prior.radius_km)
            fit=fit_position(obj,seed,rf_arm=arm,maximum_seconds=20.,maximum_iterations=400,local_center=center,local_radius_km=radius)
            r=record(fit.vector,basin,option,arm,"polish",elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,evaluations=fit.evaluations,seed_sha256=controls.vector_digest(seed))
            output["runs"].append(r)
            if r["feasible"]:output["candidates"].append(r)
            selected=min((r for r in output["candidates"] if r["option"]==option and r["arm"]==arm),key=lambda r:r["selection_score"])
            output["selections"].append(selected);save()
    for row in output["candidates"]:
        lat,lon=np.radians(coordinates(prior,row["vector"][:2]));a,b=np.radians([doc["reference_latitude_deg"],doc["reference_longitude_deg"]])
        h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
        row["horizontal_error_m"]=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    output.update(status="complete",elapsed_s=time.monotonic()-begun,fit_elapsed_s=sum(r["elapsed_s"] for r in output["runs"]));save()
    for r in output["selections"]:print("SELECTED",case,r["option"],r["arm"],r["horizontal_error_m"],r["selection_score"],r["converged"],r["pair_clock"],r["mean_common_unidentified_pair_probability"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--case",choices=("1939","2139"),required=True);run(parser.parse_args().case)
