"""Evaluate frozen method families at each disjoint replication group's own points."""
# ruff: noqa: E402
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, sys, time
from dataclasses import replace
from pathlib import Path
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"
import matplotlib.pyplot as plt
import numpy as np

REFERENCE=(37.84903264307456,-122.4856541910174)

def _module(name):
    path=Path(__file__).with_name(name)
    spec=importlib.util.spec_from_file_location(path.stem,path); mod=importlib.util.module_from_spec(spec)
    assert spec.loader is not None; sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod,path
def _digest(path): return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def _points(group, joint):
    result=json.loads((group/"results.json").read_text())
    scans=json.loads((group/"scans.json").read_text())
    full=next(x for x in result["results"] if x["scan_count"]==len(scans))
    points=[]
    for i,row in enumerate(full["basins"][:3],1):
        points.append({"location_id":f"joint_basin_{i}","latitude_deg":row["latitude_deg"],"longitude_deg":row["longitude_deg"],"source":"frozen group joint basin"})
    for prior in ("sacramento","reno"):
        coordinates=np.asarray([[s["priors"][prior]["selected"]["latitude_deg"],s["priors"][prior]["selected"]["longitude_deg"]] for s in scans])
        point=coordinates.mean(axis=0)
        points.append({"location_id":f"{prior}_coordinate_mean","latitude_deg":float(point[0]),"longitude_deg":float(point[1]),"source":"frozen group coordinate mean"})
    if not points or len({x["location_id"] for x in points})!=len(points):
        raise ValueError("group requires distinct available basin/mean points")
    return points

def _weight(track): return int(len(np.unique(np.floor(track.times_s).astype(int))))

def _integer_prediction(prediction):
    """Recover the frozen legacy integer-tau support from the quarter-second bank."""
    taus=np.asarray(prediction.taus_s); indices=np.flatnonzero(np.isclose(taus,np.round(taus)))
    if len(indices)!=11 or not np.array_equal(taus[indices],np.arange(-5.,6.)):
        raise ValueError("quarter-second bank does not contain the exact integer tau support")
    visible=np.asarray(prediction.visible)
    if visible.ndim==2: visible=visible[:,indices]
    return replace(prediction,taus_s=taus[indices],predictions_hz=np.asarray(prediction.predictions_hz)[:,indices],visible=visible)

def _soft_value(soft, prediction):
    hard,mode,null,entropy,log_evidence,train_sse,_=soft._track_score(prediction)
    return -log_evidence/int(prediction.training_mask.sum()), {"null_posterior":null,"entropy_nats":entropy,"hard":hard,"mode":mode}

