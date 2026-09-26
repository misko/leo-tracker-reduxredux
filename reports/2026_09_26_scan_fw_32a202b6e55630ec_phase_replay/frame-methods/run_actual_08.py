#!/usr/bin/env python3
"""Bounded offline binary-pi batch fit using the historical phase-slope kernels."""
import argparse,json,math
from pathlib import Path
import numpy as np
from leo.analysis.starlink import StarlinkEdge
from tools.report_edge_pilot_phase_slope_figures import _fit_wrapped_polynomial,_separate_channel_delay_and_phase,_weighted_stack_efficiency

def vec(x): return np.asarray(x['real'])+1j*np.asarray(x['imag'])
def run(folds,selection,out):
 smoke=set(json.loads(selection.read_text())['smoke8_visit_indices']); rows=[]
 for p in sorted(folds.glob('visit-*.frame-folds.json')):
  d=json.loads(p.read_text()); v=d['visit_index']
  if v not in smoke: continue
  for r in d['receivers']:
   fs=[f for f in r['frames'] if f['even_odd_split']['status']=='complete' and f['even_odd_split']['training_supported']]
   if len(fs)<4: rows.append({'visit_index':v,'receiver_id':r['receiver_id'],'status':'insufficient','frame_count':len(fs)}); continue
   t=np.asarray([f['elapsed_from_seed_s'] for f in fs]); w=np.asarray([max(0.,f['all_qin']['coherence_margin']) for f in fs]);
   z=np.asarray([(vec(f['even_odd_split']['even']['channel_vector'])+vec(f['even_odd_split']['odd']['channel_vector']))/2 for f in fs])
   _,phase,similarity,corrected=_separate_channel_delay_and_phase(z,w,sample_rate_hz=10_000_000.,edge=StarlinkEdge.UPPER)
   doubled=np.angle(np.exp(2j*phase)); model,residual=_fit_wrapped_polynomial(t-np.average(t,weights=w),doubled,w,degree=min(3,len(fs)-1))
   binary=np.rint((phase-.5*model)/math.pi).astype(int); aligned=corrected*np.exp(-.5j*model[:,None])*((-1.)**binary)[:,None]
   rows.append({'visit_index':v,'receiver_id':r['receiver_id'],'status':'complete','frame_count':len(fs),'pi_residual_rms_rad':float(np.sqrt(np.average((.5*residual)**2,weights=w))),'binary_pi_one_count':int(np.count_nonzero(binary&1)),'stack_efficiency':_weighted_stack_efficiency(aligned,w),'median_similarity':float(np.median(similarity))})
 out.write_text(json.dumps({'schema':'scan-phase-actual-08-smoke/v1','rows':rows},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--folds',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.folds,a.selection,a.output)
