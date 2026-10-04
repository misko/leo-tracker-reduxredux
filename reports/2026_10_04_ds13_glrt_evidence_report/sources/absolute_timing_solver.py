"""Corrected full-scan timing: one absolute shift per satellite in every fold.

Receiver/RF calibration remains frozen and fold-specific. The former common
timing references are NOT added to candidate shifts. Search is +/-20 s about
zero, with unchanged derivative retrieval/refinement and matched RF-arm union.
The penalty-10 greedy/replacement algorithm is unchanged. Posthoc raw coverage,
not independent validation or identity certification.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import greedy_pool_two_scans as g
from penalty_replace_search import Search
from greedy_restart_scan import compile_mode
from replay import ROOT,NAMESPACE,digest

OUT=NAMESPACE/'absolute-timing-penalty10'
BaseCalibration=g.FrozenCalibration

def absolute_parameters(parameters,indices,timing_s):
    if not np.isfinite(timing_s) or abs(timing_s)>20.:raise ValueError('Absolute timing outside +/-20 s')
    trial=np.array(parameters,copy=True);trial[6+np.asarray(indices,int)]=timing_s
    return trial

class AbsoluteCalibration(BaseCalibration):
    def __init__(self):
        super().__init__()
        self.sources[str(Path(__file__))]=digest(Path(__file__))
        self.sources[str(Path(g.__file__))]=digest(Path(g.__file__))

    def predict(self,arm,ids,timing_s):
        from prediction_jacobian import paired_prediction_jacobian
        pp=[];vv=[];rr=[]
        for d,models in self.parts:
            params,unused_fold_reference,correction=models[arm]
            trial=absolute_parameters(params,ids,timing_s)
            rows=np.repeat(np.arange(len(d.times)),len(ids));sats=np.tile(ids,len(d.times))
            p,v,j=paired_prediction_jacobian(d,trial,rows,sats)
            pp.append(p.reshape(len(d.times),-1)+correction[:,None]);vv.append(v.reshape(len(d.times),-1));rr.append(j.tau.reshape(len(d.times),-1))
        return np.concatenate(pp),np.concatenate(vv),np.concatenate(rr)

def discover(scan):
    g.SCAN=scan;g.OUT=OUT/f'scan-{scan}';g.FrozenCalibration=AbsoluteCalibration;g.__doc__=__doc__
    OUT.mkdir(exist_ok=True);g.discover()
    path=g.OUT/'candidate-pool.json';r=json.loads(path.read_text())
    r.update(timing_convention='offset_s is an ABSOLUTE ephemeris evaluation shift; identical in every fold',absolute_timing_bounds_s=[-20.,20.],prior_center_s=0.,prior_sigma_s=1.)
    path.write_text(json.dumps(r))

def solve(scan,arm,passes):
    source=OUT/f'scan-{scan}'/'candidate-pool.json';pool=json.loads(source.read_text())
    for p,h in pool['sources'].items():assert digest(Path(p))==h
    assert 'ABSOLUTE' in pool['timing_convention']
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms']['fitted-c']]==[(m['catalog_number'],m['offset_s']) for m in pool['arms']['zero-c']]
    orig=np.array(pool['original_rows'])
    with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:
        assert len(orig)==len(set(orig)) and set(orig)==set(a['canonical_rows'])
        groups=a['group'][orig];times=a['times_s'][orig];rx=a['receiver'][orig];ch=a['channel'][orig]
    modes=[compile_mode(r,rx,ch) for r in pool['arms'][arm]]
    r=Search(modes,groups,times).run(passes)
    for stage in ('initial','final'):
        for a in r[stage]['assignments']:a['row_index']=int(orig[a['row_index']])
        r[stage]['coverage']=r[stage]['assigned']/len(orig);r[stage]['unassigned']=len(orig)-r[stage]['assigned']
    import penalty_replace_search
    r.update(scope=__doc__,scan=scan,arm=arm,scan_id=pool['scan'],denominator=len(orig),score='assigned_unique_peaks - 10 * selected_unique_satellites',penalty=10,tolerance_hz=600,
        timing_convention=pool['timing_convention'],source_sha256=digest(source),script_sha256=digest(Path(__file__)),selector_sha256=digest(Path(penalty_replace_search.__file__)))
    with (OUT/f'{scan}-{arm}.json').open('x') as f:json.dump(r,f,indent=2)
    print('DONE',scan,arm,{stage:{k:v for k,v in r[stage].items() if k not in ('assignments','selected')} for stage in ('initial','final')},'converged',r['converged'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['discover','solve']);p.add_argument('--scan',choices=['A','B'],required=True);p.add_argument('--arm',choices=['fitted-c','zero-c']);p.add_argument('--passes',type=int,default=3);a=p.parse_args()
    if a.stage=='solve' and a.arm is None:p.error('--arm required for solve')
    discover(a.scan) if a.stage=='discover' else solve(a.scan,a.arm,a.passes)
