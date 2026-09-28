"""Bounded Doppler-only top-3 associations and per-observation directions."""
from __future__ import annotations
import hashlib,json,pickle,sys,time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from direction_features import marginal_direction,unit_enu
from leo.analysis.adaptive_tle_prediction import ReceiverPoint,RegionalTrackPredictionEvaluator,build_prediction_banks
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,persistent_hop_tracklet_graph,reconstruct_persistent_hop_trajectories
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.sky.frames import geodetic_to_ecef_km,julian_day_from_utc_ns,greenwich_mean_sidereal_time_rad,teme_to_ecef,ecef_to_enu_matrix,look_angles
from leo.sky.propagation import propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2

ROOT=Path('/srv/bulk/leo'); SIGMA=100.; TOP=3
class CacheStore:
 def __init__(self,x):self.x=x
 def load(self,sid):
  if sid!=self.x.session_id:raise KeyError(sid)
  return self.x
def point(lat,lon):
 xyz=geodetic_to_ecef_km(lat,lon,0);q=np.deg2rad([lat,lon]);up=np.array([np.cos(q[0])*np.cos(q[1]),np.cos(q[0])*np.sin(q[1]),np.sin(q[0])])
 return lambda e,n:ReceiverPoint(xyz,up)
def sites(sid,pose):
 # Full-catalogue prediction is bounded to one explicit diagnostic branch here.
 return {'truth_diagnostic':{'latitude_deg':pose['latitude_deg'],'longitude_deg':pose['longitude_deg'],'diagnostic_truth':True}}
def provenance(raw):
 trajectory=reconstruct_persistent_hop_trajectories(project_scanner_candidates(raw),config=PersistentHopTrajectoryConfig(minimum_span_s=3.,minimum_support=6));result={}
 for hypothesis in trajectory.hypotheses:
  for tid in hypothesis.tracklet_ids:
   graph=persistent_hop_tracklet_graph(hypothesis,tid)
   if graph is None:continue
   for o in graph.observations:
    row={'source_group_id':o.source_group_id,'source_sample_start':o.source_sample_start,'source_sample_end':o.source_sample_end,'support_center_utc_ns':o.support_center_utc_ns,'stream_id':o.stream_id}
    old=result.get((tid,o.observation_id))
    if old is not None and old!=row:result[(tid,o.observation_id)]=None
    elif (tid,o.observation_id) not in result:result[(tid,o.observation_id)]=row
 return result
