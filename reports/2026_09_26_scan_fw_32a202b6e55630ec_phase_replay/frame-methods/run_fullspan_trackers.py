#!/usr/bin/env python3
"""Run the four seeded tracker kernels once on each receiver's full remaining dwell."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from leo.analysis.qam.tracking import PilotPhaseDopplerTrackingConfig,analyze_contiguous_pilot_phase_doppler_tracking
from leo.analysis.qam.pilot_pnt_kalman import PilotPntKalmanConfig,PilotPntKalmanConfigV2,analyze_contiguous_pilot_pnt_kalman,analyze_contiguous_pilot_pnt_kalman_v2
from run_frame_methods import primary_candidate,summarize_frames,summarize_pnt
RATE=10_000_000;PROBE=200_000

def run(cache,dense,selection_path,output,limit):
 selection=json.loads(selection_path.read_text());selected={x['visit_index']:x for x in selection['visits']}; files=[p for p in sorted(dense.glob('visit-*.corrected-dense.json')) if int(p.name[6:12]) in selected]
 if limit: files=files[:limit]
 output.mkdir(parents=True,exist_ok=True); code_sha='sha256:'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest(); started=time.monotonic();rows=[]
 for path in files:
  d=json.loads(path.read_text());p=d['product'];v=p['visit_index'];source_sha='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest();ck=output/f'visit-{v:04d}.fullspan.json'
  if ck.exists():
   prior=json.loads(ck.read_text())
   if prior.get('code_sha256')==code_sha and prior.get('dense_acquisition_sha256')==source_sha:rows.extend(prior['rows']);continue
  iq=np.load(cache/f'visit-{v:04d}'/'iq_ci16.npy',mmap_mode='r');valid=np.load(cache/f'visit-{v:04d}'/'valid_mask.npy',mmap_mode='r');local=[]
  for rx in (0,1):
   probes=sorted((x for x in p['probes'] if x['receiver_id']==rx),key=lambda x:x['probe_index']);seeded=next(((x,primary_candidate(x)) for x in probes if primary_candidate(x) is not None),None)
   if seeded is None:local.append({'visit_index':v,'split':selected[v]['split'],'receiver_id':rx,'disposition':'not_acquired'});continue
   probe,c=seeded;base=probe['probe_index']*PROBE;count=len(iq)-base
   if count<=0 or not np.all(valid[base:,rx]):local.append({'visit_index':v,'split':selected[v]['split'],'receiver_id':rx,'disposition':'invalid_source_support'});continue
   raw=iq[base:,rx];samples=np.ascontiguousarray(raw[:,0].astype(np.float32)+1j*raw[:,1].astype(np.float32));epoch=int(c['integer_epoch_sample']);cfo=float(c['fractional_tracking_cfo_hz']);frac=float(c['fractional_epoch_offset_samples']);t=time.monotonic()
   ordinary=analyze_contiguous_pilot_phase_doppler_tracking(samples,RATE,epoch_sample=epoch,initial_absolute_cfo_hz=cfo,edge='upper',config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=1));modulo=analyze_contiguous_pilot_phase_doppler_tracking(samples,RATE,epoch_sample=epoch,initial_absolute_cfo_hz=cfo,edge='upper',config=PilotPhaseDopplerTrackingConfig(phase_symmetry_order=2));v1=analyze_contiguous_pilot_pnt_kalman(samples,RATE,epoch_sample=epoch,initial_absolute_cfo_hz=cfo,edge='upper',initial_fractional_epoch_offset_samples=frac,config=PilotPntKalmanConfig());v2=analyze_contiguous_pilot_pnt_kalman_v2(samples,RATE,epoch_sample=epoch,initial_absolute_cfo_hz=cfo,edge='upper',initial_fractional_epoch_offset_samples=frac,config=PilotPntKalmanConfigV2())
   local.append({'visit_index':v,'split':selected[v]['split'],'target_index':p['target_index'],'receiver_id':rx,'disposition':'processed','start_probe_index':probe['probe_index'],'actual_support_ms':count/RATE*1000,'seed_available_after_ms':probe['probe_index']*20+20,'kernel_runtime_seconds':time.monotonic()-t,'ordinary_2pi':{**summarize_frames(ordinary),'phase_reset_count':ordinary.phase_reset_count,'phase_update_count':ordinary.phase_update_count},'causal_modulo_pi':{**summarize_frames(modulo),'phase_reset_count':modulo.phase_reset_count,'phase_update_count':modulo.phase_update_count,'ambiguity_transitions':modulo.phase_ambiguity_transition_count},'pnt_v1':summarize_pnt(v1),'pnt_v2':summarize_pnt(v2)})
  ck.write_text(json.dumps({'schema':'scan-phase-fullspan-trackers/v1','code_sha256':code_sha,'dense_acquisition_sha256':source_sha,'rows':local},indent=2)+'\n');rows.extend(local)
 body={'schema':'scan-phase-fullspan-trackers/v1','code_sha256':code_sha,'processed_visit_count':len(files),'eligible_visit_count':128,'runtime_seconds':time.monotonic()-started,'rows':rows};(output/'fullspan-trackers.json').write_text(json.dumps(body,indent=2)+'\n')
if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('--cache',type=Path,required=True);q.add_argument('--dense',type=Path,required=True);q.add_argument('--selection',type=Path,required=True);q.add_argument('--output',type=Path,required=True);q.add_argument('--limit',type=int);a=q.parse_args();run(a.cache,a.dense,a.selection,a.output,a.limit)
