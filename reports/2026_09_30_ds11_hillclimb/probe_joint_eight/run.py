"""Eight-frame frequency refinement on six previously frozen common probes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import model

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'probe_coexistence'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result
    spec.loader.exec_module(result)
    return result


old_model=load('eight_coexistence_model',PREVIOUS/'model.py')
sys.modules['model']=old_model
try:previous=load('eight_coexistence_run',PREVIOUS/'run.py')
finally:sys.modules['model']=model


def blocks_for(row,iq):
    blocks=[]
    for frame in range(8):
        shifted=dict(row,candidates=[dict(c,integer_epoch_sample=c['integer_epoch_sample']+frame*5e6/750)
                                     for c in row['candidates']])
        families,training,held=previous.matrices(shifted)
        assert sum(training)>=512 and sum(held)>=256
        n=len(training);assert n<=len(iq)
        take=training|held
        times=np.arange(n)/5e6;times-=np.mean(times[training])
        blocks.append(dict(parts=[families[a][take] for a in ('a','b')],times=times[take],
                           samples=(iq[:n,0].astype(float)+1j*iq[:n,1])[take],
                           training=training[take],held=held[take]))
    return blocks


def prepare():
    plan=previous.read(PREVIOUS/'plan.json');outcome=previous.read(PREVIOUS/'outcome.json')
    sources={}
    for artifact in (plan,outcome):
        for path,h in artifact['sources'].items():
            assert previous.digest(path)==h,path
            sources[path]=h
    files=[PREVIOUS/'plan.json',PREVIOUS/'outcome.json',PREVIOUS/'verification.json',
           Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md',
           HERE.parent/'probe_joint_frequency/model.py']
    sources.update({str(p):previous.digest(p) for p in files})
    previous.write(HERE/'plan.json',dict(schema='ds11-eight-frame-joint-frequency/v1',rows=plan['rows'],
                                        frames=8,reference_used=False,position_fits=0,sources=sources))


def worker():
    plan=previous.read(HERE/'plan.json');old=previous.read(PREVIOUS/'outcome.json')
    for path,h in plan['sources'].items():assert previous.digest(path)==h,path
    for row in plan['rows']:
        stem=f"{row['ordinal']:02d}"
        previous.write(HERE/'rows'/f'{stem}.active.json',dict(status='active'))
        try:
            saved=old['rows'][f'pair-{stem}'];assert saved['status']=='ok'
            assert previous.digest(saved['excerpt_path'])==saved['excerpt_sha256']
            iq=np.load(saved['excerpt_path'],allow_pickle=False);blocks=blocks_for(row,iq)
            fitting=[dict(parts=[p[b['training']] for p in b['parts']],times=b['times'][b['training']],
                          samples=b['samples'][b['training']]) for b in blocks]
            separate=[model.separate_fit(fitting,k) for k in range(2)]
            delta=[s['delta_khz'] for s in separate]
            starts,selected=model.fit_joint(fitting,delta)
            selection=dict(ordinal=row['ordinal'],separate=separate,starts=starts,selected=selected,
                           held_used=False,plan_sha256=previous.digest(HERE/'plan.json'))
            selection_path=HERE/'rows'/f'{stem}.selection.json';previous.write(selection_path,selection)
            scores=dict(cached=model.held_score(blocks,[0.,0.]),separate=model.held_score(blocks,delta))
            assert abs(scores['cached']['frame_nmse'][0]-saved['scores']['joint']['held_nmse'])<1e-12
            if selected:scores['joint']=model.held_score(blocks,selected['delta_khz'])
            result=dict(status='ok',ordinal=row['ordinal'],scores=scores,frames=len(blocks),
                        usable=bool(selected and all(s['refinement_success'] and not s['boundary'] for s in separate)),
                        training_counts=[int(sum(b['training'])) for b in blocks],held_counts=[int(sum(b['held'])) for b in blocks],
                        selection_path=str(selection_path),selection_sha256=previous.digest(selection_path))
        except Exception as error:result=dict(status='failed',ordinal=row['ordinal'],reason=f'{type(error).__name__}: {error}')
        previous.write(HERE/'rows'/f'{stem}.json',result)


def batch():
    (HERE/'rows').mkdir()
    command=['timeout','--kill-after=5s','120s','nice','-n','19',sys.executable,str(Path(__file__)),'worker']
    start=time.monotonic()
    with (HERE/'worker.log').open('x') as log:done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    previous.write(HERE/'receipt.json',dict(exit_code=done.returncode,elapsed_s=time.monotonic()-start,
                                           command=command,plan_sha256=previous.digest(HERE/'plan.json')))
    rows=[]
    for i in range(6):
        path=HERE/'rows'/f'{i:02d}.json'
        rows.append(previous.read(path) if path.exists() else dict(ordinal=i,status='failed' if (HERE/'rows'/f'{i:02d}.active.json').exists() else 'not_attempted'))
    valid=[r for r in rows if r['status']=='ok' and r['usable']]
    comparisons={}
    for arm in ('cached','separate'):
        gains=[r['scores'][arm]['nmse']-r['scores']['joint']['nmse'] for r in valid]
        comparisons[arm]=dict(wins=sum(g>0 for g in gains),mean_gain=float(np.mean(gains)) if gains else None,
                             median_gain=float(np.median(gains)) if gains else None)
    passed=len(valid)==6 and all(c['wins']>=5 and c['mean_gain']>0 and c['median_gain']>0 for c in comparisons.values())
    files=[HERE/'plan.json',HERE/'receipt.json']+sorted((HERE/'rows').glob('*.json'))
    output=dict(schema='ds11-eight-frame-joint-frequency-outcome/v1',rows=rows,usable_cases=len(valid),
                comparisons=comparisons,advancement_passed=passed,position_fits=0,
                sources={str(p):previous.digest(p) for p in files})
    previous.write(HERE/'outcome.json',output)
    print(json.dumps(dict(usable_cases=len(valid),comparisons=comparisons,advancement_passed=passed,
                         statuses=[r['status'] for r in rows]),indent=2))


if __name__=='__main__':
    {'prepare':prepare,'worker':worker,'batch':batch}[sys.argv[1]]()
