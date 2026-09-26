#!/usr/bin/env python3
"""Extract each acquired full-Qin frame once for downstream model replay."""

import argparse, dataclasses, hashlib, json, math
from pathlib import Path
import numpy as np
from leo.analysis.qam.pilot import analyze_pilot_phase_slope, estimate_edge_pilot_frame_complex_split

RATE=10_000_000; PROBE=200_000; FRAME_CONTENT=round(302*RATE*4.4e-6)

def primary(probe):
    rows=[x for x in probe['candidates'] if x['passed_fractional_margin_gate']]
    return min(rows,key=lambda x:(-x['fractional_margin'],x['candidate_rank'])) if rows else None

def plain(x):
    if dataclasses.is_dataclass(x): return {f.name:plain(getattr(x,f.name)) for f in dataclasses.fields(x)}
    if isinstance(x,np.ndarray):
        return {'real':x.real.tolist(),'imag':x.imag.tolist()} if np.iscomplexobj(x) else x.tolist()
    if isinstance(x,np.generic): return x.item()
    if isinstance(x,complex): return {'real':x.real,'imag':x.imag}
    if isinstance(x,tuple): return [plain(y) for y in x]
    if isinstance(x,float) and not math.isfinite(x): return None
    return x

def run(cache,dense,selection_path,output):
    selection=json.loads(selection_path.read_text()); selected={x['visit_index']:x for x in selection['visits']}; output.mkdir(parents=True,exist_ok=True)
    inventory=[]
    for path in sorted(dense.glob('visit-*.corrected-dense.json')):
        document=json.loads(path.read_text()); product=document['product']; visit=product['visit_index']
        if visit not in selected: continue
        source_sha='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest(); out=output/f'visit-{visit:04d}.frame-folds.json'
        if out.exists():
            old=json.loads(out.read_text())
            if old.get('schema')=='scan-phase-frame-fold-cache/v2' and old.get('dense_acquisition_sha256')==source_sha: inventory.append({'visit_index':visit,'path':out.name,'frame_count':old['frame_count']}); continue
        iq=np.load(cache/f'visit-{visit:04d}'/'iq_ci16.npy',mmap_mode='r'); valid=np.load(cache/f'visit-{visit:04d}'/'valid_mask.npy',mmap_mode='r'); receivers=[]; frame_total=0
        for rx in (0,1):
            probes=sorted((p for p in product['probes'] if p['receiver_id']==rx),key=lambda p:p['probe_index']); seeded=next(((p,primary(p)) for p in probes if primary(p) is not None),None)
            if seeded is None: receivers.append({'receiver_id':rx,'disposition':'not_acquired','frames':[]}); continue
            probe,candidate=seeded; base=probe['probe_index']*PROBE; count=len(iq)-base
            if not np.all(valid[base:,rx]): receivers.append({'receiver_id':rx,'disposition':'invalid_source','frames':[]}); continue
            raw=iq[base:,rx]; samples=np.ascontiguousarray(raw[:,0].astype(np.float32)+1j*raw[:,1].astype(np.float32)); epoch=candidate['integer_epoch_sample']; cfo=candidate['fractional_tracking_cfo_hz']; frac=candidate['fractional_epoch_offset_samples']
            slope=analyze_pilot_phase_slope(samples,RATE,epoch_sample=epoch,absolute_cfo_hz=cfo,edge='upper',fractional_epoch_offset_samples=frac)
            frames=[]
            for frame in slope.frames:
                start=frame.frame_start_sample
                if start<1 or start+FRAME_CONTENT+1>len(samples): continue
                split=estimate_edge_pilot_frame_complex_split(samples[start-1:start+FRAME_CONTENT+1],RATE,frame_start_sample=base+start,acquisition_absolute_cfo_hz=cfo,edge='upper')
                frames.append({'local_frame_start_sample':start,'visit_frame_start_sample':base+start,'device_counter':selected[visit]['valid_start_counter']+base+start,'elapsed_from_seed_s':start/RATE,'all_qin':plain(frame),'even_odd_split':plain(split)})
            frame_total+=len(frames); receivers.append({'receiver_id':rx,'disposition':'complete','start_probe_index':probe['probe_index'],'start_sample':base,'seed_epoch_sample':epoch,'fractional_epoch_offset_samples':frac,'tracking_absolute_cfo_hz':cfo,'frames':frames})
        body={'schema':'scan-phase-frame-fold-cache/v2','input_manifest_sha256':selection['input_manifest_sha256'],'dense_acquisition_sha256':source_sha,'visit_index':visit,'split':selected[visit]['split'],'target_index':selected[visit]['target_index'],'frame_count':frame_total,'fractional_note':'all-Qin extraction applies acquired fractional timing; even/odd split is the historical integer-frame guarded estimator and is retained as a timing-sensitivity lane','receivers':receivers}; out.write_text(json.dumps(body,indent=2)+'\n'); inventory.append({'visit_index':visit,'path':out.name,'frame_count':frame_total})
    (output/'frame-fold-index.json').write_text(json.dumps({'schema':'scan-phase-frame-fold-index/v1','input_manifest_sha256':selection['input_manifest_sha256'],'eligible_visit_count':128,'processed_visit_count':len(inventory),'visits':inventory},indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--dense',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.cache,a.dense,a.selection,a.output)
