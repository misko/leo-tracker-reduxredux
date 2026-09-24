#!/usr/bin/env python3
import argparse, hashlib, importlib.util, json, multiprocessing, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parents[2]; HERE=Path(__file__).parent
GRID=ROOT/"reports/2026_09_24_local_cone_grid/inference.json"; GRID_SEAL=ROOT/"reports/2026_09_24_local_cone_grid/inference.sha256"
SEARCH=ROOT/"reports/2026_09_23_long_training_search/search.py"; CAP=800.; COARSE=np.arange(-5.,5.1,1.)

def select_tau(losses,taus):
 return min(range(len(taus)),key=lambda i:(float(losses[i]),abs(float(taus[i])),float(taus[i])))

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
def digest(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Engine:
 def __init__(self):
  self.search=load(SEARCH,"clock_search"); self.sessions=[]; policies=set(); self.bindings=[]
  configs=(("first_train",Path("/tmp/leo-long-training-cache-full8h"),ROOT/"reports/2026_09_23_long_training_cache_full8h/manifest.json"),("second_train",Path("/tmp/leo-long-training-cache-second8h"),ROOT/"reports/2026_09_23_long_training_cache_second8h/manifest.json"))
  for group,root,manifest in configs:
   for sid in json.loads(manifest.read_text())["source_group"]["session_ids"][:6]:
    receipt_path=root/sid/"cache_receipt.json"; cache_path=root/sid/"state_cache.npz"; receipt=json.loads(receipt_path.read_text()); policies.add(receipt["candidate_policy"])
    with np.load(cache_path,allow_pickle=False) as a: arrays={k:a[k] for k in a.files}
    tracks=[]
    for t in receipt["prepared_evidence"]["tracks"]:
     times=np.asarray(t["times_s"],float)
     mask=np.asarray(t["training_mask"],bool)
     if np.ptp(times)>=3:
      if not np.any(mask) or not np.any(~mask): raise ValueError("empty TRAIN or held mask")
      tracks.append({"track_id":t["track_id"],"times":times,"measured":np.asarray(t["measured_hz"],float),"train":mask,"weight":int(len(np.unique(np.floor(times))))})
    grid=arrays["receive_plus_tau_offset_ns"].astype(float)/1e9
    self.sessions.append({"session_id":sid,"candidate_ids":arrays["candidate_id"],"grid":grid,"position":arrays["position_ecef_km"],"velocity":arrays["velocity_ecef_km_s"],"tracks":tracks})
    self.bindings.append({"group":group,"session_id":sid,"receipt":digest(receipt_path),"cache":digest(cache_path),"candidate_count":len(arrays["candidate_id"]),"margin_before_s":min(t["times"].min()-grid[0] for t in tracks),"margin_after_s":min(grid[-1]-t["times"].max() for t in tracks)})
  if len(self.sessions)!=12 or len({s["session_id"] for s in self.sessions})!=12 or len(policies)!=1: raise ValueError("cohort/policy mismatch")
  if min(x["margin_before_s"] for x in self.bindings)<5 or min(x["margin_after_s"] for x in self.bindings)<5: raise ValueError("cache lacks frozen tau margin")
 def interpolate(self,session,times,taus):
  query=times[:,None]+taus[None,:]; grid=session["grid"]
  if query.min()<grid[0] or query.max()>grid[-1]: raise ValueError("tau outside cache")
  fractional=(query-grid[0])/(grid[1]-grid[0]); low=np.floor(fractional).astype(int); high=np.minimum(low+1,len(grid)-1); w=fractional-low
  p=session["position"][:,low,:]*(1-w)[None,:,:,None]+session["position"][:,high,:]*w[None,:,:,None]
  v=session["velocity"][:,low,:]*(1-w)[None,:,:,None]+session["velocity"][:,high,:]*w[None,:,:,None]
  return p,v
 def profile(self,lat,lon,taus,held=False,assignments=False):
  receiver,up=self.search.receiver_ecef(lat,lon); numerator=np.zeros(len(taus)); held_num=np.zeros(len(taus)); assignment=[[] for _ in taus]
  for session in self.sessions:
   for track in session["tracks"]:
    p,v=self.interpolate(session,track["times"],taus); delta=p-receiver; distance=np.linalg.norm(delta,axis=-1); prediction=-self.search.REFERENCE_RF_HZ/self.search.LIGHT_KM_S*np.sum(delta*v,axis=-1)/distance
    residual=track["measured"][None,:,None]-prediction; train=track["train"]; offsets=np.mean(residual[:,train,:],axis=1); errors=residual-offsets[:,None,:]
    rms=np.sqrt(np.mean(errors[:,train,:]**2,axis=1)); visible=np.max(np.sum(delta*up,axis=-1)/distance,axis=1)>=0; rms=np.where(visible,rms,np.inf); winner=np.argmin(rms,axis=0); values=rms[winner,np.arange(len(taus))]; costs=np.minimum((values/CAP)**2,1.); numerator+=track["weight"]*costs
    if held or assignments:
     for j,index in enumerate(winner):
      candidate=None if not np.isfinite(values[j]) else str(session["candidate_ids"][index]); h=errors[index,~train,j]; hc=1. if candidate is None or not len(h) else min(float(np.mean(h**2))/CAP**2,1.); held_num[j]+=track["weight"]*hc
      if assignments: assignment[j].append({"session_id":session["session_id"],"track_id":track["track_id"],"candidate_id":candidate,"training_cfo_hz":float(offsets[index,j]) if candidate else None})
  denominator=sum(t["weight"] for s in self.sessions for t in s["tracks"])
  return numerator/denominator,held_num/denominator,assignment
 def evaluate(self,point):
  lat,lon=point["latitude_deg"],point["longitude_deg"]; begun=time.monotonic(); coarse,_,_=self.profile(lat,lon,COARSE); ci=select_tau(coarse,COARSE); center=COARSE[ci]; fine=np.arange(max(-5.,center-1),min(5.,center+1)+.001,.25); train,held,assign=self.profile(lat,lon,fine,True,True); bi=select_tau(train,fine); tau=float(fine[bi]); zero_i=int(np.flatnonzero(np.isclose(fine,0))[0]) if np.any(np.isclose(fine,0)) else None
  if zero_i is None:
   ztrain,zheld,_=self.profile(lat,lon,np.array([0.]),True,False); zero_train,zero_held=float(ztrain[0]),float(zheld[0])
  else: zero_train,zero_held=float(train[zero_i]),float(held[zero_i])
  if float(train[bi])>zero_train+1e-12: raise AssertionError("fitted tau worse than tau zero")
  merged={float(t):float(v) for t,v in zip(COARSE,coarse)}; merged.update({float(t):float(v) for t,v in zip(fine,train)}); profile_tau=sorted(merged)
  return {"point_id":point["point_id"],"latitude_deg":lat,"longitude_deg":lon,"tau_s":tau,"boundary_hit":tau in (-5.,5.),"baseline_training_loss":zero_train,"tau0_training_capped_loss":zero_train,"clock_training_loss":float(train[bi]),"training_capped_loss":float(train[bi]),"clock_held_loss":float(held[bi]),"held_capped_loss":float(held[bi]),"tau0_held_capped_loss":zero_held,"training_improvement":zero_train-float(train[bi]),"profile_tau_s":profile_tau,"profile_training_loss":[merged[x] for x in profile_tau],"assignments":assign[bi],"elapsed_s":time.monotonic()-begun}

_ENGINE=None
def worker(point): return _ENGINE.evaluate(point)

def benchmark():
 e=Engine(); source=json.loads(GRID.read_text()); centers=[(37.90230600858144,-122.39601220145329),(37.80184772652388,-122.41023886955833)]; centers.append(((centers[0][0]+centers[1][0])/2,(centers[0][1]+centers[1][1])/2)); rows=[e.evaluate({"point_id":f"benchmark_{i}","latitude_deg":x[0],"longitude_deg":x[1]}) for i,x in enumerate(centers)]
 for row in rows:
  match=min(source["points"],key=lambda p:(p["latitude_deg"]-row["latitude_deg"])**2+(p["longitude_deg"]-row["longitude_deg"])**2)
  if match["latitude_deg"]==row["latitude_deg"] and match["longitude_deg"]==row["longitude_deg"] and abs(row["baseline_training_loss"]-match["methods"]["baseline"]["training_capped_loss"])>1e-10: raise AssertionError("tau-zero parity failed")
 mean=float(np.mean([x["elapsed_s"] for x in rows])); out={"schema":"shared-clock-benchmark/v1","rows":rows,"mean_point_s":mean,"point_count":len(source["points"]),"workers":4,"projected_wall_s":mean*len(source["points"])/4,"launch_allowed":mean*len(source["points"])/4<1200,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__)}}; (HERE/"benchmark.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps({k:v for k,v in out.items() if k!="rows"},indent=2))

def main():
 raw=GRID.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=GRID_SEAL.read_text().strip(): raise ValueError("local grid seal mismatch")
 source=json.loads(raw); bench=json.loads((HERE/"benchmark.json").read_text())
 if not bench["launch_allowed"]: raise RuntimeError("runtime bound failed")
 begun=time.monotonic(); engine=Engine(); global _ENGINE; _ENGINE=engine
 with ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context("fork")) as pool: rows=list(pool.map(worker,source["points"],chunksize=1))
 for row in rows:
  expected=next(p for p in source["points"] if p["point_id"]==row["point_id"])["methods"]["baseline"]["training_capped_loss"]
  if abs(row["baseline_training_loss"]-expected)>1e-10: raise AssertionError("all-point tau-zero parity failed")
 index={r["point_id"]:r for r in rows}; winner=min(rows,key=lambda r:(r["clock_training_loss"],abs(r["tau_s"]),r["tau_s"],r["point_id"])); baseline=min(rows,key=lambda r:(r["baseline_training_loss"],r["point_id"])); out={"schema":"shared-clock-grid/v1","complete":True,"truth_used":False,"held_used_for_selection":False,"clock_prior_calibrated":False,"tau_range_s":[-5,5],"rows":rows,"clock_winner_point_id":winner["point_id"],"winner_point_id":winner["point_id"],"baseline_winner_point_id":baseline["point_id"],"winner_tau_s":winner["tau_s"],"boundary_hit_count":sum(r["boundary_hit"] for r in rows),"elapsed_s":time.monotonic()-begun,"session_bindings":engine.bindings,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__),"local_grid":digest(GRID),"search":digest(SEARCH)}}; path=HERE/"inference.json"; path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); (HERE/"inference.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")

if __name__=="__main__":
 p=argparse.ArgumentParser(); p.add_argument("--benchmark",action="store_true"); a=p.parse_args(); benchmark() if a.benchmark else main()
