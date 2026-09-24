#!/usr/bin/env python3
import argparse, hashlib, importlib.util, json, sys, time, multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
BASE_PATH=ROOT/"reports/2026_09_23_joint_cone_profile/staged_run.py"
WIDTH_PATH=ROOT/"reports/2026_09_23_staged_cone_width_sweep/run.py"
CENTERS={"cell_3":(37.90230600858144,-122.39601220145329),"cell_5":(37.80184772652388,-122.41023886955833)}
WIDTHS=(10.,20.,25.,30.,40.,50.); METHODS=("baseline",)+tuple(f"cone_{int(w)}" for w in WIDTHS)

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Evaluator:
 def __init__(self):
  self.base=load(BASE_PATH,"grid_base"); self.width=load(WIDTH_PATH,"grid_width"); self.search=load(self.base.SEARCH,"grid_search"); self.loader=load(self.base.LOADER,"grid_loader"); self.cone=load(self.base.CONE,"grid_cone")
  manifests={"first_train":ROOT/"reports/2026_09_23_long_training_cache_full8h/manifest.json","second_train":ROOT/"reports/2026_09_23_long_training_cache_second8h/manifest.json"}; roots={"first_train":Path("/tmp/leo-long-training-cache-full8h"),"second_train":Path("/tmp/leo-long-training-cache-second8h")}
  self.sessions=[]; self.session_bindings=[]; policies=set()
  for group in roots:
   for sid in json.loads(manifests[group].read_text())["source_group"]["session_ids"][:6]:
    session=self.loader.load_session(self.search,roots[group]/sid,sid); self.sessions.append(session); receipt=json.loads(session["receipt"].read_text()); policies.add(receipt["candidate_policy"]); self.session_bindings.append({"group":group,"session_id":sid,"receipt":digest(session["receipt"]),"cache":digest(session["cache"]),"candidate_count":len(session["candidate_ids"])})
  if len(self.sessions)!=12 or len(policies)!=1: raise ValueError("TRAIN cohort/policy mismatch")
  metadata=json.loads(self.base.META.read_text())["sessions"]; self.labels={(s["session_id"],t["track_id"]):int(t["receiver_id"]) for s in metadata for t in s["tracks"]}
  self.orientations=self.cone.orientation_grid(15); self.axes=self.cone.axes_batched(self.orientations)
 def prepare(self,lat,lon):
  ecef,up=self.search.receiver_ecef(lat,lon); tracks=[]
  for session in self.sessions:
   receiver={"latlon":(lat,lon),"ecef":ecef,"session_id":session["session_id"]}
   tracks += [self.base.prepare_track(self.search,self.cone,t,session["candidate_ids"],receiver,up,self.labels[(session["session_id"],t["track_id"])]) for t in session["prepared"]]
  return tracks
 def fit_orientations(self,tracks,mapping=(0,1),batch=512):
  best={w:(-1.,None) for w in WIDTHS}; thresholds={w:np.cos(np.radians(w/2)) for w in WIDTHS}
  for start in range(0,len(self.orientations),batch):
   stop=min(start+batch,len(self.orientations)); gains={w:np.zeros(stop-start) for w in WIDTHS}
   for t in tracks:
    if t["baseline"] is None or t["baseline_cost"]>=1: continue
    axis=self.axes[start:stop,mapping[t["receiver_id"]]]; minimum=np.min(np.einsum("oc,kc->ok",axis,t["baseline_directions"],optimize=True),axis=1); improvement=t["weight_s"]*(1-t["baseline_cost"])
    for w in WIDTHS: gains[w]+=improvement*(minimum>=thresholds[w])
   for w in WIDTHS:
    i=int(np.argmax(gains[w])); candidate=(float(gains[w][i]),start+i)
    if candidate[0]>best[w][0]: best[w]=candidate
  return best
 def baseline(self,tracks):
  total=sum(t["weight_s"] for t in tracks); train=sum(t["weight_s"]*t["baseline_cost"] for t in tracks); held_num=held_sq=0.; held_n=0
  for t in tracks:
   if t["baseline"] is None: held_num+=t["weight_s"]
   else:
    held=t["baseline_errors"][~t["train_mask"]]; held_num+=t["weight_s"]*min(float(np.mean(held**2))/self.base.CAP_HZ**2,1.); held_sq+=float(np.sum(held**2)); held_n+=len(held)
  return {"training_capped_loss":train/total,"held_capped_loss":held_num/total,"supported_tracks":sum(t["baseline"] is not None for t in tracks),"supported_occupied_second_support":total,"held_rms_hz_supported":(held_sq/held_n)**.5}
 def evaluate(self,lat,lon,mapping=(0,1),keep_assignments=False):
  begun=time.monotonic(); tracks=self.prepare(lat,lon); prepared_s=time.monotonic()-begun; best=self.fit_orientations(tracks,mapping); fit_s=time.monotonic()-begun-prepared_s; methods={"baseline":self.baseline(tracks)}
  for w in WIDTHS:
   gain,oi=best[w]; row=self.width.evaluate(self.base,tracks,self.axes,oi,mapping,w)
   if not keep_assignments: row.pop("assignments",None)
   row.update(orientation=[int(x) for x in self.orientations[oi]],full_fov_deg=w,stage_baseline_gain=gain); methods[f"cone_{int(w)}"]=row
  return methods,{"prepare_s":prepared_s,"orientation_and_refit_s":fit_s,"total_s":time.monotonic()-begun}

