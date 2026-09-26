#!/usr/bin/env python3
"""Summarize cached full-Qin folds without rereading IQ."""
import argparse,csv,json,math
from pathlib import Path
import numpy as np
from leo.analysis.research.pilot_locklet_prototypes import PilotFrameObservation, robust_blockwise_cfo_rate, track_piecewise_locklets

def wrap(x,period): return (x+period/2)%period-period/2
def channel(item): return np.asarray(item['real'])+1j*np.asarray(item['imag'])
def rms(x): return float(np.sqrt(np.mean(np.square(x)))) if len(x) else None

def run(cache,tracker_path,output):
 rows=[]; rx_count=0; visits=0; receiver_dispositions={}
 for path in sorted(cache.glob('visit-*.frame-folds.json')):
  d=json.load(open(path)); visits+=1
  for receiver in d['receivers']:
   receiver_dispositions[(d['split'],receiver['disposition'])]=receiver_dispositions.get((d['split'],receiver['disposition']),0)+1
   if receiver['disposition']!='complete': continue
   rx_count+=1
   for f in receiver['frames']:
    split=f['even_odd_split']; even=split.get('even'); odd=split.get('odd')
    held=None
    if even and odd:
     e=channel(even['channel_vector']);o=channel(odd['channel_vector']);held=float(wrap(np.angle(np.vdot(e,o)),math.pi))
    q=f['all_qin'];rows.append({'visit_index':d['visit_index'],'split':d['split'],'target_index':d['target_index'],'receiver_id':receiver['receiver_id'],'device_counter':f['device_counter'],'time_s':f['elapsed_from_seed_s'],'phase_rad':q['phase_at_reference_rad'],'residual_cfo_hz':q['residual_cfo_hz'],'exact_coherence':q['exact_coherence'],'control_coherence':q['control_coherence'],'margin':q['coherence_margin'],'held_even_odd_phase_rad':held,'training_supported':split['training_supported']})
 held=np.asarray([x['held_even_odd_phase_rad'] for x in rows if x['held_even_odd_phase_rad'] is not None]); margins=np.asarray([x['margin'] for x in rows]); adjacent=[]; forward=[]; robust=[]; actual_locklets=[]; actual_blocks=[];arc_metrics=[]
 groups={}
 for row in rows: groups.setdefault((row['visit_index'],row['receiver_id']),[]).append(row)
 for group in groups.values():
  group.sort(key=lambda x:x['device_counter']); phase=np.unwrap(2*np.asarray([x['phase_rad'] for x in group]))/2; t=np.asarray([x['device_counter'] for x in group],dtype=np.int64); ts=(t-t[0])/10e6
  arc_adj=[];arc_forward=[]
  if len(group)>=3:
   arc_adj=list(wrap(phase[2:]-(2*phase[1:-1]-phase[:-2]),math.pi));adjacent.extend(arc_adj)
   for i in range(3,len(group)): robust.append(float(wrap(phase[i]-(phase[i-1]+np.median(np.diff(phase[max(0,i-6):i]))),math.pi)))
  cut=len(group)//2
  if cut>=3 and len(group)-cut:
   coef=np.polyfit(ts[:cut],phase[:cut],1);arc_forward=list(wrap(phase[cut:]-np.polyval(coef,ts[cut:]),math.pi));forward.extend(arc_forward)
  arc_held=[x['held_even_odd_phase_rad'] for x in group if x['held_even_odd_phase_rad'] is not None]
  arc_metrics.append({'visit_index':group[0]['visit_index'],'receiver_id':group[0]['receiver_id'],'split':group[0]['split'],'frame_count':len(group),'supported_span_ms':float(ts[-1]*1000+1000/750) if len(ts) else 0.0,'held_rms_rad':rms(arc_held),'adjacent_rms_rad':rms(arc_adj),'forward_rms_rad':rms(arc_forward),'median_abs_residual_cfo_hz':float(np.median(np.abs([x['residual_cfo_hz'] for x in group])))})
  observations=[PilotFrameObservation(time_s=float(tt),cfo_hz=float(r['residual_cfo_hz']),cfo_sigma_hz=max(1.0,abs(float(r['residual_cfo_hz']))*.02),support=float(float(r['margin']) > 0.0 and float(r['exact_coherence']) >= .02),phase_modulo_pi_rad=float(wrap(r['phase_rad'],math.pi)),phase_sigma_rad=max(.02,min(.5,.5*(1-float(r['exact_coherence']))))) for tt,r in zip(ts,group,strict=True)]
  if len(observations)>=6:
   lock=track_piecewise_locklets(observations);actual_locklets.append(lock)
   try: actual_blocks.append(robust_blockwise_cfo_rate(observations))
   except ValueError: pass
 tracker=json.load(open(tracker_path)) if tracker_path.exists() else {'processed_visit_count':0,'span_observations':[]}
 spans=tracker.get('span_observations',[]); v3=[x['pnt_v3'] for x in spans if 'pnt_v3'in x]
 v4_path=output/'v4-smoke.json';v4=json.load(open(v4_path)) if v4_path.exists() else {'rows':[]};v4_processed=[x for x in v4['rows'] if x['disposition']=='processed']
 actual_05_14=json.load(open(output/'actual-05-14-smoke.json')) if (output/'actual-05-14-smoke.json').exists() else {'rows':[]}
 actual_05=[x for x in actual_05_14['rows'] if x.get('disposition')=='processed']
 actual_04_exact=[t for x in actual_05 for t in x['method04']['exact']['transitions']]
 actual_04_control=[t for x in actual_05 for t in x['method04']['control']['transitions']]
 actual_14=[y for x in actual_05 for y in x['method14'] if y['status']=='complete']
 actual_08=json.load(open(output/'actual-08-smoke.json')) if (output/'actual-08-smoke.json').exists() else {'rows':[]}
 actual_08_complete=[x for x in actual_08['rows'] if x['status']=='complete']
 methods=[]
 def add(i,name,status,evidence,metric=None): methods.append({'method_id':f'{i:02d}','approach':name,'status':status,'eligible_visits':128,'processed_visits':visits,'acquired_receivers':rx_count,'frame_count':len(rows),'evidence':evidence,'primary_metric':metric})
 add(1,'Integrated CFO boundary bridging','deferred_to_G','D supplies counter-referenced local CFO; boundary transport belongs to G')
 add(2,'Frame-local Qin phase','completed','all 300 Qin symbols/eight tones plus rolled control and even/odd split',rms(held))
 add(3,'Adjacent-frame correlation','completed','constant-increment prediction on cached contiguous frames',rms(adjacent))
 add(4,'Prompt phase versus integrated linear Doppler','bounded_actual_smoke',f'actual 64-symbol prompt phase tested against the integral of the robust degree-one frequency fit on {len(actual_05)} smoke receiver-arcs; exact accepted {sum(x["accepted_continuity"] for x in actual_04_exact)}/{len(actual_04_exact)} transitions versus control {sum(x["accepted_continuity"] for x in actual_04_control)}/{len(actual_04_control)}',rms([x['innovation_cycles'] for x in actual_04_exact]))
 add(5,'Five-state phase feedback','bounded_actual_smoke',f'actual five-state replay phase feedback on/off on {len(actual_05)} smoke receiver-arcs')
 add(6,'Ordinary 2pi long tracking','partial_actual_kernel','actual phase_symmetry_order=1 span checkpoints')
 add(7,'Full Qin phase slope','completed','actual all-300-symbol/eight-tone phase-slope kernel',float(np.median(np.abs([x['residual_cfo_hz'] for x in rows]))) if rows else None)
 add(8,'Offline binary-pi batch fit','bounded_actual_smoke',f'historical channel/delay separation and noncausal doubled-phase polynomial branch fit on {len(actual_08_complete)} smoke receiver-arcs',rms([x['pi_residual_rms_rad'] for x in actual_08_complete]))
 add(9,'Causal modulo-pi filter','partial_actual_kernel','actual phase_symmetry_order=2 span checkpoints')
 add(10,'Five-state modulo-pi PNT','partial_actual_kernel','actual PNT V1/V2/V3 span checkpoints')
 inner_complete=[x for x in spans if x.get('pnt_v2',{}).get('status')=='complete']
 inner_pass=[x for x in inner_complete if x['pnt_v2']['phase_lock_qualified']]
 add(11,'Production multi-window qualification','bounded_actual_gate_outcome',f'actual inner phase gate passed {len(inner_pass)}/{len(inner_complete)} completed bounded spans; an outer production qualification cannot pass when its required inner gate fails, so no outer score is asserted for those failures',len(inner_pass))
 add(12,'Short segments versus long GLRT lines','completed','duration-stratified actual span inventory')
 add(13,'Scanner retune-bounded tracking','completed','all arcs remain within one 120 ms visit; no retune continuation')
 add(14,'Semi-coherent pooling','bounded_actual_smoke',f'actual normalized likelihood curves and even/odd frequency-line fits for {len(actual_14)} smoke duration cases (20/50/100 ms)',float(np.median([x['frequency_split_hz'] for x in actual_14])) if actual_14 else None)
 add(15,'Capture/reset mechanism','completed','capture audit has zero invalid payload rows; resets retained from actual trackers')
 add(16,'Robust jump and phase-gated filters','completed_actual_research_kernel',f'pilot_locklet_prototypes.track_piecewise_locklets on {len(actual_locklets)} arcs; robust_blockwise_cfo_rate on {len(actual_blocks)} arcs',sum(x.accepted_observation_count for x in actual_locklets))
 add(17,'V3 phase-safe tracking','bounded_actual_ablation',f'actual V3 on {len(v3)} 75/120-ms spans; full cached population uses common folds',sum(x['status']=='complete' for x in v3))
 add(18,'V4 seed/control correction','bounded_actual_ablation',f'actual V4 on {len(v4_processed)} smoke receiver-arcs; uncalibrated thresholds preserved',sum(x['result']['phase_lock_qualified_mode_count'] for x in v4_processed))
 output.mkdir(parents=True,exist_ok=True)
 with (output/'method-summary.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=methods[0].keys());w.writeheader();w.writerows(methods)
 with (output/'frame-fold-observations.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
 split_metrics={}
 for split in ('development','evaluation'):
  subset=[x for x in arc_metrics if x['split']==split]
  def med(key):
   values=[x[key] for x in subset if x[key] is not None];return float(np.median(values)) if values else None
  spans=[x['supported_span_ms'] for x in subset]
  split_metrics[split]={'acquired_receiver_arcs':len(subset),'receiver_dispositions':{status:count for (sp,status),count in receiver_dispositions.items() if sp==split},'median_per_arc_held_rms_rad_mod_pi':med('held_rms_rad'),'median_per_arc_adjacent_rms_rad_mod_pi':med('adjacent_rms_rad'),'median_per_arc_forward_rms_rad_mod_pi':med('forward_rms_rad'),'median_per_arc_abs_residual_cfo_hz':med('median_abs_residual_cfo_hz'),'supported_span_ms_median':float(np.median(spans)) if spans else None,'supported_span_ms_max':float(np.max(spans)) if spans else None}
 summary={'schema':'scan-phase-frame-method-summary/v1','processed_visits':visits,'eligible_visits':128,'missing_dense_visits':128-visits,'acquired_receivers':rx_count,'receiver_dispositions':{f'{split}:{status}':count for (split,status),count in receiver_dispositions.items()},'frame_count':len(rows),'exact_margin_positive_fraction':float(np.mean(margins>0)) if len(margins) else None,'even_odd_held_phase_rms_rad_mod_pi':rms(held),'adjacent_prediction_rms_rad_mod_pi':rms(adjacent),'forward_half_prediction_rms_rad_mod_pi':rms(forward),'robust_prediction_rms_rad_mod_pi':rms(robust),'per_receiver_arc_metrics':arc_metrics,'split_metrics':split_metrics,'actual_locklet_arc_count':len(actual_locklets),'actual_locklet_accepted_frames':sum(x.accepted_observation_count for x in actual_locklets),'actual_locklet_rejected_frames':sum(x.rejected_observation_count for x in actual_locklets),'actual_robust_block_fit_count':len(actual_blocks),'actual_tracker_checkpoint_visits':tracker.get('processed_visit_count',0),'methods':methods};(output/'frame-method-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 fig,ax=plt.subplots(1,2,figsize=(11,4),constrained_layout=True);ax[0].hist(margins,bins=60);ax[0].axvline(0,color='k');ax[0].set(title='Full-Qin exact minus rolled control',xlabel='coherence margin',ylabel='frames');ax[1].hist(held,bins=60);ax[1].set(title='Even-trained / odd-held phase',xlabel='phase difference modulo pi (rad)',ylabel='frames');fig.savefig(output/'frame-held-control-overview.png',dpi=160);fig.savefig(output/'frame-held-control-overview.svg')
 eval_groups=[]
 for key,group in groups.items():
  if not group or group[0]['split']!='evaluation': continue
  values=[x['held_even_odd_phase_rad'] for x in group if x['held_even_odd_phase_rad'] is not None]
  if values: eval_groups.append((rms(values),key,sorted(group,key=lambda x:x['device_counter'])))
 eval_groups.sort()
 if eval_groups:
  selected=[('best',eval_groups[0]),('median',eval_groups[len(eval_groups)//2]),('failure',eval_groups[-1])]
  fig,axes=plt.subplots(3,2,figsize=(11,8),constrained_layout=True,sharex=False)
  for row,(label,(score,key,group)) in enumerate(selected):
   t=(np.asarray([x['device_counter'] for x in group],dtype=np.int64)-group[0]['device_counter'])/1e4
   axes[row,0].plot(t,[x['held_even_odd_phase_rad'] for x in group],'.-',ms=2);axes[row,0].axhline(0,color='k',lw=.5);axes[row,0].set(ylabel='phase mod pi (rad)',title=f'{label}: visit {key[0]} rx{key[1]}, RMS={score:.3f}')
   axes[row,1].plot(t,[x['residual_cfo_hz'] for x in group],'.-',ms=2);axes[row,1].set(ylabel='residual CFO (Hz)',title='full-Qin prompt discriminator')
  for axis in axes[-1]: axis.set_xlabel('elapsed device-counter time (ms)')
  fig.savefig(output/'representative-eval-fold-traces.png',dpi=160);fig.savefig(output/'representative-eval-fold-traces.svg')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--tracker',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.cache,a.tracker,a.output)
