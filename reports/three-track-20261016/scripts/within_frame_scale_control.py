import json
from pathlib import Path
import numpy as np
import leo.analysis.starlink.pilot_methods as module
from leo.analysis.starlink.fractional_epoch import fractional_take
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score
fs=2500000;period=fs/750;anchor=500.25;mid=33.5*11;epsilon=.002;carrier=100000.;template=np.asarray(qin_edge_pilot_frame(fs,'lower'));positions=np.arange(50000,dtype=float);frame=np.floor((positions-anchor)/period).astype(int);local=positions-anchor-np.rint(frame*period);q=mid+(local-mid)/(1+epsilon);valid=(frame>=0)&(q>=8)&(q<len(template)-9);samples=np.zeros(50000,complex);samples[valid]=fractional_take(template,q[valid]);samples*=np.exp(2j*np.pi*carrier*positions/fs);original=module.fractional_take;out=[]
try:
 for ppm in [-2000,0,2000]:
  scale=ppm*1e-6
  def take(values,pos,**kwargs):
   frame=np.floor((pos-anchor)/period).astype(int);local=pos-anchor-np.rint(frame*period);return original(values,pos+scale*(local-mid),**kwargs)
  module.fractional_take=take;score,_=continuous_glrt_score(samples,fs,anchor=500,offset=.25,conditioning_cfo_hz=carrier,edge='lower');out.append(dict(ppm=ppm,exact_score=score.exact_score,physical_cfo_hz=score.tracking_cfo_hz/(1+scale)))
finally:module.fractional_take=original
assert max(out,key=lambda r:r['exact_score'])['ppm']==2000,out
assert abs(out[-1]['physical_cfo_hz']-carrier)<25,out
p=Path('/tmp/three-track-investigation/space-track-pipeline-rerun/within_frame_scale_control.json');p.write_text(json.dumps(dict(injected_ppm=2000,injected_cfo_hz=carrier,results=out),indent=2)+'\n');print(json.dumps(out,indent=2))
