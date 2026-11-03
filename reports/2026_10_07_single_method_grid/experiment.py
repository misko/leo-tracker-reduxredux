"""V16-only grid discovery and calibration, with matched final c ablation."""
import concurrent.futures as futures
from dataclasses import asdict, replace
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026_10_07_slope_priors"
sys.path.insert(0, str(OLD))
import numpy as np
from scipy.optimize import nnls
from bounded_fit import fit_position, PositionFit
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior, PositionScore
from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.analysis.regional_position_bootstrap import bootstrap_position, BootstrapMatch, PositionBootstrap
from leo.analysis.regional_position_calibration import receiver_correction, RegionalCalibration
from leo.analysis.regional_position_association import associate_calibration
from leo.analysis.regional_position_search import distinct_basins, SpatialSearch
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
import grid

SCHEDULES = {"current100": (100.,50.,25.,12.5),
             "start50": (50.,25.,12.5,6.25), "proposed50_20_5": (50.,20.,5.)}
CONTEXT = None

def encode(x):
    if isinstance(x, np.ndarray): return x.tolist()
    if isinstance(x, np.generic): return x.item()
    raise TypeError(type(x).__name__)

def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=encode, allow_nan=False) + "\n")
    temporary.replace(path)

def bootstrap(value):
    return PositionBootstrap(tuple(value["satellite_indices"]), np.asarray(value["vector"]),
                             tuple(BootstrapMatch(**m) for m in value["matches"]))

def load():
    global CONTEXT
    d = json.loads((HERE / "inputs.json").read_text())
    assert digest(HERE / "inputs.npz") == d["inputs_sha256"]
    import leo
    for path, expected in d["source_digests"].items():
        assert digest(Path(leo.__file__).parent / path) == expected, path
    with np.load(HERE / "inputs.npz", allow_pickle=False) as a:
        obs = PositionObservations(tuple(a["obs_window_ids"].tolist()), **{n:a["obs_"+n] for n in
            ("times_s","measured_hz","rf_hz","receiver","channel","margin")})
        bank = PositionOrbitBank(**{n:a["bank_"+n] for n in ("numbers","nodes_s","position_km","velocity_km_s")})
    score = replace(PositionScore(**d["scores"]["V16"]), relative_sigma_s=1.)
    checkpoints = RegionalCheckpointStore(Path("/srv/bulk/leo"), d["session_id"], d["checkpoint_binding"])
    CONTEXT = d, obs, bank, RegionalPrior(**d["prior"]), score, checkpoints

def point_path(xy):
    return HERE / "points" / (f"{xy[0]:g}_{xy[1]:g}.json")

def score_point(xy):
    """Reuse only geometry-conditioned bootstrap seeds, never another score's ranking."""
    d, obs, bank, prior, score, cp = CONTEXT
    path = point_path(xy)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return dict(json.loads(path.read_text()), cache_hit=True)
        started = time.monotonic()
        out = dict(point=list(xy), score=1e100, status="failed", cache_hit=False)
        try:
            cached = cp.get(d["checkpoint_prefix"] + f":point:{xy[0]:g}:{xy[1]:g}")
            if cached and cached["result"]:
                seed = bootstrap(cached["result"]["bootstrap"])
                source = "verified-method-independent-bootstrap-checkpoint"
            else:
                seed = bootstrap_position(obs, bank, prior, xy, d["bootstrap_tracks"], maximum_seconds=5.)
                source = "fresh-bootstrap"
            out.update(bootstrap=asdict(seed), bootstrap_source=source,
                       bootstrap_seconds=time.monotonic()-started)
            obj = PositionObjective(obs, bank.select(list(seed.satellite_indices)), prior, score)
            fit = fit_position(obj, seed.vector, fixed_position=True, rf_arm="fitted-c",
                               maximum_seconds=5., maximum_iterations=200, slope_half_width_hz_s=60.)
            out.update(status="complete", score=fit.objective, fit=asdict(fit))
        except (ValueError, TimeoutError, ArithmeticError) as error:
            out["error"] = str(error)
        out["elapsed_s"] = time.monotonic()-started
        write(path, out)
        return out

