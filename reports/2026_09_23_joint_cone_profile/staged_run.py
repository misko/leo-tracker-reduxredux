#!/usr/bin/env python3
"""Staged 25-degree-full-FOV candidate/orientation/refit experiment."""
import hashlib, importlib.util, json, sys, time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
SEARCH=ROOT/"reports/2026_09_23_long_training_search/search.py"
LOADER=ROOT/"reports/2026_09_23_long_training_fast_score/loader.py"
CONE=ROOT/"reports/2026_09_23_train_pointing_cone/run.py"
META=Path("/tmp/leo-train-rx-metadata.json")
FULL_FOV_DEG=25.0; HALF_ANGLE_DEG=FULL_FOV_DEG/2; CAP_HZ=800.0
MAPPINGS=((0,1),(1,0))

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def capped_cost(rms): return np.minimum((np.asarray(rms)/CAP_HZ)**2,1.0)

def baseline_candidate(rms, visible):
    eligible=np.flatnonzero(visible)
    if not len(eligible): return None
    return int(eligible[np.argmin(rms[eligible])])

def all_samples_inside(directions, axis, half_angle_deg=HALF_ANGLE_DEG):
    return np.min(np.einsum("...c,c->...",directions,axis),axis=-1) >= np.cos(np.radians(half_angle_deg))

def select_shared_orientation(cone, tracks, mapping, batch=512):
    """Use frozen baseline IDs and training samples only."""
    orientations=cone.orientation_grid(15); axes=cone.axes_batched(orientations)
    best=(-1.0,None); threshold=np.cos(np.radians(HALF_ANGLE_DEG))
    for start in range(0,len(orientations),batch):
        stop=min(start+batch,len(orientations)); gain=np.zeros(stop-start)
        for t in tracks:
            if t["baseline"] is None or t["baseline_cost"] >= 1: continue
            axis=axes[start:stop,mapping[t["receiver_id"]]]
            compatible=np.min(np.einsum("oc,kc->ok",axis,t["baseline_directions"],optimize=True),axis=1)>=threshold
            gain += t["weight_s"]*(1-t["baseline_cost"])*compatible
        i=int(np.argmax(gain)); candidate=(float(gain[i]),start+i)
        if candidate[0]>best[0]: best=candidate
    return orientations,axes,best

def refit_track(track, axis):
    """Return best RF candidate among normal-visible, RF-improving, all-sample-compatible candidates."""
    if not len(track["retained_indices"]): return None
    compatible=all_samples_inside(track["retained_directions"],axis)
    viable=np.flatnonzero(compatible)
    if not len(viable): return None
    return int(viable[np.argmin(track["retained_costs"][viable])])

def prepare_track(search,cone,track,candidate_ids,receiver,up,receiver_id):
    delta=track["position"]-receiver["ecef"]; distance=np.linalg.norm(delta,axis=-1)
    prediction=-search.REFERENCE_RF_HZ/search.LIGHT_KM_S*np.sum(delta*track["velocity"],axis=-1)/distance
    train=track["training_mask"]
    if not np.any(train) or not np.any(~train): raise ValueError("track has empty training or held partition")
    if receiver_id not in (0,1): raise ValueError("invalid receiver label")
    if np.ptp(track["times_s"]) < 3: raise ValueError("ineligible short track reached staged preparation")
    residual=track["measured_hz"][None,:]-prediction
    offsets=np.mean(residual[:,train],axis=1); errors=residual-offsets[:,None]
    rms=np.sqrt(np.mean(errors[:,train]**2,axis=1)); visible=np.max(np.sum(delta*up,axis=-1)/distance,axis=1)>=0
    baseline=baseline_candidate(rms,visible); costs=capped_cost(rms)
    retained=np.flatnonzero(visible & (costs<1))
    directions=cone.enu_directions(search,*receiver["latlon"],receiver["ecef"],track["position"][:,train,:].reshape(-1,3)).reshape(len(candidate_ids),-1,3)
    return {"session_id":receiver["session_id"],"track_id":track["track_id"],"receiver_id":receiver_id,"weight_s":track["weight_s"],
      "observation_count":len(track["times_s"]),"span_s":float(np.ptp(track["times_s"])),"train_mask":train,
      "baseline":baseline,"baseline_candidate_id":None if baseline is None else str(candidate_ids[baseline]),
      "baseline_cost":1.0 if baseline is None else float(costs[baseline]),"baseline_rms_hz":None if baseline is None else float(rms[baseline]),
      "baseline_errors":None if baseline is None else errors[baseline],
      "baseline_directions":np.empty((0,3)) if baseline is None else directions[baseline],
      "retained_indices":retained,"retained_candidate_ids":candidate_ids[retained],"retained_costs":costs[retained],
      "retained_directions":directions[retained],"retained_errors":errors[retained]}