def _evaluate(group, joint, timing, soft):
    cache=group/"cache"; manifest=json.loads((cache/"cache_manifest.json").read_text()); points=_points(group,joint)
    configs=[timing.AblationConfig(step,obj,identity) for identity in ("evaluation","training") for step in (1.,.5,.25) for obj in ("duration-capped-rmse-800hz",)] + [timing.AblationConfig(step,"uncertainty-floor-pseudo-huber","training") for step in (1.,.5,.25)]
    rows=[]
    for point in points:
        predictions=[]
        for scan in manifest["scans"]:
            evidence,arrays=joint.load_scan_cache(cache,scan["session_id"])
            for track in evidence["tracks"]:
                predictions.append((scan["session_id"],joint.prediction_for_track(evidence,arrays,track,point["latitude_deg"],point["longitude_deg"],taus_s=np.arange(-5.,5.0001,.25))))
        integer_predictions=[_integer_prediction(x[1]) for x in predictions]
        native=joint.score_point(0,0,integer_predictions)
        rows.append({**point,"method":"native_integer_capped","objective_name":"capped_weighted_rms_hz","objective_value":native.residual_rmse_hz,"native_objective_hz2":native.weighted_mse_hz2,"track_count":len(predictions),"observation_count":sum(len(x[1].observation_ids) for x in predictions)})
        weighted=[]; diagnostics=[]
        for prediction in integer_predictions:
            value,detail=_soft_value(soft,prediction); weighted.append((_weight(prediction),value)); diagnostics.append(detail)
        total=sum(w for w,_ in weighted)
        rows.append({**point,"method":"soft_marginal_train","objective_name":"duration_weighted_mean_negative_log_evidence","objective_value":sum(w*v for w,v in weighted)/total,"track_count":len(predictions),"observation_count":sum(len(x[1].observation_ids) for x in predictions),"median_null_posterior":float(np.median([x["null_posterior"] for x in diagnostics])),"median_entropy_nats":float(np.median([x["entropy_nats"] for x in diagnostics]))})
        for config in configs:
            track_rows=[]
            for sid,prediction in predictions:
                uncertainty=timing.training_roughness_uncertainty_hz(prediction.times_s,prediction.measured_hz,prediction.training_mask)
                winner=timing.score_track(prediction.measured_hz,prediction.predictions_hz,prediction.training_mask,np.full(len(prediction.measured_hz),uncertainty),prediction.candidate_ids,prediction.taus_s,config,visible=prediction.visible)
                track_rows.append({"session_id":sid,"track_id":prediction.track_id,"weight_s":_weight(prediction),"winner":winner})
            summary=timing.summarize_tracks(track_rows,config)
            if config == timing.AblationConfig(1.,"duration-capped-rmse-800hz","evaluation"):
                if not np.isclose(summary["objective_value"],native.residual_rmse_hz,rtol=0,atol=1e-10):
                    raise AssertionError("native integer score differs from timing 1 s evaluation-ID parity")
            rows.append({**point,"method":f"timing-{config.timing_step_s:g}s-{config.objective}-identity-{config.identity_selection}","objective_name":config.objective,"objective_value":summary["objective_value"],"track_count":len(track_rows),"observation_count":sum(len(x[1].observation_ids) for x in predictions),**summary})
    # The reference is introduced only after every per-method location choice is fixed.
    selected=[]
    for method in sorted({row["method"] for row in rows}):
        candidates=[row for row in rows if row["method"]==method]; winner=min(candidates,key=lambda x:x["objective_value"])
        selected.append({"method":method,"location_id":winner["location_id"],"latitude_deg":winner["latitude_deg"],"longitude_deg":winner["longitude_deg"],"objective":winner["objective_value"],"objective_value":winner["objective_value"],"track_count":winner["track_count"],"observation_count":winner["observation_count"],"error_km":joint.haversine_km((winner["latitude_deg"],winner["longitude_deg"]),REFERENCE)})
    return rows,selected,{"tracks":sum(x["track_count"] for x in rows[:1]),"observations":sum(x["observation_count"] for x in rows[:1]),"cache_digest":_digest(cache/"cache_manifest.json")}

def run(args):
    if args.output.exists(): raise ValueError("fresh output required")
    joint,joint_path=_module("sixteen_joint_compare.py"); timing,timing_path=_module("sixteen_timing_robust.py"); soft,soft_path=_module("sixteen_soft_orbit.py")
    groups=sorted(x for x in args.replication_root.iterdir() if (x/"cache/cache_manifest.json").is_file() and (x/"results.json").is_file() and (x/"scans.json").is_file())
    if not groups: raise ValueError("no stable replication group cache/results found")
    started=time.monotonic(); output=[]
    for group in groups:
        rows,selected,accounting=_evaluate(group,joint,timing,soft)
        output.append({"group_id":group.name,"scan_count":len(json.loads((group/"scans.json").read_text())),"accounting":accounting,"points":[{k:x[k] for k in ("location_id","latitude_deg","longitude_deg","source")} for x in rows if x["method"]=="native_integer_capped"],"five_point_scores":rows,"results":selected})
    # Remainder groups remain separate because their scan counts differ.
    complete=[x for x in output if x["scan_count"]==16]
    def distribution(groups):
        values={}
        for group in groups:
            for row in group["results"]: values.setdefault(row["method"],[]).append(row["error_km"])
        return {method:{"values_km":series,"count":len(series),"median_km":float(np.median(series)),"maximum_km":float(np.max(series)),"within_0_3_km":int(np.sum(np.asarray(series)<=.3))} for method,series in values.items()}
    document={"schema":"day-position-method-family-ablation/v1","position_truth_used_for_selection":False,"candidate_scope":"per-scan conditional production winner union; not full catalogue","timing_scope":"all variants use the same group-specific points and cached 0.25 s states","soft_scope":"fixed null/signal settings and training-only marginalized evidence","complete_16_groups":len(complete),"remainder_groups":[x["group_id"] for x in output if x not in complete],"method_error_distribution_complete_16":distribution(complete),"method_error_distribution_remainder":distribution([x for x in output if x not in complete]),"groups":output,"runtime_s":time.monotonic()-started,"source_digests":{str(p.name):_digest(p) for p in (joint_path,timing_path,soft_path)}}
    args.output.mkdir(parents=True); (args.output/"results.json").write_text(json.dumps(document,indent=2,allow_nan=False)+"\n")
    fig,ax=plt.subplots(figsize=(10,4),layout="constrained")
    methods=sorted({x["method"] for group in output for x in group["results"]})
    for method in methods:
        rows=[next(x for x in group["results"] if x["method"]==method) for group in complete]
        ax.plot([group["group_id"] for group in complete],[x["error_km"] for x in rows],"o-",label=method)
    ax.axhline(.3,color="black",linestyle="--",label="300 m"); ax.set(ylabel="Post-selection reference error (km)",xlabel="Disjoint 16-scan group"); ax.grid(alpha=.25); ax.legend(fontsize=6,ncol=2); fig.savefig(args.output/"method_errors.png",dpi=160); plt.close(fig)