def run_search(name, executor, deadline):
    started = time.monotonic()
    out = dict(name=name, levels_km=SCHEDULES[name], budget_points=400, method="V16",
               sigma_s=1., slope_half_width_hz_s=60., points=[], status="running")
    def batch(points):
        if time.monotonic() >= deadline:
            raise TimeoutError("bounded discovery wall-time budget")
        pending = [executor.submit(score_point, xy) for xy in points]
        rows = [f.result() for f in pending]
        out["points"].extend({k:r[k] for k in ("point","score","status","elapsed_s","cache_hit")} |
            dict(converged=r.get("fit",{}).get("converged"),
                 stop_reason=r.get("fit",{}).get("stop_reason"),
                 bootstrap_source=r.get("bootstrap_source")) for r in rows)
        out["elapsed_s"] = time.monotonic()-started
        write(HERE / f"{name}-search-progress.json", out)
        print(name, "points", len(out["points"]), "best", min(r["score"] for r in out["points"]), flush=True)
        return [r["score"] for r in rows]
    search = grid.search(batch, levels=SCHEDULES[name], budget=400)
    supported = SpatialSearch(tuple(p for p in search.evaluations if p.score < 1e100),
                              search.deferred_cells, search.stop_reason)
    basins = distinct_basins(supported, count=3, minimum_separation_km=12.5)
    out.update(status="complete", search=asdict(search), basins=[asdict(b) for b in basins],
               elapsed_s=time.monotonic()-started,
               logical_scoring_seconds=sum(p["elapsed_s"] for p in out["points"]))
    write(HERE / f"{name}-search.json", out)
    return out

def audit(obj, vector, gradient, arm, center, radius):
    """Independent bounds and scaled constrained-stationarity calculation."""
    v = np.asarray(vector); n=len(v)
    scale=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(n-7)]
    free=np.arange(n) if arm=="fitted-c" else np.delete(np.arange(n),6)
    lo,hi=np.full(n,-np.inf),np.full(n,np.inf)
    lo[:2],hi[:2]=-obj.prior.radius_km,obj.prior.radius_km
    lo[[3,5]],hi[[3,5]]=-60.,60.
    lo[6:8],hi[6:8]=[-5000.,-10.],[5000.,10.]
    normals=[];slacks=list((v-lo)[free])+list((hi-v)[free]);active=[]
    for i in free:
        for slack,sign in [(v[i]-lo[i],1),(hi[i]-v[i],-1)]:
            if slack/scale[i]<=1e-7:
                normal=np.zeros(n);normal[i]=sign/scale[i];normals.append(normal)
                if i in (3,5):active.append(int(i))
    boundary=False
    for origin,r in [(np.zeros(2),obj.prior.radius_km),(np.asarray(center),radius)]:
        delta=v[:2]-origin;slack=r*r-delta@delta;slacks.append(slack)
        boundary |= bool(np.linalg.norm(delta)>=r-1e-4)
        if slack<=1e-6:
            normal=np.zeros(n);normal[:2]=-2*delta;normals.append(normal)
    mat=np.zeros((len(obj.bank.numbers),n));mat[:,7]=1.;mat[:,8:]=obj.basis
    shifts=mat@v
    lower=max(-20.,obj.bank.nodes_s[0]-obj.observations.times_s.min())
    upper=min(20.,obj.bank.nodes_s[-1]-obj.observations.times_s.max())
    slacks.extend(shifts-lower);slacks.extend(upper-shifts)
    normals.extend(mat[shifts-lower<=1e-6]);normals.extend(-mat[upper-shifts<=1e-6])
    residual=(gradient*scale)[free]
    if normals:
        a=(np.asarray(normals)*scale)[:,free].T
        beta,_=nnls(a,residual,maxiter=100*a.shape[1]);residual-=a@beta
    stationarity=float(abs(residual).max())
    feasible=bool(min(slacks)>=-1e-6 and (arm!="zero-c" or v[6]==0))
    return dict(feasible=feasible,converged=feasible and stationarity<=.001,
                stationarity=stationarity,boundary=boundary,slope_active_bounds=active)