def coordinate(search,region,east,north): return search.offset_coordinate(CENTERS[region],east,north)
def point_key(lat,lon): return (round(lat,10),round(lon,10))

def benchmark():
 ev=Evaluator(); points=[CENTERS["cell_3"],CENTERS["cell_5"],((CENTERS["cell_3"][0]+CENTERS["cell_5"][0])/2,(CENTERS["cell_3"][1]+CENTERS["cell_5"][1])/2)]; rows=[]
 for lat,lon in points:
  methods,timing=ev.evaluate(lat,lon,(0,1),True); exchanged,_=ev.evaluate(lat,lon,(1,0),True)
  for method in METHODS:
   for field in ("training_capped_loss","held_capped_loss","supported_tracks","supported_occupied_second_support"):
    if methods[method][field]!=exchanged[method][field]: raise AssertionError("receiver mapping parity failed")
   if method!="baseline" and [x["refit_candidate_id"] for x in methods[method]["assignments"]]!=[x["refit_candidate_id"] for x in exchanged[method]["assignments"]]: raise AssertionError("receiver mapping assignment parity failed")
  rows.append({"latitude_deg":lat,"longitude_deg":lon,"timing":timing,"mapping_symmetry_verified":True,"method_training_losses":{k:v["training_capped_loss"] for k,v in methods.items()}})
 mean=float(np.mean([r["timing"]["total_s"] for r in rows])); out={"schema":"local-cone-grid-benchmark/v1","point_count":3,"rows":rows,"mean_point_s":mean,"worst_case_point_count":302,"projected_worst_case_s":302*mean,"hard_limit_s":1200,"launch_allowed":302*mean<=1200,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__)}}
 (HERE/"benchmark.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps(out,indent=2))

def best_one(rows,method):
 return min(rows,key=lambda r:(r["methods"][method]["training_capped_loss"],r["east_km"],r["north_km"]))

_WORKER_EVALUATOR=None
def worker_evaluate(item):
 lat,lon=item; methods,timing=_WORKER_EVALUATOR.evaluate(lat,lon); return lat,lon,methods,timing

def run_grid():
 bench=json.loads((HERE/"benchmark.json").read_text())
 if not bench["launch_allowed"]: raise RuntimeError("benchmark projection exceeds 20-minute bound")
 begun=time.monotonic(); ev=Evaluator(); points={}; region_rows={r:[] for r in CENTERS}; counter=0
 global _WORKER_EVALUATOR; _WORKER_EVALUATOR=ev
 def evaluate_specs(pool,specs,level):
  nonlocal counter
  coordinates={point_key(*coordinate(ev.search,r,e,n)):coordinate(ev.search,r,e,n) for r,e,n in specs}
  pending=[value for key,value in coordinates.items() if key not in points]
  for lat,lon,methods,timing in pool.map(worker_evaluate,pending,chunksize=1):
   counter+=1; points[point_key(lat,lon)]={"point_id":f"p{counter:04d}","latitude_deg":lat,"longitude_deg":lon,"level_km":level,"methods":methods,"timing":timing}
  for region,east,north in specs:
   lat,lon=coordinate(ev.search,region,east,north); point=points[point_key(lat,lon)]; row={"point_id":point["point_id"],"east_km":east,"north_km":north,"methods":point["methods"]}
   if not any(x["point_id"]==row["point_id"] for x in region_rows[region]): region_rows[region].append(row)
 with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context("fork")) as pool:
  coarse=[(r,float(e),float(n)) for r in CENTERS for e in np.arange(-10,10.1,5) for n in np.arange(-10,10.1,5)]; evaluate_specs(pool,coarse,5.)
  for spacing in (2.5,1.25):
   specs=[]
   for region in CENTERS:
    seeds={}
    for method in METHODS:
     row=best_one(region_rows[region],method); seeds[(row["east_km"],row["north_km"])]=row
    for east,north in seeds:
     for de in (-spacing,0,spacing):
      for dn in (-spacing,0,spacing):
       e,n=east+de,north+dn
       if -10<=e<=10 and -10<=n<=10: specs.append((region,e,n))
   evaluate_specs(pool,specs,spacing)
 winners={}; regional_winners={region:{} for region in CENTERS}
 for method in METHODS:
  candidates=[]
  for region in CENTERS:
   row=best_one(region_rows[region],method); regional_winners[region][method]={"point_id":row["point_id"],"training_capped_loss":row["methods"][method]["training_capped_loss"]}; candidates.append((row["methods"][method]["training_capped_loss"],region,row["east_km"],row["north_km"],row["point_id"]))
  value=min(candidates); winners[method]={"point_id":value[4],"region":value[1],"training_capped_loss":value[0]}
 out={"schema":"local-cone-grid/v1","complete":True,"truth_used_for_fit":False,"held_used_for_selection":False,"methods":list(METHODS),"points":list(points.values()),"winners":winners,"regional_winners":regional_winners,"regions":[{"region":r,"center_latitude_deg":c[0],"center_longitude_deg":c[1],"half_width_km":10} for r,c in CENTERS.items()],"elapsed_s":time.monotonic()-begun,"benchmark":bench,"session_bindings":ev.session_bindings,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__),"base_source":digest(BASE_PATH),"width_source":digest(WIDTH_PATH)}}
 path=HERE/"inference.json"; path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); (HERE/"inference.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")

if __name__=="__main__":
 p=argparse.ArgumentParser(); p.add_argument("--benchmark",action="store_true"); args=p.parse_args(); benchmark() if args.benchmark else run_grid()
