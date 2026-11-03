import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scaled_model import Scaled,helper

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
SOURCE=REPORTS/'2026_09_29_ds10_geographic'


def read(path):return json.loads(path.read_text())


def prepare():
    pairs_path=REPORTS/'2026_09_30_rx_scale_common_transfer/results.json'
    prior=read(pairs_path)
    for name,digest in prior['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    logs=defaultdict(list);receivers={}
    for pair in prior['pairs']:
        if pair['dataset']!='DS10':continue
        for rx in [0,1]:
            fit=prior['summary'][f'rx{rx}']['fits']
            assert all(f['qualified'] for f in fit.values())
            a,b=fit['paired_scale']['params'];constant=fit['constant']['params'][0]
            key=(pair['session_id'],pair[f'track{rx}'])
            logs[key].append(a+b*np.log(pair['feature'])-constant)
            receivers[key]=rx
    track_logs={key:float(np.median(values)) for key,values in logs.items()}
    controls={rx:float(np.median([v for key,v in track_logs.items() if receivers[key]==rx])) for rx in [0,1]}
    weights=[dict(session_id=key[0],track_id=key[1],receiver=receivers[key],
                  variable=float(np.exp(value)),constant=float(np.exp(controls[receivers[key]]))) for key,value in sorted(track_logs.items())]
    dsplan=read(SOURCE/'plan.json');baseline=read(SOURCE/'fits/N24_h0/result.json')
    hashes={}
    for obj in [dsplan,baseline]:
        for name,digest in obj['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            hashes[name]=digest
    assert baseline['selected']['qualified'] and baseline['sessions']==dsplan['panels']['N24']
    rows={r['session_id']:r for r in dsplan['captures']}
    inputs=[read(SOURCE/'exports'/rows[s]['unit_id']/'validated.json')['input'] for s in baseline['sessions']]
    for p in [pairs_path,SOURCE/'plan.json',SOURCE/'fits/N24_h0/result.json',HERE/'run.py',HERE/'scaled_model.py',HERE/'PROTOCOL.md',HERE/'test_scaled.py']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    plan=dict(weights=weights,inputs=inputs,config=dsplan['config'],baseline=baseline['selected'],sessions=baseline['sessions'],hashes=hashes)
    with (HERE/'plan.json').open('x') as out:json.dump(plan,out,indent=2,allow_nan=False)
    print('Supported tracks',len(weights),'ratios',min(w['variable'] for w in weights),max(w['variable'] for w in weights),'controls',controls)


def main(arm):
    if arm=='prepare':return prepare()
    assert arm in ['constant','variable']
    started=time.monotonic();plan=read(HERE/'plan.json')
    for name,digest in plan['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=plan['inputs']))
    assert [d['session_id'] for d in docs]==plan['sessions']
    original=helper.TrendMixturePosition(docs,plan['config'],helper.baseline.Stationary,.2)
    initial=plan['baseline']['x']
    replay=original.evaluate(initial,held=True)
    unity=Scaled(docs,plan['config'],{}).evaluate(initial,held=True)
    assert abs(replay['score']-plan['baseline']['score'])<1e-7
    assert replay['score']==unity['score'] and replay['rows']==unity['rows']
    np.testing.assert_array_equal(replay['gradient'],unity['gradient'])
    ratios={(w['session_id'],w['track_id']):w[arm] for w in plan['weights']}
    keys={(d['session_id'],t['track_id']) for d in docs for t in d['tracks']}
    assert set(ratios)<=keys
    model=Scaled(docs,plan['config'],ratios)
    fit=helper.fit_model(model,initial)
    if fit['qualified']:
        scored=model.evaluate(fit['x'],gradient=False,held=True)
        raw=original.evaluate(fit['x'],gradient=False,held=True)
        fit.update(estimate_deg=list(model.models[0].coordinates(fit['x'][:3])),held_score=sum(r['held_log_score'] for r in scored['rows']),
                   original_model_training=raw['score'],original_model_held=sum(r['held_log_score'] for r in raw['rows']))
    result=dict(arm=arm,fit=fit,tracks=len(keys),supported=len(ratios),elapsed_seconds=time.monotonic()-started,
                hashes={str(HERE/'plan.json'):hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()})
    with (HERE/f'{arm}.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print(arm,json.dumps({k:v for k,v in fit.items() if k!='x'}),flush=True)


if __name__=='__main__':main(sys.argv[1])
