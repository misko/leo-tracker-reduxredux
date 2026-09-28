"""Extract training-selected calibration frequency residuals at metadata site.

This read-only research runner never loads a holdout cache. Candidate ranking and
constant CFO profiling use each track's training partition only. Reserved
residuals are emitted only after the training shortlist is frozen.
"""
from __future__ import annotations
import hashlib,json,math,pickle,sys,time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
import numpy as np

from leo.analysis.adaptive_tle_prediction import ReceiverPoint,RegionalTrackPredictionEvaluator,build_prediction_banks
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from robust_core import robust_location as _shared_robust_location,student_t_logpdf,train_shortlist as _shared_train_shortlist
SOURCE=HERE.parent/'2026_09_27_roof_direction_subset';ROOT=Path('/srv/bulk/leo')
DF=4.;SCALE_HZ=100.;TOP_K=3
def digest(x):return 'sha256:'+hashlib.sha256(x).hexdigest()
def atomic(path,value):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)
class CachedInput:
 def __init__(self,x):self.x=x
 def load(self,sid):
  if sid!=self.x.session_id:raise KeyError(sid)
  return self.x
def point(lat,lon):
 q=np.deg2rad([lat,lon]);return ReceiverPoint(geodetic_to_ecef_km(lat,lon,0),np.array([np.cos(q[0])*np.cos(q[1]),np.cos(q[0])*np.sin(q[1]),np.sin(q[0])]))
def robust_location(values,*,scale=SCALE_HZ,df=DF):
 return _shared_robust_location(values,scale_hz=scale,degrees_of_freedom=df)
def student_nll(residual,*,scale=SCALE_HZ,df=DF):
 return float(-np.sum(student_t_logpdf(residual,scale_hz=scale,degrees_of_freedom=df)))
def shortlist(predicted,measured,training,visible,ids):
 predicted=np.asarray(predicted,float);measured=np.asarray(measured,float);training=np.asarray(training,bool);visible=np.asarray(visible,bool).reshape(-1)
 if predicted.shape!=(len(ids),len(measured)) or visible.shape!=(len(ids),):raise ValueError('candidate shapes disagree')
 result=_shared_train_shortlist(predicted,measured,training,visible,scale_hz=SCALE_HZ,df=DF,top_k=TOP_K)
 return [{'candidate_index':int(i),'candidate_id':int(ids[i]),'profiled_cfo_hz':float(cfo),'training_nll':float(-ll),'log_weight':float(lw),'weight':float(w)} for i,cfo,ll,lw,w in zip(result['candidate_indices'],result['profiled_cfo_hz'],result['training_log_likelihood'],result['log_weights'],result['weights'],strict=True)]
def extract(prepared,lat,lon):
 banks,receipt=build_prediction_banks(prepared.catalogue,prepared.candidate_indices,prepared.start_utc_ns,prepared.tracks,taus_s=np.array([0.]))
 blocks=defaultdict(list)
 for b in RegionalTrackPredictionEvaluator(banks,lambda e,n:point(lat,lon),taus_s=np.array([0.]))(0,0):blocks[b.track_id].append(b)
 output=[]
 for track in prepared.tracks:
  bb=blocks[track.track_id];pred=np.concatenate([x.predictions_hz[:,0,:] for x in bb]);ids=np.concatenate([x.candidate_ids for x in bb]);vis=np.concatenate([np.asarray(x.visible).reshape(-1) for x in bb])
  chosen=shortlist(pred,track.measured_hz,track.training_mask,vis,ids)
  for rank,row in enumerate(chosen):
   residual=np.asarray(track.measured_hz)-pred[row['candidate_index']]-row['profiled_cfo_hz'];tr=np.asarray(track.training_mask,bool)
   output.append({'track_id':track.track_id,'weight_seconds':int(len(np.unique(np.floor(track.times_s)))),'candidate_id':row['candidate_id'],'candidate_index':row['candidate_index'],'visible_eligible':True,'training_rank':rank,'profiled_cfo_hz':row['profiled_cfo_hz'],'training_nll':row['training_nll'],'training_log_likelihood':-row['training_nll'],'log_weight':row['log_weight'],'weight':row['weight'],'extraction_seed_scale_hz':SCALE_HZ,'extraction_seed_degrees_of_freedom':DF,
    'training_observations':int(np.count_nonzero(tr)),'reserve_observations':int(np.count_nonzero(~tr)),
    'training_observation_ids':[x for x,k in zip(track.observation_ids,tr,strict=True) if k],'reserve_observation_ids':[x for x,k in zip(track.observation_ids,tr,strict=True) if not k],
    'training_residual_hz':residual[tr].tolist(),'reserve_residual_hz':residual[~tr].tolist()})
 return output,asdict(receipt)
def main():
 started=time.monotonic();manifest=json.loads((SOURCE/'evaluation_manifest.json').read_text());inventory={x['session_id']:x for x in json.loads((SOURCE/'evaluation_inventory.json').read_text())};sessions=[]
 selected=[x for x in manifest['sessions'] if x['split']=='calibration']
 if len(selected)!=6:raise ValueError('expected exactly six frozen calibration sessions')
 for item in selected:
  sid=item['pose']['session_id'];entry=inventory[sid]
  if entry['split']!='calibration' or not entry['ready']:raise ValueError(f'{sid}: calibration cache not ready')
  path=Path(entry['cache_file']);payload=path.read_bytes()
  if digest(payload)!=entry['cache_sha256']:raise ValueError(f'{sid}: cache digest mismatch')
  raw=pickle.loads(payload);p=prepare_adaptive_tle_position_inputs(sid,inputs=CachedInput(raw),archive=TleArchiveReader(Path('/var/lib/leo/tle')))
  if (p.input_manifest_sha256,p.analysis_manifest_sha256)!=(entry['input_manifest_sha256'],entry['analysis_manifest_sha256']):raise ValueError(f'{sid}: prepared digest mismatch')
  pose=item['pose']['pose_authority'];rows,receipt=extract(p,pose['latitude_deg'],pose['longitude_deg'])
  sessions.append({'session_id':sid,'input_manifest_sha256':p.input_manifest_sha256,'analysis_manifest_sha256':p.analysis_manifest_sha256,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,'track_count':len(p.tracks),'candidate_rows':rows,'prediction_receipt':receipt})
  atomic(HERE/'calibration_frequency.partial.json',{'protocol':{'df':DF,'scale_hz':SCALE_HZ,'top_k':TOP_K},'sessions':sessions});print(sid,len(p.tracks),len(rows),flush=True)
 out={'protocol':{'corpus':'six frozen calibration sessions only','site':'operator metadata WGS84 position; diagnostic calibration geometry','candidate_selection':'full causal catalogue; zero timing; fixed df=4 scale=100Hz normalized Student-t training likelihood; top3 per track','cfo':'shared robust_core Student-t IRLS (1e-8Hz tolerance, max100) initialized by training median; reserve never used','purpose':'residual extraction for later normalized Student-t calibration; no holdout or search'},'sessions':sessions,'elapsed_s':time.monotonic()-started,'code_sha256':digest(Path(__file__).read_bytes())}
 atomic(HERE/'calibration_frequency.json',out)
if __name__=='__main__':main()
