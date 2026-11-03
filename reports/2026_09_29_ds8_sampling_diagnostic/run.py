import hashlib
import importlib.util
import json
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj


def read(path):return json.loads(path.read_text())


def main():
    started=time.monotonic()
    budget=module('budget',HERE.parent/'2026_09_29_scan_budget/run.py');helper=budget.helper
    timing=module('timing_control',HERE.parent/'2026_09_29_disjoint_frozen_association/run.py').timing_fit
    old_plan_path=HERE.parent/'2026_09_29_scan_budget/manifest.json'
    new_plan_path=HERE.parent/'2026_09_29_rank24_control/plan.json'
    old_plan,new_plan=read(old_plan_path),read(new_plan_path)
    assert old_plan['config']==new_plan['config']
    old_unit=next(s for s in old_plan['sets'] if s['unit']=='DS8_n24_0')
    new_unit=next(s for s in new_plan['sets'] if s['dataset']=='DS8')
    plans={'old':old_unit['scans'],'rank':new_unit['scans']}
    paths={'old':HERE.parent/'2026_09_29_scan_budget/DS8_n24_0.json','rank':HERE.parent/'2026_09_29_rank24_control/DS8/result.json'}
    fits={k:read(p) for k,p in paths.items()};inputs={};membership={};inherited={};hashes={}
    for arm,scans in plans.items():
        assert fits[arm]['selected']['qualified']
        assert fits[arm]['sessions']==[s['session_id'] for s in scans]
        for index,row in enumerate(scans):
            sid=row['session_id'];entry=row['input']
            if sid in inputs:
                assert sorted(a['sha256'] for a in inputs[sid]['artifacts'])==sorted(a['sha256'] for a in entry['artifacts'])
            inputs[sid]=entry;membership.setdefault(sid,[]).append(arm)
            inherited.setdefault(sid,[]).append(fits[arm]['selected']['x'][index+2])
            for a in entry['artifacts']:
                p=Path(a['path']);h=hashlib.sha256(p.read_bytes()).hexdigest();assert 'sha256:'+h==a['sha256'];hashes[str(p)]=h
    assert len(inputs)==40
    docs=helper.baseline.load_documents(dict(config=old_plan['config'],inputs=[inputs[s] for s in sorted(inputs)]))
    grid=np.array(old_plan['config']['timing_grid_s']);rows=[]
    folder=HERE/'scans';folder.mkdir(exist_ok=True)
    for d in docs:
        sid=d['session_id'];m=helper.TrendMixturePosition([d],old_plan['config'],helper.baseline.Stationary,.2)
        arms={};posteriors={}
        for arm in ['old','rank']:
            position=np.array(fits[arm]['selected']['x'][:2])
            scores,_=budget.training_scores(m,position,grid)
            guesses=list(dict.fromkeys([float(grid[int(np.argmax(scores))])]+inherited[sid]))
            starts=[dict(timing(m,position,[tau]),initial_tau_s=tau) for tau in guesses]
            qualified=[s for s in starts if s['qualified']]
            selected=max(qualified,key=lambda s:s['score']) if qualified else None
            arms[arm]=dict(starts=starts,selected=selected)
            if selected:
                assert np.array_equal(np.array(selected['x'][:2]),position)
                out=m.evaluate(selected['x'],gradient=False,held=True)
                arms[arm].update(training=out['score'],held=sum(r['held_log_score'] for r in out['rows']))
                posteriors[arm]=out['rows']
        group='shared' if len(membership[sid])==2 else membership[sid][0]+'_only'
        row=dict(session_id=sid,group=group,arms=arms,tracks=len(d['tracks']),qualified=len(posteriors)==2)
        if row['qualified']:
            row.update(training_margin=arms['rank']['training']-arms['old']['training'],held_margin=arms['rank']['held']-arms['old']['held'])
            pairs=list(zip(posteriors['old'],posteriors['rank'],strict=True))
            assert all(a['track_id']==b['track_id'] for a,b in pairs)
            row.update(candidate_changes=sum(int(np.argmax(a['weights_given_signal']))!=int(np.argmax(b['weights_given_signal'])) for a,b in pairs),visible_count_changes=sum(a['visible_candidates']!=b['visible_candidates'] for a,b in pairs))
        with (folder/f'{sid}.json').open('x') as out:json.dump(row,out,indent=2,allow_nan=False)
        rows.append(row)
        print(group,len(rows),row['qualified'],flush=True)
    summaries=[]
    for group in ['shared','old_only','rank_only']:
        subset=[r for r in rows if r['group']==group];valid=[r for r in subset if r['qualified']]
        summaries.append(dict(group=group,total=len(subset),qualified=len(valid),training_margin=sum(r['training_margin'] for r in valid),held_margin=sum(r['held_margin'] for r in valid),rank_training_wins=sum(r['training_margin']>0 for r in valid),rank_held_wins=sum(r['held_margin']>0 for r in valid),candidate_changes=sum(r['candidate_changes'] for r in valid),tracks=sum(r['tracks'] for r in valid),visible_count_changes=sum(r['visible_count_changes'] for r in valid)))
    for p in list(paths.values())+[old_plan_path,new_plan_path,HERE/'run.py',HERE/'PROTOCOL.md',HERE.parent/'2026_09_29_disjoint_frozen_association/run.py',HERE.parent/'2026_09_29_scan_budget/run.py']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'results.json').open('x') as out:json.dump(dict(rows=rows,summary=summaries,hashes=hashes,elapsed_seconds=time.monotonic()-started),out,indent=2,allow_nan=False)
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
