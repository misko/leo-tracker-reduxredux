"""Correct raw-CFO alias representation on the frozen v1 comparison design."""
import hashlib
import json
from pathlib import Path
import time
import unittest
import numpy as np
from circular import wrap,intercept

HERE=Path(__file__).resolve().parent;OLD=HERE.parent;REPORTS=HERE.parents[2]
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
INVENTORY=REPORTS/'2026_10_17_dsx01_iteration6/frame_phase_inventory'
PERIOD=1/4.4e-6
def read(p):return json.loads(Path(p).read_text())
def digest(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def plain(v):
    if isinstance(v,dict):return {k:plain(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [plain(x) for x in v]
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    return v
def save(p,v):
    with Path(p).open('x') as stream:json.dump(plain(v),stream,indent=2,allow_nan=False);stream.write('\n')


def run():
    begun=time.monotonic()
    paths=[HERE/'circular.py',HERE/'test_circular.py',HERE/'run.py',OLD/'manifest.json',OLD/'results.json',OLD/'points.json',
        DATA/'context-observations.jsonl',INVENTORY/'observations.jsonl']
    save(HERE/'protocol.json',dict(reason='Correct known circular227272.727Hz CFO representation; v1rawoutputs/source unchanged',
        fixed_design='Reuseexact49eligiblegroups442observations234TRAIN208heldpoints, phasefits andx_centered fromv1; no regroup/reselect/newphasefit',
        primary='Fixedsign0constantcontrol,+unit,−unit. PredictionHz=TRAINintercept+sign*actualRF*x_centered. x_centered=dphase/Fs minusTRAINmean.',
        intercept='ForTRAIN(y−physicalprediction), enumerateall sortedaliascuts, means, circularSSE; retainglobalminimum deterministictie. Atmost12TRAIN/group.',
        scoring='PrincipalwrappedheldresidualHz dividedbyactualRF forppm. No heldCFO ininterceptorphasefit; no learnedbeta.',
        null='Same32rngseed5301withinsegmentheldCFOpermutations, identicalgroups/masks, TRAINintercepts fixed; reportbothsignsnotchosenwinner',
        physical_limit='NumericalphasebranchguardandCFO-selectedcohort unchanged; no universalclock/identity/geometryclaim',
        maximum_seconds=120,source_sha256={str(p):digest(p) for p in paths}))
    import test_circular
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_circular))
    if not tests.wasSuccessful():raise AssertionError('Circular component tests failed')
    for item in read(OLD/'manifest.json')['files']:assert digest(OLD/item['path'])==item['sha256']
    rows=read(OLD/'points.json');old=read(OLD/'results.json')
    frozen={r['observation_id']:r for s in (DATA/'context-observations.jsonl').read_text().splitlines() if (r:=json.loads(s))}
    groups=[];data=[]
    for group in sorted({r['group'] for r in rows}):
        points=[r for r in rows if r['group']==group];o=old['groups'][group]
        y=np.array([frozen[p['observation_id']]['measured_cfo_hz'] for p in points]);rf=np.array([frozen[p['observation_id']]['actual_rf_hz'] for p in points])
        assert len(np.unique(rf))==1
        train=np.array([not p['held'] for p in points]);held=~train;assert train.sum()<=12
        physical=rf*np.array([p['x_centered'] for p in points]);fits={};predictions={}
        for name,sign in [('baseline',0.),('plus',1.),('minus',-1.)]:
            fit=intercept((y-sign*physical)[train],PERIOD);fits[name]=fit;predictions[name]=fit['offset']+sign*physical
        metric=lambda prediction:float(np.sqrt(np.mean((wrap(y[held]-prediction[held],PERIOD)/rf[held])**2)))*1e6
        row=dict(group=group,source_id=o['source_id'],receiver=o['receiver'],channel=o['channel'],observations=len(y),
            train_points=int(train.sum()),held_points=int(held.sum()),phase_degree=o['degree'],phase_train_rms_samples=o['phase_train_rms_samples'],
            phase_held_rms_samples=o['phase_held_rms_samples'],intercepts=fits,held_rms_ppm={name:metric(p) for name,p in predictions.items()})
        groups.append(row);data.append(dict(row=row,y=y,rf=rf,train=train,held=held,predictions=predictions))
    assert len(data)==49 and sum(d['row']['observations'] for d in data)==442 and sum(d['row']['held_points'] for d in data)==208
    def aggregate(items):
        if not items:return None
        def rms(name,ys=None):
            residuals=[wrap((d['y'][d['held']] if ys is None else y)-d['predictions'][name][d['held']],PERIOD)/d['rf'][d['held']]
                for d,y in zip(items,([None]*len(items) if ys is None else ys))]
            return float(np.sqrt(np.mean(np.concatenate(residuals)**2)))*1e6
        actual={name:rms(name) for name in ['baseline','plus','minus']};rng=np.random.default_rng(5301);null={name:[] for name in ['plus','minus']}
        for _ in range(32):
            shuffled=[rng.permutation(d['y'][d['held']]) for d in items]
            for name in null:null[name].append(rms(name,shuffled))
        return dict(groups=len(items),observations=sum(d['row']['observations'] for d in items),held_points=sum(d['row']['held_points'] for d in items),
            held_rms_ppm=actual,null_held_rms_ppm=null,null_lower_tail={name:(1+sum(v<=actual[name] for v in values))/33 for name,values in null.items()})
    strata=[]
    for s in old['strata']:
        items=[d for d in data if all(d['row'][k]==s[k] for k in ['source_id','receiver','channel'])]
        strata.append({**{k:s[k] for k in ['source_id','receiver','channel']},'summary':aggregate(items)})
    result=dict(original_observations=693,eligible_observations=442,excluded_short_observations=251,groups=groups,strata=strata,
        all_eligible=aggregate(data),quadratic_only=aggregate([d for d in data if d['row']['phase_degree']==2]),
        component_tests=tests.testsRun,intercept_fits=147,maximum_train_points=max(int(d['train'].sum()) for d in data),
        total_enumerated_alias_cuts=sum(f['enumerated_cuts'] for g in groups for f in g['intercepts'].values()),
        phase_refits=0,orbit_or_localization_fit_calls=0,learned_beta_fits=0,elapsed_seconds=time.monotonic()-begun,
        v1_manifest_sha256=digest(OLD/'manifest.json'),protocol_sha256=digest(HERE/'protocol.json'),
        interpretation='Circularrepresentationfix onidenticalfrozendesign; bothsignsreported. No physicalclock/identity/positionclaim.')
    save(HERE/'results.json',result)
    print(json.dumps(plain(dict(all_eligible=result['all_eligible'],quadratic_only=result['quadratic_only'],elapsed_seconds=result['elapsed_seconds']))),flush=True)


if __name__=='__main__':run()
