#!/usr/bin/env python3
import hashlib, importlib.util, json, sys, time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
BASE=ROOT/"reports/2026_09_23_joint_cone_profile/staged_run.py"
BASE_RESULTS=ROOT/"reports/2026_09_23_joint_cone_profile/staged_results.json"
WIDTHS=(10.0,25.0,30.0); MAPPINGS=((0,1),(1,0))

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def all_samples_inside(directions,axis,full_fov_deg):
 return np.min(np.einsum("...c,c->...",directions,axis),axis=-1)>=np.cos(np.radians(full_fov_deg/2))

def select_shared_orientation(base,cone,tracks,mapping,full_fov_deg,batch=512):
 orientations=cone.orientation_grid(15); axes=cone.axes_batched(orientations); threshold=np.cos(np.radians(full_fov_deg/2)); best=(-1.,None)
 for start in range(0,len(orientations),batch):
  stop=min(start+batch,len(orientations)); gain=np.zeros(stop-start)
  for t in tracks:
   if t["baseline"] is None or t["baseline_cost"]>=1: continue
   axis=axes[start:stop,mapping[t["receiver_id"]]]
   compatible=np.min(np.einsum("oc,kc->ok",axis,t["baseline_directions"],optimize=True),axis=1)>=threshold
   gain+=t["weight_s"]*(1-t["baseline_cost"])*compatible
  i=int(np.argmax(gain)); candidate=(float(gain[i]),start+i)
  if candidate[0]>best[0]: best=candidate
 return orientations,axes,best

def refit_track(track,axis,full_fov_deg):
 if not len(track["retained_indices"]): return None
 viable=np.flatnonzero(all_samples_inside(track["retained_directions"],axis,full_fov_deg))
 return None if not len(viable) else int(viable[np.argmin(track["retained_costs"][viable])])

def sampled_angular_span(directions):
 dots=np.einsum("ic,jc->ij",directions,directions)
 return float(np.degrees(np.arccos(np.clip(np.min(dots),-1,1))))

def evaluate(base,tracks,axes,oi,mapping,width):
 train_num=held_num=held_sq=0.; held_n=supported=changed=0; weight=obs=0.; span=0.; maximum_selected_angle=0.; assignments=[]
 for t in tracks:
  local=refit_track(t,axes[oi,mapping[t["receiver_id"]]],width)
  if local is None: cost=held_cost=1.; candidate=None; selected_angle=None
  else:
   supported+=1; weight+=t["weight_s"]; obs+=t["observation_count"]; span+=t["span_s"]
   cost=float(t["retained_costs"][local]); candidate=str(t["retained_candidate_ids"][local]); changed+=candidate!=t["baseline_candidate_id"]
   minimum_dot=float(np.min(np.einsum("kc,c->k",t["retained_directions"][local],axes[oi,mapping[t["receiver_id"]]])))
   selected_angle=float(np.degrees(np.arccos(np.clip(minimum_dot,-1,1)))); maximum_selected_angle=max(maximum_selected_angle,selected_angle)
   if selected_angle>width/2+1e-8: raise AssertionError("refit candidate outside cone at a training sample")
   held=t["retained_errors"][local,~t["train_mask"]]; held_cost=min(float(np.mean(held**2))/base.CAP_HZ**2,1.)
   held_sq+=float(np.sum(held**2)); held_n+=len(held)
  train_num+=t["weight_s"]*cost; held_num+=t["weight_s"]*held_cost
  assignments.append({"session_id":t["session_id"],"track_id":t["track_id"],"receiver_id":t["receiver_id"],"baseline_candidate_id":t["baseline_candidate_id"],"refit_candidate_id":candidate,"maximum_training_angle_deg":selected_angle})
 denominator=sum(t["weight_s"] for t in tracks)
 return {"training_capped_loss":train_num/denominator,"held_capped_loss":held_num/denominator,"supported_tracks":supported,"unsupported_tracks":len(tracks)-supported,"supported_track_fraction":supported/len(tracks),"supported_occupied_second_support":weight,"supported_occupied_second_fraction":weight/denominator,"supported_observation_count":int(obs),"supported_track_span_s":span,"changed_candidate_id_count":changed,"maximum_selected_training_angle_deg":maximum_selected_angle,"held_rms_hz_supported":None if not held_n else (held_sq/held_n)**.5,"assignments":assignments}

