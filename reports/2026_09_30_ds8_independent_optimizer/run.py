import hashlib
import importlib.util
import json
import time
from pathlib import Path

from solver import fit_model

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(path):
    return json.loads(path.read_text())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    started=time.monotonic()
    source=REPORTS/'2026_09_30_ds8_validated_timing_refit/result.json'
    original=read(source)
    for name,digest in original['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    old=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new=read(REPORTS/'2026_09_29_rank24_control/plan.json')
    assert old['config']==new['config']
    inputs={}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']:s['input'] for s in scans})
    helper=module('budget',REPORTS/'2026_09_29_scan_budget/run.py').helper
    docs=helper.baseline.load_documents(dict(config=old['config'],inputs=[inputs[s] for s in original['sessions']]))
    assert [d['session_id'] for d in docs]==original['sessions']
    model=helper.TrendMixturePosition(docs,old['config'],helper.baseline.Stationary,.2)
    fit=fit_model(model,original['initial'])
    if fit['qualified']:
        scored=model.evaluate(fit['x'],gradient=False,held=True)
        fit.update(estimate_deg=list(model.models[0].coordinates(fit['x'][:3])),held_score=sum(r['held_log_score'] for r in scored['rows']))
    paths=[source,HERE/'run.py',HERE/'solver.py',HERE/'test_solver.py',HERE/'PROTOCOL.md']
    result=dict(fit=fit,initial=original['initial'],sessions=original['sessions'],elapsed_seconds=time.monotonic()-started,
                hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'result.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in fit.items() if k!='x'},indent=2))


if __name__=='__main__':
    main()
