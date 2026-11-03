"""Joint DS8 refit from independently validated timing modes."""
import hashlib
import importlib.util
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    started = time.monotonic()
    rank_path = REPORTS/'2026_09_29_ds8_union40/rank.json'
    scalar_path = REPORTS/'2026_09_30_ds8_timing_modes/scalar-results.json'
    profile_path = REPORTS/'2026_09_30_ds8_timing_modes/results.json'
    corrected_path = REPORTS/'2026_09_29_ds8_union_timing/refit_old.json'
    rank, scalar, profiles, corrected = [read(p) for p in [rank_path,scalar_path,profile_path,corrected_path]]
    hashes = {}
    for result in [rank,scalar,profiles,corrected,read(REPORTS/'2026_09_29_ds8_sampling_diagnostic/results.json')]:
        for name,digest in result['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            hashes[name]=digest
    assert rank['fit']['qualified'] and corrected['fit']['qualified']
    initial=list(rank['fit']['x'])
    rows=[r for r in scalar['rows'] if r['arm']=='rank']
    assert len(rows)==3 and all(r['selected']['qualified'] for r in rows)
    for r in rows:
        assert r['selected']['x'][:2]==initial[:2]
        initial[rank['sessions'].index(r['session_id'])+2]=r['selected']['x'][2]
    old=read(REPORTS/'2026_09_29_scan_budget/manifest.json')
    new=read(REPORTS/'2026_09_29_rank24_control/plan.json')
    assert old['config']==new['config']
    inputs={}
    for scans in [next(s for s in old['sets'] if s['unit']=='DS8_n24_0')['scans'],next(s for s in new['sets'] if s['dataset']=='DS8')['scans']]:
        inputs.update({s['session_id']:s['input'] for s in scans})
    helper=module('budget',REPORTS/'2026_09_29_scan_budget/run.py').helper
    docs=helper.baseline.load_documents(dict(config=old['config'],inputs=[inputs[s] for s in rank['sessions']]))
    assert [d['session_id'] for d in docs]==rank['sessions']
    model=helper.TrendMixturePosition(docs,old['config'],helper.baseline.Stationary,.2)
    replay=model.evaluate(initial,gradient=False,held=True)
    training_audit=abs(replay['score']-rank['fit']['score']-sum(r['training_gain'] for r in rows))
    held_audit=abs(sum(t['held_log_score'] for t in replay['rows'])-rank['fit']['held_score']-sum(r['held_gain'] for r in rows))
    assert max(training_audit,held_audit)<1e-7
    fit=helper.fit_model(model,initial)
    if fit['qualified']:
        scored=model.evaluate(fit['x'],gradient=False,held=True)
        fit.update(estimate_deg=list(model.models[0].coordinates(fit['x'][:3])),held_score=sum(t['held_log_score'] for t in scored['rows']))
    for p in [rank_path,scalar_path,profile_path,corrected_path,HERE/'run.py',HERE/'PROTOCOL.md']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(initial=initial,fit=fit,sessions=rank['sessions'],training_replay_error=training_audit,
                held_replay_error=held_audit,hashes=hashes,elapsed_seconds=time.monotonic()-started)
    with (HERE/'result.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in fit.items() if k!='x'},indent=2))


if __name__=='__main__':
    main()