def main():
 begun=time.monotonic(); base=load(BASE,"width_base"); search=load(base.SEARCH,"width_search"); loader=load(base.LOADER,"width_loader"); cone=load(base.CONE,"width_cone")
 cells=json.loads((ROOT/"reports/2026_09_23_train_fixed_cone/locations.json").read_text())["cells"]
 manifests={"first_train":ROOT/"reports/2026_09_23_long_training_cache_full8h/manifest.json","second_train":ROOT/"reports/2026_09_23_long_training_cache_second8h/manifest.json"}; roots={"first_train":Path("/tmp/leo-long-training-cache-full8h"),"second_train":Path("/tmp/leo-long-training-cache-second8h")}
 sessions=[]; bindings=[]; policies=set(); expected=[]
 for group in roots:
  ids=json.loads(manifests[group].read_text())["source_group"]["session_ids"][:6]; expected+=ids
  for sid in ids:
   session=loader.load_session(search,roots[group]/sid,sid); sessions.append(session); receipt=json.loads(session["receipt"].read_text()); policies.add(receipt["candidate_policy"]); bindings.append({"group":group,"session_id":sid,"receipt":digest(session["receipt"]),"cache":digest(session["cache"]),"candidate_count":len(session["candidate_ids"]),"candidate_policy":receipt["candidate_policy"]})
 if [s["session_id"] for s in sessions]!=expected or len(set(expected))!=12 or len(policies)!=1: raise ValueError("session cohort or candidate policy mismatch")
 metadata=json.loads(base.META.read_text())["sessions"]; labels={(s["session_id"],t["track_id"]):int(t["receiver_id"]) for s in metadata for t in s["tracks"]}; published=json.loads(BASE_RESULTS.read_text()); results=[]
 for ci,cell in enumerate(cells):
  ecef,up=search.receiver_ecef(cell["latitude_deg"],cell["longitude_deg"]); tracks=[]
  for session in sessions:
   receiver={"latlon":(cell["latitude_deg"],cell["longitude_deg"]),"ecef":ecef,"session_id":session["session_id"]}
   tracks += [base.prepare_track(search,cone,t,session["candidate_ids"],receiver,up,labels[(session["session_id"],t["track_id"])]) for t in session["prepared"]]
  denominator=sum(t["weight_s"] for t in tracks); baseline=sum(t["weight_s"]*t["baseline_cost"] for t in tracks)/denominator; baseline_held_num=baseline_held_sq=0.; baseline_held_n=baseline_supported=0
  for t in tracks:
   if t["baseline"] is None: baseline_held_num+=t["weight_s"]
   else:
    baseline_supported+=1; held=t["baseline_errors"][~t["train_mask"]]; baseline_held_num+=t["weight_s"]*min(float(np.mean(held**2))/base.CAP_HZ**2,1.); baseline_held_sq+=float(np.sum(held**2)); baseline_held_n+=len(held)
  scenarios=[]
  for width in WIDTHS:
   baseline_span_exclusions=sum(t["baseline"] is not None and sampled_angular_span(t["baseline_directions"])>width+1e-10 for t in tracks)
   candidate_span_exclusions=sum(sampled_angular_span(d)>width+1e-10 for t in tracks for d in t["retained_directions"])
   for mapping in MAPPINGS:
    orientations,axes,(gain,oi)=select_shared_orientation(base,cone,tracks,mapping,width); row=evaluate(base,tracks,axes,oi,mapping,width)
    if row["training_capped_loss"]+1e-12<baseline: raise AssertionError("restricted loss beat baseline")
    row.update(full_fov_deg=width,half_angle_deg=width/2,mapping=list(mapping),orientation=[int(x) for x in orientations[oi]],stage_baseline_gain=gain,baseline_winner_track_span_exclusions=baseline_span_exclusions,retained_candidate_track_span_exclusions=candidate_span_exclusions); scenarios.append(row)
  parity=[x for x in scenarios if x["full_fov_deg"]==25 and x["mapping"]==[0,1]][0]; old=published["results"][ci]["scenarios"][0]
  if parity["orientation"]!=old["orientation"] or abs(parity["training_capped_loss"]-old["training_capped_loss"])>1e-12 or abs(parity["held_capped_loss"]-old["held_capped_loss"])>1e-12 or parity["supported_tracks"]!=old["supported_tracks"] or parity["changed_candidate_id_count"]!=old["changed_candidate_id_count"] or [a["refit_candidate_id"] for a in parity["assignments"]]!=[a["refit_candidate_id"] for a in old["assignments"]]: raise AssertionError("published 25-degree parity failed")
  results.append({"cell_id":cell["cell_id"],"track_count":len(tracks),"occupied_second_support":denominator,"observation_count":sum(t["observation_count"] for t in tracks),"track_span_s":sum(t["span_s"] for t in tracks),"baseline_training_capped_loss":baseline,"baseline_held_capped_loss":baseline_held_num/denominator,"baseline_held_rms_hz_supported":None if not baseline_held_n else (baseline_held_sq/baseline_held_n)**.5,"baseline_supported_tracks":baseline_supported,"scenarios":scenarios,"training_loss_width_ranking":[x["full_fov_deg"] for x in sorted([s for s in scenarios if s["mapping"]==[0,1]],key=lambda x:x["training_capped_loss"])]}); print("completed",cell["cell_id"],flush=True)
 out={"schema":"staged-cone-width-sweep/v1","full_fov_deg":list(WIDTHS),"axis_separation_deg":20,"truth_used":False,"held_used_for_fit":False,"published_25_parity":True,"candidate_policy":next(iter(policies)),"elapsed_s":time.monotonic()-begun,"results":results,"session_bindings":bindings,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__),"published_source":digest(BASE),"published_results":digest(BASE_RESULTS),"search":digest(base.SEARCH),"loader":digest(base.LOADER),"cone":digest(base.CONE),"metadata":digest(base.META),"locations":digest(ROOT/"reports/2026_09_23_train_fixed_cone/locations.json"),"manifests":{k:digest(v) for k,v in manifests.items()}}}
 path=HERE/"results.json"; path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); (HERE/"results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")
if __name__=="__main__": main()