def evaluate_scenario(tracks,axes,orientation_index,mapping):
    train_numerator=held_numerator=0.; supported=0; supported_weight=0.; supported_obs=0; supported_span=0.; changed=0; held_sq=0.; held_count=0; assignments=[]
    for t in tracks:
        axis=axes[orientation_index,mapping[t["receiver_id"]]]; local=refit_track(t,axis)
        if local is None:
            cost=held_cost=1.; candidate=None
        else:
            supported+=1; supported_weight+=t["weight_s"]; supported_obs+=t["observation_count"]; supported_span+=t["span_s"]
            cost=float(t["retained_costs"][local]); candidate=str(t["retained_candidate_ids"][local]); changed += candidate != t["baseline_candidate_id"]
            held=t["retained_errors"][local,~t["train_mask"]]
            held_cost=min(float(np.mean(held**2))/CAP_HZ**2,1.) if len(held) else 1.
            held_sq+=float(np.sum(held**2)); held_count+=len(held)
        train_numerator += t["weight_s"]*cost; held_numerator += t["weight_s"]*held_cost
        assignments.append({"session_id":t["session_id"],"track_id":t["track_id"],"baseline_candidate_id":t["baseline_candidate_id"],"refit_candidate_id":candidate})
    denominator=sum(t["weight_s"] for t in tracks)
    return {"training_capped_loss":train_numerator/denominator,"held_capped_loss":held_numerator/denominator,
      "supported_tracks":supported,"unsupported_tracks":len(tracks)-supported,
      "supported_occupied_second_support":supported_weight,"supported_observation_count":supported_obs,"supported_track_span_s":supported_span,"changed_candidate_id_count":changed,
      "held_rms_hz_supported":None if not held_count else (held_sq/held_count)**.5,"assignments":assignments}