def directions(catalogue,cids,times_ns,lat,lon):
 """Vectorized candidate x observation propagation."""
 lookup={int(x):i for i,x in enumerate(catalogue.satellite_numbers)};idx=[lookup[int(x)] for x in cids]
 times=tuple(map(int,times_ns)); grid=SamplingGrid(times,len(times)//2,max((times[-1]-times[0])/1e9/max(len(times)-1,1),1e-9))
 p=propagate_grid(catalogue,grid,idx);jd,fr=julian_day_from_utc_ns(np.asarray(times,np.int64));gm=greenwich_mean_sidereal_time_rad(jd,fr)
 if not np.all(p.usable):raise ValueError('selected candidate failed SGP4 propagation')
 pos,vel=teme_to_ecef(p.position_teme_km,p.velocity_teme_km_s,gm[None,:]);az,el,_,_=look_angles(pos,vel,geodetic_to_ecef_km(lat,lon,0),ecef_to_enu_matrix(lat,lon))
 return az,el
def associate(prepared,site,source_provenance):
 banks,_=build_prediction_banks(prepared.catalogue,prepared.candidate_indices,prepared.start_utc_ns,prepared.tracks,taus_s=np.array([0.]))
 by_track={}
 for b in RegionalTrackPredictionEvaluator(banks,point(site['latitude_deg'],site['longitude_deg']),taus_s=np.array([0.]))(0,0):
  mask=np.asarray(b.training_mask,bool); residual=np.asarray(b.measured_hz)[None,:]-np.asarray(b.predictions_hz)[:,0,:]
  cfo=residual[:,mask].mean(axis=1); centered=residual-cfo[:,None]; sse=np.sum(centered[:,mask]**2,axis=1)
  vis=np.asarray(b.visible);vis=vis if vis.ndim==1 else vis[:,0]
  for i,cid in enumerate(b.candidate_ids):
   if not vis[i]:continue
   row=(float(sse[i]),int(cid),float(cfo[i]))
   old=by_track.setdefault(b.track_id,{}).get(int(cid));
   if old is None or row<old:by_track[b.track_id][int(cid)]=row
 tracks={t.track_id:t for t in prepared.tracks};rows=[]
 for tid,opts in by_track.items():
  t=tracks[tid]; ranked=sorted(opts.values())[:TOP]
  if not ranked:continue
  logw=np.array([-x[0]/(2*SIGMA**2) for x in ranked]);logw-=np.max(logw);w=np.exp(logw);w/=w.sum()
  train_rms=[float(np.sqrt(x[0]/np.count_nonzero(t.training_mask))) for x in ranked];entropy=float(-np.sum(np.where(w>0,w*np.log(w),0.)))
  times=np.asarray([prepared.start_utc_ns+round(float(x)*1e9) for x in t.times_s],dtype=np.int64);cids=[x[1] for x in ranked]
  az,el=directions(prepared.catalogue,cids,times,site['latitude_deg'],site['longitude_deg'])
  for j,(oid,utc,train) in enumerate(zip(t.observation_ids,times,t.training_mask,strict=True)):
   feature=marginal_direction(az[:,j],el[:,j],logw)
   prov=source_provenance.get((tid,oid));
   if prov is None:continue
   propagation_utc=int(utc);utc=int(prov['support_center_utc_ns'])
   rows.append({'projected_observation_id':oid,'track_id':tid,'observation_utc_ns':int(utc),'propagation_utc_ns':propagation_utc,'training':bool(train),**prov,
    'u_east':feature['east'],'u_north':feature['north'],'u_up':feature['up'],'east_variance':feature['east_variance'],
    'candidate_ids':cids,'candidate_probabilities':w.tolist(),'candidate_training_rms_hz':train_rms,'association_entropy_nats':entropy,'candidate_azimuth_deg':az[:,j].tolist(),'candidate_elevation_deg':el[:,j].tolist()})
 return rows
def main():
 started=time.monotonic();manifest=json.loads((HERE/'evaluation_manifest.json').read_text());inventory={x['session_id']:x for x in json.loads((HERE/'evaluation_inventory.json').read_text())};out=[];excluded=[]
 for item in manifest['sessions']:
  sid=item['pose']['session_id'];cache=HERE/'cache'/f'{sid}.pickle'
  if not inventory.get(sid,{}).get('ready') or not cache.exists():excluded.append({'session_id':sid,'reason':inventory.get(sid,{}).get('reason','cache not ready')});continue
  payload=cache.read_bytes();actual='sha256:'+hashlib.sha256(payload).hexdigest()
  if actual!=inventory[sid]['cache_sha256']:raise ValueError(f'{sid}: cache digest mismatch')
  raw=pickle.loads(payload);p=prepare_adaptive_tle_position_inputs(sid,inputs=CacheStore(raw),archive=TleArchiveReader(Path('/var/lib/leo/tle')));prov=provenance(raw)
  for branch,site in sites(sid,item['pose']['pose_authority']).items():
   values=associate(p,site,prov);out.append({'session_id':sid,'split':item['split'],'branch':branch,'site':site,'input_manifest_sha256':p.input_manifest_sha256,'analysis_manifest_sha256':p.analysis_manifest_sha256,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,'track_count':len(p.tracks),'source_observation_count':sum(len(t.observation_ids) for t in p.tracks),'mapped_row_count':len(values),'unmapped_or_ambiguous_count':sum(len(t.observation_ids) for t in p.tracks)-len(values),'max_propagation_vs_support_center_delta_ns':max(abs(x['propagation_utc_ns']-x['support_center_utc_ns']) for x in values),'rows':values})
  (HERE/'associations.partial.json').write_text(json.dumps({'completed_sessions':[x['session_id'] for x in out],'excluded':excluded,'branches':out},indent=2)+'\n')
  print(sid,len(p.tracks),flush=True)
 result={'protocol':{'association':'full prepared candidate catalogue, tau=0, per-track constant CFO, training-mask SSE only, top3 soft weights, sigma_hz=100','directions':'SGP4 from the same frozen catalogue at each projected observation UTC','join_key':['session_id','source_group_id','source_sample_start','source_sample_end','support_center_utc_ns'],'conditioning':'satellite SSE/soft weights use Doppler training residuals only; cross-receiver reception endpoint is not used to choose identities; upstream detection and track selection remain conditioned on GLRT-gated products','scope':'truth-position diagnostic branch only; independent Sacramento/Reno full-catalogue reruns deferred as outside bounded runtime'},'excluded':excluded,'branches':out,'elapsed_s':time.monotonic()-started}
 (HERE/'associations.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
