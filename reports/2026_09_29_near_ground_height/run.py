import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'2026_09_29_height_sensitivity'))
from height_model import HeightStationary


def distance(a,b):
    a,b=np.radians(a),np.radians(b);d=b-a
    return float(6371008.8*2*np.arcsin(np.sqrt(np.sin(d[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2)))


def main(ds):
    started=time.monotonic()
    helper_path=HERE.parent/'2026_09_29_receiver_holdout/run.py'
    spec=importlib.util.spec_from_file_location('receiver_helper',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    source=HERE.parent/'2026_09_29_scan_budget/manifest.json'
    plan=json.loads(source.read_text())
    unit=next(u for u in plan['sets'] if u['unit']==f'{ds}_n24_0')
    selected_path=source.parent/f'{ds}_n24_0.json'
    prior=json.loads(selected_path.read_text());old=prior['selected'];assert old['qualified']
    terrain=HERE.parent/'2026_09_29_public_elevation/summary.json'
    terrain_data=json.loads(terrain.read_text())
    assert terrain_data['wgs84_antenna_ellipsoidal_height_m'] is None
    paths=[source,selected_path,HERE/'run.py',HERE/'PROTOCOL.md',helper_path,terrain,
           HERE.parent/'2026_09_29_height_sensitivity/height_model.py',
           ROOT/'tools/ds7_baseline_adapter.py',ROOT/'tools/ds7_fast_baseline_adapter.py',
           HERE.parent/'2026_09_29_unassociated_trend/trend_mixture.py',
           HERE.parent/'2026_09_29_frequency_contrast/contrast_position.py']
    inputs=[r['input'] for r in unit['scans']]
    for entry in inputs:
        for artifact in entry['artifacts']:
            p=Path(artifact['path']);assert 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256'];paths.append(p)
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=inputs))
    assert [d['session_id'] for d in docs]==prior['sessions']
    def model(h):
        return helper.TrendMixturePosition(docs,dict(plan['config'],receiver_height_m=h),HeightStationary,.2)
    def visibility(m,x):
        return np.concatenate([m.models[i].prediction(t,[x[0],x[1],x[i+2]])[1] for i,d in enumerate(docs) for t in d['tracks']])
    zero=model(0);x=np.array(old['x']);base=zero.evaluate(x,gradient=False,held=True)
    assert abs(base['score']-old['score'])<1e-7
    baseline_held=sum(r['held_log_score'] for r in base['rows'])
    baseline_coord=list(zero.models[0].coordinates(x[:3]));support=visibility(zero,x)
    reference=[37.849056280893684,-122.48575489722863]
    results=[]
    for h in [20.,40.]:
        m=model(h);initial_changes=int(np.count_nonzero(support!=visibility(m,x)))
        assert initial_changes==0
        fit=helper.fit_model(m,x)
        if fit['qualified']:
            coord=list(m.models[0].coordinates(fit['x'][:3]));scored=m.evaluate(fit['x'],gradient=False,held=True)
            fit.update(estimate_deg=coord,horizontal_shift_m=distance(baseline_coord,coord),reference_distance_m=distance(reference,coord),training_change=fit['score']-base['score'],held_change=sum(r['held_log_score'] for r in scored['rows'])-baseline_held,final_visibility_changes=int(np.count_nonzero(support!=visibility(m,fit['x']))))
        results.append(dict(height_m=h,initial_visibility_changes=initial_changes,fit=fit))
    output=dict(dataset=ds,sessions=prior['sessions'],baseline=old,baseline_reference_distance_m=distance(reference,baseline_coord),baseline_held=baseline_held,results=results,elapsed_seconds=time.monotonic()-started,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/f'{ds}.json').open('x') as out:json.dump(output,out,indent=2,allow_nan=False)
    print(ds,output['elapsed_seconds'],[(r['height_m'],r['fit'].get('horizontal_shift_m'),r['fit']['qualified']) for r in results],flush=True)


if __name__=='__main__':main(sys.argv[1])
