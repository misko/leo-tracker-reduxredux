"""Refine all 7382 canonical passing scan-A hypotheses; no orbit input."""
import json,time,hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
from candidate_guided_refinement import refine
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score

B=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
OUT=B/'full-scan-A-refinement'
ROOT=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports')
BUNDLE=ROOT/'2026_10_02_ds13_timing_em/scans/scan-fw-911c4e5db9243281/bundle.json'
FROZEN=ROOT/'2026_10_03_ds13_coverage_goal/frozen/A-observations.npz'
SESSION='scan-fw-911c4e5db9243281'

def worker(task):
    visit_id,rows,manifest=task
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    try:
        pub=store.inspect(SESSION);assert pub.manifest_sha256==manifest
        fs=int(pub.manifest.receipt.plan.geometry.sample_rate_hz)
        visit,iq=store.read_visit_ci16(pub,visit_id);signals={};result=[]
        for row,m in rows:
            _,rx,probe=m['probe_key'];assert probe==0
            if rx not in signals:
                block=iq[:fs//50,rx,:]
                signals[rx]=(block[:,0].astype(float)+1j*block[:,1].astype(float))/32768.
            def score(f,e):
                integer=int(round(e));s=conditioned_glrt64_score(signals[rx],fs,epoch_sample=integer,
                    fractional_epoch_offset_samples=e-integer,acquired_cfo_hz=float(f),edge=visit.event.target.edge,glrt_size=4096)
                return dict(tracking_cfo_hz=s.tracking_cfo_hz,margin=s.margin,exact=s.exact_score,control=s.control_score)
            tic=time.monotonic();r=refine(score,m['tracking_cfo_hz'],m['integer_epoch_sample']+m['fractional_epoch_offset_samples'])
            result.append(dict(row_index=row,probe_key=m['probe_key'],original_hz=m['tracking_cfo_hz'],original_margin=m['fractional_margin'],refinement_seconds=time.monotonic()-tic,refinement=r,
                output_hz=r['tracking_cfo_hz'] if r['status']=='refined' else m['tracking_cfo_hz']))
        return result
    finally:store.close()

def main():
    OUT.mkdir(exist_ok=True);bundle=json.loads(BUNDLE.read_text());meta=bundle['alias_grouping']['representative_rows']
    with np.load(FROZEN) as a:canonical=a['canonical_rows'];assert len(canonical)==7382
    grouped={}
    for row in canonical:
        m=meta[int(row)];grouped.setdefault(m['probe_key'][0],[]).append((int(row),m))
    manifest=bundle['provenance']['input_manifest_sha256'];started=time.monotonic();records=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        pending={}
        for visit,rows in grouped.items():
            path=OUT/f'visit-{visit}.json'
            if path.exists():records.extend(json.loads(path.read_text()))
            else:pending[pool.submit(worker,(visit,rows,manifest))]=path
        done=0
        for future in as_completed(pending):
            rr=future.result();pending[future].write_text(json.dumps(rr));records.extend(rr);done+=1
            if done%50==0:print('visits',done,'candidates',len(records),'seconds',round(time.monotonic()-started),flush=True)
    assert len(records)==len(canonical) and {r['row_index'] for r in records}==set(canonical)
    result=dict(scope=__doc__,records=records,elapsed_s=time.monotonic()-started,workers=8,input_manifest_sha256=manifest,
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BUNDLE,FROZEN,Path(__file__),B/'candidate_guided_refinement.py')},
        policy='Same bounded 3-iteration refinement as targeted experiment. Failed local searches retain original measurement; no merging or denominator changes.')
    (OUT/'refined.json').write_text(json.dumps(result))
    print('COMPLETE',len(records),'failed',sum(r['refinement']['status']!='refined' for r in records),'wall',result['elapsed_s'],flush=True)

if __name__=='__main__':main()
