import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(p.read_text())


def main(arm):
    assert arm in ['old','rank'];started=time.monotonic()
    source=HERE.parent/'2026_09_29_ds8_sampling_diagnostic/results.json';prior=read(source)
    for name,h in prior['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    oldpath=HERE.parent/'2026_09_29_scan_budget/manifest.json';newpath=HERE.parent/'2026_09_29_rank24_control/plan.json'
    old,new=read(oldpath),read(newpath);assert old['config']==new['config']
    inputs={}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        for s in scans:inputs[s['session_id']]=s['input']
    rows=sorted(prior['rows'],key=lambda r:r['session_id']);assert len(rows)==40
    spec=importlib.util.spec_from_file_location('budget',HERE.parent/'2026_09_29_scan_budget/run.py')
    budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);helper=budget.helper
    docs=helper.baseline.load_documents(dict(config=old['config'],inputs=[inputs[r['session_id']] for r in rows]))
    m=helper.TrendMixturePosition(docs,old['config'],helper.baseline.Stationary,.2)
    fits=[r['arms'][arm]['selected'] for r in rows];assert all(f['qualified'] for f in fits)
    position=fits[0]['x'][:2];assert all(f['x'][:2]==position for f in fits)
    initial=np.r_[position,[f['x'][2] for f in fits]]
    replay=m.evaluate(initial,gradient=False,held=True)
    assert abs(replay['score']-sum(r['arms'][arm]['training'] for r in rows))<1e-7
    assert abs(sum(t['held_log_score'] for t in replay['rows'])-sum(r['arms'][arm]['held'] for r in rows))<1e-7
    fit=helper.fit_model(m,initial)
    result=dict(start_arm=arm,initial=initial.tolist(),fit=fit,sessions=[r['session_id'] for r in rows],elapsed_seconds=time.monotonic()-started)
    if fit['qualified']:
        scored=m.evaluate(fit['x'],gradient=False,held=True)
        fit.update(estimate_deg=list(m.models[0].coordinates(fit['x'][:3])),held_score=sum(t['held_log_score'] for t in scored['rows']))
        groups=[]
        for group in ['shared','old_only','rank_only']:
            subset=[r for r in rows if r['group']==group];ids={r['session_id'] for r in subset};tracks=[t for t in scored['rows'] if t['session_id'] in ids]
            groups.append(dict(group=group,scans=len(subset),training=sum(t['training_log_score'] for t in tracks),held=sum(t['held_log_score'] for t in tracks),controls={a:dict(training=sum(r['arms'][a]['training'] for r in subset),held=sum(r['arms'][a]['held'] for r in subset)) for a in ['old','rank']}))
        result['groups']=groups
    paths=[source,oldpath,newpath,HERE/'run.py',HERE/'PROTOCOL.md',HERE.parent/'2026_09_29_scan_budget/run.py',HERE.parent/'2026_09_29_receiver_holdout/run.py']
    result['hashes']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with (HERE/f'{arm}.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print(arm,fit['qualified'],fit.get('estimate_deg'),result['elapsed_seconds'],flush=True)


if __name__=='__main__':main(sys.argv[1])
