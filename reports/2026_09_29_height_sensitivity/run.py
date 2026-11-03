import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np
from height_model import HeightStationary

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def distance(a,b):
    a,b=np.radians(a),np.radians(b)
    d=b-a
    return float(6371008.8*2*np.arcsin(np.sqrt(np.sin(d[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2)))


def main(ds):
    started=time.monotonic()
    spec=importlib.util.spec_from_file_location('receiver_helper',HERE.parent/'2026_09_29_receiver_holdout/run.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    source=HERE.parent/'2026_09_29_source_consistent_n8/manifest.json'
    plan=json.loads(source.read_text());items=[r for r in plan['scans'] if r['real_dataset']==ds]
    selected_path=HERE.parent/f'2026_09_29_time_balanced_scans/grid_{ds}_balanced_0.json'
    old=json.loads(selected_path.read_text())['selected'];assert old['qualified']
    paths=[source,selected_path,HERE/'run.py',HERE/'height_model.py',HERE/'PROTOCOL.md',ROOT/'tools/ds7_baseline_adapter.py',HERE.parent/'2026_09_29_receiver_holdout/run.py',HERE.parent/'2026_09_29_unassociated_trend/trend_mixture.py']
    for item in items:
        for artifact in item['input']['artifacts']:
            p=Path(artifact['path']);assert 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256'];paths.append(p)
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=[r['input'] for r in items]))
    def model(h):
        return helper.TrendMixturePosition(docs,dict(plan['config'],receiver_height_m=h),HeightStationary,.2)
    zero=model(0);x=np.array(old['x']);base=zero.evaluate(x,gradient=False,held=True)
    assert abs(base['score']-old['score'])<1e-7
    baseline_held=sum(r['held_log_score'] for r in base['rows'])
    baseline_coord=list(zero.models[0].coordinates(x[:3]))
    reference=[37.849056280893684,-122.48575489722863]
    results=[]
    for h in [100.,300.]:
        m=model(h)
        for di,doc in enumerate(docs):
            local=[x[0],x[1],x[di+2]]
            for track in doc['tracks']:
                assert np.array_equal(zero.models[di].prediction(track,local)[1],m.models[di].prediction(track,local)[1])
        fit=helper.fit_model(m,x)
        if fit['qualified']:
            coord=list(m.models[0].coordinates(fit['x'][:3]));scored=m.evaluate(fit['x'],gradient=False,held=True)
            fit.update(estimate_deg=coord,horizontal_shift_m=distance(baseline_coord,coord),reference_distance_m=distance(reference,coord),training_change=fit['score']-base['score'],held_change=sum(r['held_log_score'] for r in scored['rows'])-baseline_held)
        results.append(dict(height_m=h,fit=fit))
    output=dict(dataset=ds,baseline=old,baseline_reference_distance_m=distance(reference,baseline_coord),baseline_held=baseline_held,results=results,elapsed_seconds=time.monotonic()-started,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/f'{ds}.json').open('x') as out:json.dump(output,out,indent=2,allow_nan=False)
    print(ds,output['elapsed_seconds'],[(r['height_m'],r['fit'].get('horizontal_shift_m'),r['fit']['qualified']) for r in results],flush=True)


if __name__=='__main__':main(sys.argv[1])