def run_hard_training_supplemental(args):
    """Add the old hard training-SSE selector without re-evaluating timing variants."""
    joint,joint_path=_module("sixteen_joint_compare.py"); soft,soft_path=_module("sixteen_soft_orbit.py")
    groups=sorted(x for x in args.replication_root.iterdir() if (x/"cache/cache_manifest.json").is_file() and (x/"results.json").is_file() and (x/"scans.json").is_file())
    results=[]
    for group in groups:
        values=[]
        for point in _points(group,joint):
            numerator=0.; denominator=0; tracks=0; observations=0
            manifest=json.loads((group/"cache/cache_manifest.json").read_text())
            for scan in manifest["scans"]:
                evidence,arrays=joint.load_scan_cache(group/"cache",scan["session_id"])
                for track in evidence["tracks"]:
                    prediction=_integer_prediction(joint.prediction_for_track(evidence,arrays,track,point["latitude_deg"],point["longitude_deg"],taus_s=np.arange(-5.,5.0001,.25)))
                    _,_,_,_,_,sse,_=soft._track_score(prediction); weight=_weight(prediction)
                    numerator += weight*sse/int(prediction.training_mask.sum()); denominator += weight; tracks += 1; observations += len(prediction.observation_ids)
            values.append({**point,"objective":numerator/denominator,"track_count":tracks,"observation_count":observations})
        winner=min(values,key=lambda x:x["objective"])
        results.append({"group_id":group.name,"scan_count":len(json.loads((group/"scans.json").read_text())),"five_point_scores":values,"result":{**winner,"method":"hard_training_mean_sse","error_km":joint.haversine_km((winner["latitude_deg"],winner["longitude_deg"]),REFERENCE)}})
    complete=[x for x in results if x["scan_count"]==16]; remainder=[x for x in results if x["scan_count"]!=16]
    def summary(rows):
        values=[x["result"]["error_km"] for x in rows]
        return {"values_km":values,"count":len(values),"median_km":float(np.median(values)),"maximum_km":float(np.max(values)),"within_0_3_km":int(np.sum(np.asarray(values)<=.3))}
    document={"schema":"day-position-hard-training-supplemental/v1","position_truth_used_for_selection":False,"method":"hard_training_mean_sse","objective":"per-track training mean SSE then one-second duration weighting","tau_support_s":[-5,5],"tau_step_s":1.,"groups":results,"complete_16_distribution":summary(complete),"remainder_distribution":summary(remainder),"source_digests":{joint_path.name:_digest(joint_path),soft_path.name:_digest(soft_path)}}
    payload=json.dumps(document,indent=2,allow_nan=False)+"\n"; temporary=args.output/"hard_training_supplemental.tmp"; temporary.write_text(payload); os.replace(temporary,args.output/"hard_training_supplemental.json")

def _self_test():
    class J:
        haversine_km=staticmethod(lambda a,b:float(np.hypot(a[0]-b[0],a[1]-b[1])))
    rows=[{"method":"a","objective_value":2,"latitude_deg":1.,"longitude_deg":1.,"location_id":"x"},{"method":"a","objective_value":1,"latitude_deg":2.,"longitude_deg":2.,"location_id":"y"}]
    winner=min(rows,key=lambda x:x["objective_value"]); assert winner["location_id"]=="y" and J.haversine_km((winner["latitude_deg"],winner["longitude_deg"]),REFERENCE)>0

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--replication-root",type=Path); parser.add_argument("--output",type=Path); parser.add_argument("--self-test",action="store_true"); parser.add_argument("--hard-training-supplemental",action="store_true"); args=parser.parse_args()
    if args.self_test: _self_test()
    elif args.hard_training_supplemental and args.replication_root and args.output: run_hard_training_supplemental(args)
    elif args.replication_root and args.output: run(args)
    else: parser.error("--replication-root and --output required unless --self-test")