def refine_region(task):
    xy,radius=task
    d,obs,bank,prior,score,_=CONTEXT
    started=time.monotonic()
    out=dict(point=xy,local_radius_km=radius,method="V16",runs=[],candidates=[],status="running")
    path=HERE / "regions" / f"{xy[0]:g}_{xy[1]:g}_{radius:g}.json"
    try:
        point=json.loads(point_path(xy).read_text());seed=bootstrap(point["bootstrap"])
        subset=bank.select(list(seed.satellite_indices))
        obj=PositionObjective(obs,subset,prior,score)
        prefit=PositionFit(**{**point["fit"],"vector":np.asarray(point["fit"]["vector"])})
        if not prefit.converged:
            prefit=fit_position(obj,prefit.vector,fixed_position=True,maximum_seconds=20.,
                                maximum_iterations=600,slope_half_width_hz_s=60.)
        if not prefit.converged: raise ValueError("V16 calibration prefit did not converge")
        correction=receiver_correction(obs,obj.evaluate(prefit.vector)[2])
        corrected=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=correction.values_hz)
        postfit=fit_position(corrected,prefit.vector,fixed_position=True,maximum_seconds=20.,
                             maximum_iterations=600,slope_half_width_hz_s=60.)
        if not postfit.converged: raise ValueError("V16 calibration postfit did not converge")
        baseline=correction.values_hz+corrected.design[:,:4]@postfit.vector[2:6]
        calibrated=RegionalCalibration(seed.satellite_indices,prefit,postfit,correction,baseline)
        associated=associate_calibration(obs,bank,prior,calibrated,maximum_seconds=60.)
        final_bank=bank.select(list(associated.selected_indices))
        objective=PositionObjective(obs,final_bank,prior,score,receiver_baseline_hz=baseline)
        knots=correction.knots_hz
        penalty=float(.5*(np.sum(knots**2)/50**2+np.sum(np.diff(knots,n=2,axis=1)**2)/25**2))
        out.update(calibration=asdict(calibrated), association=asdict(associated),
                   satellite_numbers=final_bank.numbers,calibration_penalty=penalty)
        def record(v,arm,origin,**extra):
            value,gradient,terms=objective.evaluate(np.asarray(v));mass=float(terms.responsibilities.sum())
            row=dict(arm=arm,origin=origin,vector=np.asarray(v).tolist(),objective=value,
                     selection_score=value+penalty,data_nll=float(terms.nll),timing_penalty=value-terms.nll,
                     frequency_rms_hz=float(np.sqrt(np.sum(terms.responsibilities*terms.residual_hz**2)/mass)) if mass>1e-12 else None,
                     additional_slopes_hz_s=np.asarray(v)[[3,5]].tolist(),
                     calibration_slopes_hz_s=postfit.vector[[3,5]].tolist(),
                     **audit(objective,v,gradient,arm,xy,radius),**extra)
            out["candidates"].append(row)
            return row
        def fit_one(v,arm,label,parent=None):
            v=np.asarray(v).copy();v[[3,5]]=np.clip(v[[3,5]],-60,60)
            if arm=="zero-c":v[6]=0.
            # Roundoff-only spatial repair of a continuation on an active disk.
            for center,r in [(np.zeros(2),prior.radius_km),(np.asarray(xy),radius)]:
                delta=v[:2]-center;dist=np.linalg.norm(delta)
                if dist>r:
                    assert dist-r<1e-6
                    v[:2]=center+delta*((r-1e-8)/dist)
            record(v,arm,"initial:"+label,parent_origin=parent)
            fit=fit_position(objective,v,rf_arm=arm,maximum_seconds=20.,maximum_iterations=600,
                             local_center=np.asarray(xy),local_radius_km=radius,slope_half_width_hz_s=60.)
            row=record(fit.vector,arm,"fit:"+label,elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,parent_origin=parent)
            np.testing.assert_allclose(row["objective"],fit.objective,atol=1e-6,rtol=0)
            np.testing.assert_allclose(row["stationarity"],fit.stationarity,atol=1e-5,rtol=0)
            out["runs"].append(row);write(path,out)
        for arm in ("zero-c","fitted-c"):
            for label in ("association","zero-timing"):
                v=associated.initial_vector.copy()
                if label=="zero-timing":v[7:]=0.
                fit_one(v,arm,label)
            parent=min((r for r in out["candidates"] if r["arm"]==arm and r["feasible"]),key=lambda r:r["selection_score"])
            fit_one(parent["vector"],arm,"own-continuation",parent["origin"])
        out["status"]="complete"
    except (ValueError,TimeoutError,ArithmeticError) as error:
        out.update(status="failed",error=str(error))
    out["elapsed_s"]=time.monotonic()-started
    write(path,out)
    print("REGION",xy,radius,out["status"],out.get("error",""),flush=True)
    return out