def main():
    started=time.monotonic(); search=load(SEARCH,"staged_search"); loader=load(LOADER,"staged_loader"); cone=load(CONE,"staged_cone")
    cells=json.loads((ROOT/"reports/2026_09_23_train_fixed_cone/locations.json").read_text())["cells"]
    manifests={"first_train":ROOT/"reports/2026_09_23_long_training_cache_full8h/manifest.json","second_train":ROOT/"reports/2026_09_23_long_training_cache_second8h/manifest.json"}
    roots={"first_train":Path("/tmp/leo-long-training-cache-full8h"),"second_train":Path("/tmp/leo-long-training-cache-second8h")}
    sessions=[]; session_bindings=[]; candidate_policy=None; expected_ids=[]
    for group in roots:
        ids=json.loads(manifests[group].read_text())["source_group"]["session_ids"][:6]
        expected_ids += ids
        for sid in ids:
            session=loader.load_session(search,roots[group]/sid,sid); sessions.append((group,session))
            receipt=json.loads(session["receipt"].read_text()); policy=receipt["candidate_policy"]
            if candidate_policy is None: candidate_policy=policy
            if policy != candidate_policy: raise ValueError("candidate policy differs across sessions")
            session_bindings.append({"group":group,"session_id":sid,"receipt":digest(session["receipt"]),"cache":digest(session["cache"]),"candidate_count":len(session["candidate_ids"]),"candidate_policy":policy})
    md=json.loads(META.read_text())["sessions"]; labels={(s["session_id"],t["track_id"]):int(t["receiver_id"]) for s in md for t in s["tracks"]}
    if [s[1]["session_id"] for s in sessions] != expected_ids or len(set(expected_ids)) != 12: raise ValueError("unexpected TRAIN session cohort")
    results=[]
    for cell in cells:
        receiver_ecef,up=search.receiver_ecef(cell["latitude_deg"],cell["longitude_deg"]); tracks=[]
        for group,session in sessions:
            receiver={"latlon":(cell["latitude_deg"],cell["longitude_deg"]),"ecef":receiver_ecef,"session_id":session["session_id"]}
            tracks += [prepare_track(search,cone,t,session["candidate_ids"],receiver,up,labels[(session["session_id"],t["track_id"])]) for t in session["prepared"]]
        baseline_loss=sum(t["weight_s"]*t["baseline_cost"] for t in tracks)/sum(t["weight_s"] for t in tracks)
        baseline_held_num=baseline_held_sq=0.; baseline_held_n=0; baseline_supported=0
        for t in tracks:
            if t["baseline"] is None: baseline_held_num += t["weight_s"]
            else:
                baseline_supported += 1; held=t["baseline_errors"][~t["train_mask"]]
                baseline_held_num += t["weight_s"]*min(float(np.mean(held**2))/CAP_HZ**2,1.)
                baseline_held_sq += float(np.sum(held**2)); baseline_held_n += len(held)
        scenarios=[]
        for mapping in MAPPINGS:
            orientations,axes,(stage_gain,oi)=select_shared_orientation(cone,tracks,mapping)
            scenario=evaluate_scenario(tracks,axes,oi,mapping)
            if scenario["training_capped_loss"]+1e-12 < baseline_loss: raise AssertionError("restricted loss beat unconstrained baseline")
            scenario.update(mapping=list(mapping),orientation=[int(x) for x in orientations[oi]],stage_baseline_gain=stage_gain)
            scenarios.append(scenario)
        total_weight=sum(t["weight_s"] for t in tracks)
        results.append({"cell_id":cell["cell_id"],"aliases":cell["aliases"],"track_count":len(tracks),"occupied_second_support":total_weight,"observation_count":sum(t["observation_count"] for t in tracks),"track_span_s":sum(t["span_s"] for t in tracks),"baseline_training_capped_loss":baseline_loss,"baseline_held_capped_loss":baseline_held_num/total_weight,"baseline_held_rms_hz_supported":None if not baseline_held_n else (baseline_held_sq/baseline_held_n)**.5,"baseline_supported_tracks":baseline_supported,"retained_candidate_count":sum(len(t["retained_indices"]) for t in tracks),"scenarios":scenarios})
        print("completed",cell["cell_id"],flush=True)
    output={"schema":"joint-cone-staged/v1","full_fov_deg":FULL_FOV_DEG,"half_angle_deg":HALF_ANGLE_DEG,"axis_separation_deg":20,"mapping_selection":"both mappings reported; neither selected","stage":"baseline_then_orientation_on_frozen_winners_then_single_refit","truth_used":False,"held_used_for_fit":False,"candidate_policy":candidate_policy,"session_bindings":session_bindings,"results":results,"elapsed_s":time.monotonic()-started,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"amendment":digest(HERE/"PREEXECUTION_AMENDMENT_STAGED.json"),"source":digest(__file__),"metadata":digest(META),"locations":digest(ROOT/"reports/2026_09_23_train_fixed_cone/locations.json"),"search":digest(SEARCH),"loader":digest(LOADER),"cone":digest(CONE),"manifests":{k:digest(v) for k,v in manifests.items()}}}
    path=HERE/"staged_results.json"; path.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n"); (HERE/"staged_results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")

if __name__=="__main__": main()
