"""Calibration-only fixed-point shortlist/CFO and Student-t parameter prototype."""
from __future__ import annotations
import hashlib,json,pickle,sys,time
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));SOURCE=HERE.parent/'2026_09_27_roof_direction_subset';ROOT=Path('/srv/bulk/leo')
from fit_frequency import fit
from robust_core import train_shortlist
from leo.analysis.adaptive_tle_prediction import ReceiverPoint,RegionalTrackPredictionEvaluator,build_prediction_banks
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km

INITIAL=(135.4204,1.63354);MAX_ROUNDS=5
def digest(x):return 'sha256:'+hashlib.sha256(x).hexdigest()
def atomic(path,x):
 t=path.with_suffix(path.suffix+'.tmp');t.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n');t.replace(path)
class CachedInput:
 def __init__(self,x):self.x=x
 def load(self,s):
  if s!=self.x.session_id:raise KeyError(s)
  return self.x
def point(lat,lon):
 q=np.deg2rad([lat,lon]);return ReceiverPoint(geodetic_to_ecef_km(lat,lon,0),np.array([np.cos(q[0])*np.cos(q[1]),np.cos(q[0])*np.sin(q[1]),np.sin(q[0])]))
def relative_change(old,new):return abs(float(new)-float(old))/float(old)
def convergence(old,new,old_maps,new_maps):
 overlap=set(old_maps)&set(new_maps);stable=sum(old_maps[x]==new_maps[x] for x in overlap)/len(overlap) if overlap else 0.
 return {'scale_relative_change':relative_change(old[0],new[0]),'df_relative_change':relative_change(old[1],new[1]),'map_stability':stable,'converged':relative_change(old[0],new[0])<.01 and relative_change(old[1],new[1])<.01 and stable>=.99}
def gather():
 manifest=json.loads((SOURCE/'evaluation_manifest.json').read_text());inventory={x['session_id']:x for x in json.loads((SOURCE/'evaluation_inventory.json').read_text())};cache={};digests={}
 selected=[x for x in manifest['sessions'] if x['split']=='calibration']
 if len(selected)!=6:raise ValueError('expected six calibration sessions')
 for item in selected:
  sid=item['pose']['session_id'];e=inventory[sid];payload=Path(e['cache_file']).read_bytes()
  if not e['ready'] or e['split']!='calibration' or digest(payload)!=e['cache_sha256']:raise ValueError(f'{sid}: invalid calibration cache')
  raw=pickle.loads(payload);p=prepare_adaptive_tle_position_inputs(sid,inputs=CachedInput(raw),archive=TleArchiveReader(Path('/var/lib/leo/tle')))
  if (p.input_manifest_sha256,p.analysis_manifest_sha256)!=(e['input_manifest_sha256'],e['analysis_manifest_sha256']):raise ValueError(f'{sid}: digest mismatch')
  pose=item['pose']['pose_authority'];banks,receipt=build_prediction_banks(p.catalogue,p.candidate_indices,p.start_utc_ns,p.tracks,taus_s=np.array([0.]))
  blocks=defaultdict(list)
  for b in RegionalTrackPredictionEvaluator(banks,lambda x,y,lat=pose['latitude_deg'],lon=pose['longitude_deg']:point(lat,lon),taus_s=np.array([0.]))(0,0):blocks[b.track_id].append(b)
  rows=[]
  for t in p.tracks:
   bb=blocks[t.track_id];pred=np.concatenate([x.predictions_hz[:,0,:] for x in bb]);ids=np.concatenate([x.candidate_ids for x in bb]);vis=np.concatenate([np.asarray(x.visible).reshape(-1) for x in bb]);keep=np.flatnonzero(vis)
   if not len(keep):raise ValueError(f'{sid}/{t.track_id}: no visible candidates')
   rows.append({'track_id':t.track_id,'candidate_ids':ids[keep].astype(int),'predicted_hz':pred[keep].astype(np.float64),'measured_hz':np.asarray(t.measured_hz,float),'training_mask':np.asarray(t.training_mask,bool),'weight_seconds':len(np.unique(np.floor(t.times_s)))})
  cache[sid]=rows;digests[sid]={'input_manifest_sha256':p.input_manifest_sha256,'analysis_manifest_sha256':p.analysis_manifest_sha256,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,'tracks':len(rows),'prediction_candidates':sum(len(x['candidate_ids']) for x in rows)}
  print('GATHER',sid,len(rows),digests[sid]['prediction_candidates'],flush=True)
 return cache,digests