def main():
    if (HERE/"protocol.json").exists():raise FileExistsError("experiment already started")
    (HERE/"points").mkdir();(HERE/"regions").mkdir()
    load();started=time.monotonic()
    sources=[Path(__file__),HERE/"grid.py",HERE/"inputs.json",OLD/"bounded_fit.py"]
    write(HERE/"protocol.json",dict(method="V16",schedules=SCHEDULES,points_per_schedule=400,
        relative_sigma_s=1.,slope_half_width_hz_s=60.,coarse_seconds=5.,coarse_iterations=200,
        calibration_likelihood="V16",coarse_arm="fitted-c",final_arms=["zero-c","fitted-c"],
        ablation_scope="final c only; shared V16 fitted-c discovery calibration and association",
        workers=8,reference_usage="after all score selection",source_hashes={str(p):digest(p) for p in sources}))
    with futures.ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context("fork")) as pool:
        with futures.ThreadPoolExecutor(max_workers=3) as threads:
            jobs={name:threads.submit(run_search,name,pool,started+1200) for name in SCHEDULES}
            searches={name:f.result() for name,f in jobs.items()}
        tasks=sorted({((b["east_km"],b["north_km"]),max(25.,b["spacing_km"]/np.sqrt(2)))
                      for s in searches.values() for b in s["basins"]})
        regions={task:r for task,r in zip(tasks,pool.map(refine_region,tasks))}
    selections=[]
    for name,search in searches.items():
        candidates=[]
        for b in search["basins"]:
            task=((b["east_km"],b["north_km"]),max(25.,b["spacing_km"]/np.sqrt(2)))
            candidates.extend(dict(r,point=task[0],local_radius_km=task[1]) for r in regions[task]["candidates"])
        for arm in ("zero-c","fitted-c"):
            pool=[r for r in candidates if r["arm"]==arm and r["feasible"]]
            converged=[r for r in pool if r["converged"]]
            key=lambda r:(r["selection_score"],r["point"],r["origin"])
            selections.append(dict(schedule=name,arm=arm,result=min(converged,key=key,default=None),
                                   best_feasible=min(pool,key=key,default=None)))
    # Geographic truth is introduced after every region and model-score selection.
    reference=json.loads((HERE/"evaluation.json").read_text())
    lat0,lon0=np.radians([reference["latitude_deg"],reference["longitude_deg"]])
    def error(point):
        lat,lon=np.radians(coordinates(CONTEXT[3],point))
        h=np.sin((lat-lat0)/2)**2+np.cos(lat)*np.cos(lat0)*np.sin((lon-lon0)/2)**2
        return float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
    for row in selections:
        for name in ("result","best_feasible"):
            if row[name] is not None:row[name]["horizontal_error_m"]=error(row[name]["vector"][:2])
    coverage=[]
    for name,search in searches.items():
        ranked=sorted(search["search"]["evaluations"],key=lambda r:(r["score"],r["east_km"],r["north_km"]))
        closest=min(enumerate(ranked,1),key=lambda ir:error([ir[1]["east_km"],ir[1]["north_km"]]))
        coverage.append(dict(schedule=name,closest_evaluated_error_m=error([closest[1]["east_km"],closest[1]["north_km"]]),
            closest_evaluated_score_rank=closest[0],closest_evaluated_point=closest[1],
            retained=[dict(b,reference_distance_m=error([b["east_km"],b["north_km"]])) for b in search["basins"]]))
    out=dict(status="complete",elapsed_s=time.monotonic()-started,selections=selections,coverage=coverage,
             searches={name:{k:v for k,v in search.items() if k not in ("points","search")} for name,search in searches.items()},
             regions=[dict(point=xy,local_radius_km=r,status=value["status"],error=value.get("error"),
                           runs=len(value["runs"]),elapsed_s=value["elapsed_s"]) for (xy,r),value in regions.items()])
    write(HERE/"results.json",out)
    print("COMPLETE",out["elapsed_s"],flush=True)

if __name__=="__main__":main()
