#!/usr/bin/env python3
"""Bounded actual V4 acquisition/tracking on the sealed smoke-eight visits."""
import argparse,dataclasses,hashlib,json,math
from pathlib import Path
import numpy as np
from leo.analysis.starlink.seeded_acquisition import KnownPilotModeSeed, SeededPilotAcquisitionConfig
from leo.analysis.qam.pilot_pnt_kalman_v4 import analyze_contiguous_pilot_pnt_kalman_v4, PilotPntKalmanConfigV4
RATE=10_000_000;PROBE=200_000;COUNT=800_000
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
 s=json.loads(selection_path.read_text()); smoke=set(s['smoke8_visit_indices']); output.mkdir(parents=True,exist_ok=True); rows=[]
 for path in sorted(dense.glob('visit-*.corrected-dense.json')):
  d=json.loads(path.read_text());p=d['product'];v=p['visit_index']
  if v not in smoke:continue
  iq=np.load(cache/f'visit-{v:04d}'/'iq_ci16.npy',mmap_mode='r')
  for rx in (0,1):
   probes=sorted((x for x in p['probes'] if x['receiver_id']==rx),key=lambda x:x['probe_index']);seeded=next(((x,primary(x)) for x in probes if primary(x) is not None),None)
   if not seeded:rows.append({'visit_index':v,'receiver_id':rx,'disposition':'not_acquired'});continue
   probe,c=seeded;base=probe['probe_index']*PROBE
   if base+COUNT>len(iq):rows.append({'visit_index':v,'receiver_id':rx,'disposition':'insufficient_80ms'});continue
   raw=iq[base:base+COUNT,rx];samples=np.ascontiguousarray(raw[:,0].astype(np.float32)+1j*raw[:,1].astype(np.float32)); provenance=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest();seed=KnownPilotModeSeed(nominal_epoch_sample=c['integer_epoch_sample'],nominal_absolute_cfo_hz=c['fractional_tracking_cfo_hz'],branch_id=f'visit-{v}-rx-{rx}-probe-{probe["probe_index"]}',provenance_sha256=provenance);config=PilotPntKalmanConfigV4(acquisition_config=SeededPilotAcquisitionConfig(maximum_sample_count=COUNT));result=analyze_contiguous_pilot_pnt_kalman_v4(samples,RATE,seed=seed,edge='upper',config=config);rows.append({'visit_index':v,'receiver_id':rx,'disposition':'processed','start_probe_index':probe['probe_index'],'configuration':plain(config),'result':plain(result)})
 (output/'v4-smoke.json').write_text(json.dumps({'schema':'scan-phase-v4-smoke/v1','input_manifest_sha256':s['input_manifest_sha256'],'eligible_smoke_visits':8,'rows':rows},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--dense',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.cache,a.dense,a.selection,a.output)