def select(cache,parameters):
 scale,df=parameters;sessions={};maps={};audit={}
 for sid,tracks in cache.items():
  fitted=[];rows=[]
  for t in tracks:
   s=train_shortlist(t['predicted_hz'],t['measured_hz'],t['training_mask'],np.ones(len(t['candidate_ids']),bool),scale_hz=scale,df=df,top_k=3)
   ix=np.asarray(s['candidate_indices']);reserve=~t['training_mask'];residual=t['measured_hz'][None,:]-t['predicted_hz'][ix]-np.asarray(s['profiled_cfo_hz'])[:,None]
   fitted.append((residual[:,reserve].astype(float),np.asarray(s['log_weights'],float),float(t['weight_seconds'])))
   cids=t['candidate_ids'][ix].astype(int).tolist();maps[(sid,t['track_id'])]=cids[0]
   rows.append({'track_id':t['track_id'],'candidate_ids':cids,'log_weights':s['log_weights'],'weights':s['weights'],'profiled_cfo_hz':s['profiled_cfo_hz'],'training_log_likelihood':s['training_log_likelihood'],'training_rms_hz':s['training_rms_hz'],'training_observations':s['training_observations'],'reserve_observations':int(np.count_nonzero(reserve)),'weight_seconds':t['weight_seconds'],'reserve_residual_hz':residual[:,reserve].tolist()})
  sessions[sid]=fitted;audit[sid]=rows
 return sessions,maps,audit
def main():
 target=HERE/'frequency_fixedpoint.json'
 if target.exists():raise FileExistsError('fixed-point result exists; do not overwrite')
 started=time.monotonic();cache,digests=gather();parameters=INITIAL;rounds=[];iteration_converged=False;final_audit=None
 for index in range(1,MAX_ROUNDS+1):
  sessions,maps,audit=select(cache,parameters);fitted=fit(sessions);new=(fitted['scale_hz'],fitted['degrees_of_freedom'])
  _,updated_maps,_=select(cache,new);status=convergence(parameters,new,maps,updated_maps)
  rounds.append({'round':index,'selection_parameters':{'scale_hz':parameters[0],'degrees_of_freedom':parameters[1]},'fit':fitted,**status,'changed_map_tracks':sum(maps[k]!=updated_maps[k] for k in maps),'track_count':len(maps)})
  print('ROUND',index,new,status,flush=True);parameters=new;previous_maps=maps
  if status['converged']:iteration_converged=True;break
 # Freeze the last fitted parameters, reselect once, and quantify one final refit discrepancy.
 sessions,maps,final_audit=select(cache,parameters);refit=fit(sessions);refit_parameters=(refit['scale_hz'],refit['degrees_of_freedom']);_,refit_maps,_=select(cache,refit_parameters);refit_status=convergence(parameters,refit_parameters,maps,refit_maps);converged=iteration_converged and refit_status['converged']
 out={'protocol':{'scope':'six calibration scans only; no holdouts, reception, or search','initial_parameters':{'scale_hz':INITIAL[0],'degrees_of_freedom':INITIAL[1]},'iteration':'full visible catalogue reselected using training-only shared robust_core shortlist/CFO; reserve mixture fit via fit_frequency.fit','convergence':'both parameter relative changes <1% and MAP IDs >=99% unchanged after reselection at updated parameters; max5 rounds; final refit must also pass','interpretation':'approximate conditional fixed point, not a global MLE; no LOSO claim'},'converged':converged,'iteration_converged':iteration_converged,'stopped_reason':'converged' if converged else ('final-refit-check-failed' if iteration_converged else 'maximum-rounds-reached'),'rounds':rounds,'frozen_final_parameters':{'scale_hz':parameters[0],'degrees_of_freedom':parameters[1]},'final_refit':refit,'final_refit_difference':refit_status,'source_digests':digests,'final_tracks':final_audit,'elapsed_s':time.monotonic()-started,'code_sha256':digest(Path(__file__).read_bytes()),'robust_core_sha256':digest((HERE/'robust_core.py').read_bytes()),'fit_frequency_sha256':digest((HERE/'fit_frequency.py').read_bytes())}
 atomic(target,out)
 compatible={'calibration_sessions':sorted(cache),'parameters':{'scale_hz':parameters[0],'degrees_of_freedom':parameters[1],'optimizer_success':bool(refit['optimizer_success'])},'converged':converged,'extraction_file':'frequency_fixedpoint.json','extraction_sha256':digest(target.read_bytes()),'code_sha256':out['code_sha256'],'robust_core_sha256':out['robust_core_sha256'],'fit_frequency_sha256':out['fit_frequency_sha256']}
 atomic(HERE/'fixedpoint_parameters.json',compatible)
if __name__=='__main__':main()
