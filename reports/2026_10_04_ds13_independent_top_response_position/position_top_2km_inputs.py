"""Bounded Scan B replication of the saved Scan A top-response protocol."""
import argparse,json,time,multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
from candidate_guided_refinement import refine
from replay import NAMESPACE,ROOT,digest

OUT=NAMESPACE/'position-top-2km'
SESSION='scan-fw-ffa1cc19d8d7c09f'
SOURCE=OUT/'B-refinement/refined.json'

def worker(task):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
    visit_id,rows,manifest=task
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    try:
        pub=store.inspect(SESSION);assert pub.manifest_sha256==manifest
        fs=int(pub.manifest.receipt.plan.geometry.sample_rate_hz)
        visit,iq=store.read_visit_ci16(pub,visit_id);signals={};results=[]
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
            results.append(dict(row_index=row,probe_key=m['probe_key'],original_hz=m['tracking_cfo_hz'],original_margin=m['fractional_margin'],
                refinement_seconds=time.monotonic()-tic,refinement=r,output_hz=r.get('tracking_cfo_hz',m['tracking_cfo_hz'])))
        return results
    finally:store.close()

def refine_b():
    bundle_path=ROOT.parent/'2026_10_02_ds13_timing_em/scans'/SESSION/'bundle.json'
    bundle=json.loads(bundle_path.read_text());meta=bundle['alias_grouping']['representative_rows']
    frozen=ROOT/'frozen/B-observations.npz'
    with np.load(frozen) as a:canonical=a['canonical_rows'];assert len(canonical)==6602
    grouped={}
    for i in canonical:grouped.setdefault(meta[int(i)]['probe_key'][0],[]).append((int(i),meta[int(i)]))
    SOURCE.parent.mkdir(parents=True,exist_ok=True);assert not SOURCE.exists()
    started=time.monotonic();records=[]
    with ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('fork')) as pool:
        pending={pool.submit(worker,(visit,rows,bundle['provenance']['input_manifest_sha256'])):visit for visit,rows in grouped.items()}
        for index,future in enumerate(as_completed(pending)):
            rows=future.result();records.extend(rows)
            (SOURCE.parent/f'visit-{pending[future]}.json').write_text(json.dumps(rows))
            if index%100==0:print('B refinement',index+1,'/',len(pending),'visits',len(records),'candidates',round(time.monotonic()-started),'s',flush=True)
    assert {r['row_index'] for r in records}==set(canonical)
    SOURCE.write_text(json.dumps(dict(records=records,workers=8,elapsed_s=time.monotonic()-started,
        sources={str(p):digest(p) for p in (bundle_path,frozen,Path(__file__),NAMESPACE/'candidate_guided_refinement.py')},
        input_manifest_sha256=bundle['provenance']['input_manifest_sha256'])))
    print('B complete',len(records),'fallbacks',sum(r['refinement']['status']!='refined' for r in records),flush=True)

def winners(records):
    groups={}
    for r in records:
        key=tuple(r['probe_key']);priority=(r['refinement'].get('margin',r['original_margin']),-r['row_index'])
        if key not in groups or priority>groups[key][0]:groups[key]=(priority,r['row_index'])
    return {v[1] for v in groups.values()}

def calibration():
    import greedy_pool_two_scans as g
    from absolute_timing_solver import AbsoluteCalibration
    from training_bootstrap import training_view
    g.SCAN='B'
    class BCalibration(AbsoluteCalibration):
        def __init__(self):
            super().__init__();r=json.loads(SOURCE.read_text());values={x['row_index']:x['output_hz'] for x in r['records']};keep=winners(r['records'])
            for path,h in r['sources'].items():assert digest(Path(path))==h
            self.d.measured=np.array([values[int(i)] for i in self.d.original_rows])
            mask=np.isin(self.d.original_rows,list(keep));original=self.d.original_rows[mask]
            self.d=training_view(self.d,mask);self.d.original_rows=original
            parts=[]
            for d,models in self.parts:
                d.measured=np.array([values[int(i)] for i in d.original_rows]);m=np.isin(d.original_rows,list(keep));original=d.original_rows[m]
                view=training_view(d,m);view.original_rows=original
                parts.append((view,{arm:(p,c,corr[m]) for arm,(p,c,corr) in models.items()}))
            self.parts=parts;assert len(set(self.d.group))==len(keep)
            self.sources.update({str(SOURCE):digest(SOURCE),str(Path(__file__)):digest(Path(__file__))})
    return BCalibration

def discover():
    import greedy_pool_two_scans as g
    g.OUT=OUT/'B-top';g.FrozenCalibration=calibration();g.OUT.mkdir(exist_ok=True);g.discover()

def solve():
    from greedy_restart_scan import compile_mode,evaluate
    from penalty_replace_search import Search
    pool=json.loads((OUT/'B-top/candidate-pool.json').read_text());cal=calibration()();d=cal.d
    assert pool['original_rows']==d.original_rows.tolist()
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms']['fitted-c']]==[(m['catalog_number'],m['offset_s']) for m in pool['arms']['zero-c']]
    metrics=[]
    for arm in ('fitted-c','zero-c'):
        modes=[compile_mode(m,d.receiver,d.channel) for m in pool['arms'][arm]];r=Search(modes,d.group,d.times).run(3)
        for stage in ('initial','final'):
            for a in r[stage]['assignments']:a['row_index']=int(d.original_rows[a['row_index']])
            r[stage].update(coverage=r[stage]['assigned']/len(d.times),unassigned=len(d.times)-r[stage]['assigned'])
        lookup={int(i):j for j,i in enumerate(d.original_rows)}
        for m in r['final']['selected']:
            raw=pool['arms'][arm][m['mode_index']];aa=[a for a in r['final']['assignments'] if a['catalog_number']==m['catalog_number']]
            ix=np.array([lookup[a['row_index']] for a in aa]);e,v,_=cal.residual(arm,raw['satellite_index'],raw['offset_s'])
            assert np.all(v[ix]) and np.all(abs(e[ix])<=600) and np.allclose(e[ix],[a['residual_hz'] for a in aa],atol=1e-6)
        r.update(arm=arm,scan='B',denominator=len(d.times),source_sha256=digest(OUT/'B-top/candidate-pool.json'),score='assigned - 10 * satellites')
        (OUT/'B-top'/f'{arm}.json').write_text(json.dumps(r,indent=2))
        metrics.append({k:v for k,v in r['final'].items() if k not in ('assignments','selected')})
        print('B',arm,metrics[-1],flush=True)
    (OUT/'B-top/audit.json').write_text(json.dumps(dict(status='passed',metrics=metrics)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['refine','discover','solve']);a=p.parse_args()
    {'refine':refine_b,'discover':discover,'solve':solve}[a.stage]()
