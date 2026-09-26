#!/usr/bin/env python3
"""Bounded actual historical method-05 and method-14 kernels on smoke-eight."""
import argparse,dataclasses,json,math
from dataclasses import replace
from pathlib import Path
import numpy as np
from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.analysis.starlink.phase_doppler import estimate_frame_carrier_observations,fit_constant_rate_phase_doppler
from leo.analysis.starlink.pnt_kalman import CodePhaseObservation,PntKalmanConfig,replay_pnt_kalman
from tools.report_470384_semicoherent_recovery import Branch,FrameLikelihood,fit_likelihood_line,normalized_frequency_curves
RATE=10_000_000;PROBE=200_000;SYMBOLS64=np.arange(2,66);SYMBOLS300=np.arange(2,302)
def primary(p):
 x=[c for c in p['candidates'] if c['passed_fractional_margin_gate']];return min(x,key=lambda c:(-c['fractional_margin'],c['candidate_rank'])) if x else None
def plain(x):
 if dataclasses.is_dataclass(x):return {f.name:plain(getattr(x,f.name)) for f in dataclasses.fields(x) if f.repr}
 if isinstance(x,np.ndarray):return x.tolist()
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,tuple):return [plain(y) for y in x]
 if isinstance(x,float) and not math.isfinite(x):return None
 return x
def run(cache,dense,selection_path,output):
 selection=json.loads(selection_path.read_text());smoke=set(selection['smoke8_visit_indices']);rows=[]
 for path in sorted(dense.glob('visit-*.corrected-dense.json')):
  d=json.loads(path.read_text());p=d['product'];v=p['visit_index']
  if v not in smoke:continue
  iq=np.load(cache/f'visit-{v:04d}'/'iq_ci16.npy',mmap_mode='r')
  for rx in (0,1):
   probes=sorted((x for x in p['probes'] if x['receiver_id']==rx),key=lambda x:x['probe_index']);seeded=next(((x,primary(x)) for x in probes if primary(x) is not None),None)
   if not seeded:rows.append({'visit_index':v,'receiver_id':rx,'disposition':'not_acquired'});continue
   probe,c=seeded;base=probe['probe_index']*PROBE;available=len(iq)-base;count=min(1_000_000,available);raw=iq[base:base+count,rx];samples=np.ascontiguousarray((raw[:,0].astype(float)+1j*raw[:,1].astype(float))/32768.0);epoch=c['integer_epoch_sample'];cfo=c['fractional_tracking_cfo_hz']
   w64=_conditioned_correlation_workspace(samples,RATE,epoch,cfo,edge=StarlinkEdge.UPPER,selected_symbols=SYMBOLS64);e64=w64.select(SYMBOLS64);n64=w64.select(SYMBOLS64,control=True);obs=estimate_frame_carrier_observations(e64.values,n64.values,e64.normalized_power,n64.normalized_power,e64.times_s,nco_frequency_hz=cfo,absolute_time_offset_s=(int(p['valid_start_counter'])+base)/RATE,container_id=(v,rx));initial_rate=float(np.polyfit([x.time_s for x in obs],[x.doppler_hz for x in obs],1)[0]) if len(obs)>2 else 0.0;code=(CodePhaseObservation(time_s=obs[0].time_s,code_phase_s=((base+epoch)/RATE)%(1/750),container_id=(v,rx)),);cfg=PntKalmanConfig();on=replay_pnt_kalman(obs,code,initial_doppler_rate_hz_s=initial_rate,config=cfg);off=replay_pnt_kalman(obs,code,initial_doppler_rate_hz_s=initial_rate,config=replace(cfg,apply_phase_updates=False))
   integrated_exact=fit_constant_rate_phase_doppler(obs,phase_channel='exact',initial_doppler_rate_hz_s=initial_rate)
   integrated_control=fit_constant_rate_phase_doppler(obs,phase_channel='control',initial_doppler_rate_hz_s=initial_rate)
   method04={'exact':plain(integrated_exact),'control':plain(integrated_control),'exact_accepted_transition_count':sum(x.accepted_continuity for x in integrated_exact.transitions),'control_accepted_transition_count':sum(x.accepted_continuity for x in integrated_control.transitions),'exact_innovation_rms_cycles':float(np.sqrt(np.mean([x.innovation_cycles**2 for x in integrated_exact.transitions]))),'control_innovation_rms_cycles':float(np.sqrt(np.mean([x.innovation_cycles**2 for x in integrated_control.transitions])))}
   method05={'observation_count':len(obs),'phase_on':plain(on),'phase_off':plain(off)}
   w=_conditioned_correlation_workspace(samples,RATE,epoch,cfo,edge=StarlinkEdge.UPPER,selected_symbols=SYMBOLS300);exact=w.select(SYMBOLS300);control=w.select(SYMBOLS300,control=True);even=np.arange(0,len(SYMBOLS300),2);odd=np.arange(1,len(SYMBOLS300),2);curves=[]
   for source in (exact,control):
    for idx in (even,odd):curves.append(normalized_frequency_curves(source.values,source.times_s,idx))
   frames=tuple(FrameLikelihood(time_s=float(np.mean(exact.times_s[i])),nco_cfo_hz=cfo,even_exact_power=curves[0][0][i],even_exact_ceiling=float(curves[0][1][i]),even_control_power=curves[2][0][i],even_control_ceiling=float(curves[2][1][i]),odd_exact_power=curves[1][0][i],odd_exact_ceiling=float(curves[1][1][i]),odd_control_power=curves[3][0][i],odd_control_ceiling=float(curves[3][1][i])) for i in range(len(exact.values)))
   sem=[];branch=Branch(index=0,label=f'{v}-{rx}',start_s=0,end_s=count/RATE,reference_time_s=0,coefficients_hz=(0.0,cfo))
   for ms in (20,50,100):
    if count/RATE < ms/1000:
     sem.append({'duration_ms':ms,'status':'insufficient_remaining_span','actual_support_ms':count/RATE*1000});continue
    chosen=tuple(x for x in frames if x.time_s<=ms/1000)
    if len(chosen)<3:sem.append({'duration_ms':ms,'status':'insufficient'});continue
    try:
     et=fit_likelihood_line(chosen,branch=branch,split='even');od=fit_likelihood_line(chosen,branch=branch,split='odd');sem.append({'duration_ms':ms,'status':'complete','even':plain(et),'odd':plain(od),'frequency_split_hz':abs(et.frequency_at_reference_hz-od.frequency_at_reference_hz),'slope_split_hz_s':abs(et.slope_hz_s-od.slope_hz_s)})
    except Exception as exc:sem.append({'duration_ms':ms,'status':'error','reason':str(exc)})
   rows.append({'visit_index':v,'receiver_id':rx,'disposition':'processed','start_probe_index':probe['probe_index'],'method04':method04,'method05':method05,'method14':sem})
 output.mkdir(parents=True,exist_ok=True);(output/'actual-05-14-smoke.json').write_text(json.dumps({'schema':'scan-phase-actual-05-14-smoke/v1','rows':rows},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--dense',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.cache,a.dense,a.selection,a.output)
