import hashlib
import json
import time
from pathlib import Path

from centered import Centered
from run import HERE, REPORTS, module, read


def main():
    started=time.monotonic()
    original=read(HERE/'result.json')
    for name,digest in original['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    old=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new=read(REPORTS/'2026_09_29_rank24_control/plan.json')
    inputs={}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']:s['input'] for s in scans})
    helper=module('budget',REPORTS/'2026_09_29_scan_budget/run.py').helper
    docs=helper.baseline.load_documents(dict(config=old['config'],inputs=[inputs[s] for s in original['sessions']]))
    model=helper.TrendMixturePosition(docs,old['config'],helper.baseline.Stationary,.2)
    shifted=Centered(model,original['initial'])
    fit=helper.fit_model(shifted,original['initial'])
    fit['centered_score']=fit['score']
    fit['score']+=shifted.offset
    replay=model.evaluate(fit['x'],gradient=False)
    assert abs(replay['score']-fit['score'])<1e-7
    if fit['qualified']:
        scored=model.evaluate(fit['x'],gradient=False,held=True)
        fit.update(estimate_deg=list(model.models[0].coordinates(fit['x'][:3])),held_score=sum(t['held_log_score'] for t in scored['rows']))
    paths=[HERE/p for p in ['result.json','centered.py','run_centered.py','CENTERED_PROTOCOL.md','test_centered.py']]
    result=dict(fit=fit,offset=shifted.offset,initial=original['initial'],elapsed_seconds=time.monotonic()-started,
                hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'centered-result.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in fit.items() if k!='x'},indent=2))


if __name__=='__main__':
    main()
