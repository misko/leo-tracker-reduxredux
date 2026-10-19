import json
from pathlib import Path
import numpy as np
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.analysis.starlink.acquisition import acquire_symbolwise,ReceiverFrequencyCalibration,SymbolwiseAcquisitionConfig
fs=2500000;template=np.asarray(qin_edge_pilot_frame(fs,'lower'));period=fs/750;result=[]
for delay in [0,100]:
 epoch=500+delay;samples=np.zeros(50000,complex)
 for frame in range(16):
  start=epoch+round(frame*period);end=min(start+len(template),len(samples))
  if start>=len(samples):break
  samples[start:end]+=template[:end-start]
 samples*=np.exp(2j*np.pi*100000*np.arange(len(samples))/fs)
 config=SymbolwiseAcquisitionConfig(residual_cfo_min_hz=80000,residual_cfo_max_hz=120000,coarse_cfo_step_hz=20000,retained_candidate_count=4,candidate_epoch_separation_samples=5,candidate_cfo_separation_hz=10000)
 fit=acquire_symbolwise(samples,fs,ReceiverFrequencyCalibration('synthetic',0,'0'*64),edge='lower',config=config);winner=fit.winner;assert winner is not None
 result.append(dict(injected_delay_samples=delay,injected_epoch_samples=epoch,recovered_epoch_samples=winner.refined_epoch_sample,recovered_cfo_hz=winner.absolute_cfo_hz))
assert result[1]['recovered_epoch_samples']-result[0]['recovered_epoch_samples']==100,result
p=Path('/tmp/three-track-investigation/space-track-pipeline-rerun/frame_epoch_sign_control.json');p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
