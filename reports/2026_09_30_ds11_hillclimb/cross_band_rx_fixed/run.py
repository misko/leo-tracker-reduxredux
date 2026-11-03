"""Three receiver allocations at frozen training positions, without refits."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import ds7_fast_baseline_adapter as fast
spec = importlib.util.spec_from_file_location('drift_measurement',HILL/'cross_band_rx_drift/run.py')
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)


def differential(track1, track0, fit):
    a,b = track1,track0
    ai = {v:i for i,v in enumerate(a['visits']) if a['visits'].count(v)==1}
    bi = {v:i for i,v in enumerate(b['visits']) if b['visits'].count(v)==1}
    train = []
    for v in sorted(ai.keys() & bi.keys()):
        i,j = ai[v],bi[v]
        if not (a['mask'][i] and b['mask'][j]) or abs(a['times_s'][i]-b['times_s'][j])>1e-4:
            continue
        train.append(((a['times_s'][i]+b['times_s'][j])/2,
                      drift.audit.wrap((a['y'][i]-b['y'][j])*a['rf_hz']/11.2e9)))
    assert len(train)>=6
    train = np.array(train)
    result = []
    for track in (a,b):
        constant,predicted = drift.predict(train[:,0],train[:,1],np.asarray(track['times_s']),fit)
        result.append((predicted-constant)*11.2e9/track['rf_hz'])
    return result


def allocate(receiver, delta, alpha):
    return -alpha*delta if receiver==1 else (1-alpha)*delta


def scores(document, config, x, changes):
    geometry = fast.Stationary(document,config)
    arms = {name:dict(train=0.,held=0.,map=[]) for name in ('baseline','rx1_fixed','symmetric','rx0_fixed')}
    for track in document['tracks']:
        prediction,visible = geometry.prediction(track,x)
        for name in arms:
            y = track['y']+changes.get(name,{}).get(track['track_id'],0.)
            train,joint,audits,_ = fast.profile(y[None,:]-prediction,track['mask'])
            assert all(a['converged'] for a in audits)
            train = np.where(visible,train,-np.inf)
            joint = np.where(visible,joint,-np.inf)
            normal = logsumexp(train)
            arms[name]['train'] += float(normal-np.log(track['catalogue_size']))
            arms[name]['held'] += float(logsumexp(joint)-normal)
            arms[name]['map'].append(int(np.argmax(train)))
    return arms


def main():
    screen_path = HILL/'cross_band_rx_drift/outcome.json'
    confirmation_path = HILL/'cross_band_rx_drift_confirmation/outcome.json'
    screen = json.loads(screen_path.read_text())
    confirmation = json.loads(confirmation_path.read_text())
    assert screen['summary']['gate_pass'] and confirmation['summary']['gate_pass']
    sources = {**screen['sources'],**confirmation['sources']}
    for name,expected in sources.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected
    plan_path = HILL.parent/'2026_09_30_ds11_single10/plan.json'
    plan = json.loads(plan_path.read_text())
    rows = []
    extra = [screen_path,confirmation_path,Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md',
             ROOT/'tools/ds7_fast_baseline_adapter.py',ROOT/'tools/ds7_baseline_adapter.py']
    for index in range(0,32,4):
        entry = plan['inputs'][index]
        for artifact in entry['artifacts']:
            path = Path(artifact['path'])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256'].removeprefix('sha256:')
            extra.append(path)
        document = fast.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
        tracks = {t['track_id']:t for t in document['tracks']}
        fit_path = HILL.parent/f'2026_09_30_ds11_single10/runs/{index:02d}_iid.json'
        extra.append(fit_path)
        original = json.loads(fit_path.read_text())['selected']
        assert original['qualified']
        pairs = [r for r in screen['rows'] if r['scan_index']==index]
        counts = Counter(t for r in pairs for t in r['tracks'])
        changes = {name:{} for name in ('rx1_fixed','symmetric','rx0_fixed')}
        excluded = []
        corrections = []
        for pair in pairs:
            if any(counts[t]>1 for t in pair['tracks']):
                excluded.append(pair['tracks'])
                continue
            a,b = (tracks[t] for t in pair['tracks'])
            assert a['receiver_id']==1 and b['receiver_id']==0
            da,db = differential(a,b,pair['fit'])
            for name,alpha in (('rx1_fixed',0.),('symmetric',.5),('rx0_fixed',1.)):
                changes[name][a['track_id']] = allocate(1,da,alpha)
                changes[name][b['track_id']] = allocate(0,db,alpha)
            corrections.append(dict(tracks=pair['tracks'],canonical_delta_rx1=da.tolist(),canonical_delta_rx0=db.tolist()))
        arms = scores(document,plan['config'],np.array(original['x']),changes)
        replay_error = arms['baseline']['train']-original['score']
        assert abs(replay_error)<1e-6
        for name,arm in arms.items():
            arm['held_gain'] = arm['held']-arms['baseline']['held']
            arm['map_changes'] = sum(a!=b for a,b in zip(arm['map'],arms['baseline']['map']))
        rows.append(dict(index=index,arms=arms,baseline_replay_error=replay_error,
                         excluded_conflicting_pairs=excluded,corrections=corrections))
    summary = {}
    for name in ('rx1_fixed','symmetric','rx0_fixed'):
        gains = [r['arms'][name]['held_gain'] for r in rows]
        summary[name] = dict(wins=sum(g>0 for g in gains),total_gain=float(sum(gains)),
                             median_gain=float(np.median(gains)),
                             gate_pass=bool(sum(g>0 for g in gains)>=5 and sum(gains)>0 and np.median(gains)>0))
    for path in extra:
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    output = dict(summary=summary,rows=rows,sources=sources,position_fits=0,reference_used=False)
    (HERE/'outcome.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
