"""Bounded frequency-refinement comparison with per-case sealed selections."""
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


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


previous_model=load_module('coexistence_previous_model',PREVIOUS/'model.py')
sys.modules['model']=previous_model
try:
    previous=load_module('coexistence_previous_run',PREVIOUS/'run.py')
finally:
    sys.modules['model']=model


def prepare():
    plan=previous.read(PREVIOUS/'plan.json');outcome=previous.read(PREVIOUS/'outcome.json')
    sources={}
    for artifact in (plan,outcome):
        for path,h in artifact['sources'].items():
            assert previous.digest(path)==h,path
            sources[path]=h
    files=[PREVIOUS/'plan.json',PREVIOUS/'outcome.json',PREVIOUS/'verification.json',
           Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md']
    sources.update({str(p):previous.digest(p) for p in files})
    previous.write(HERE/'plan.json',dict(schema='ds11-common-probe-joint-frequency/v1',
                                        rows=plan['rows'],sources=sources,reference_used=False,position_fits=0))


def worker():
    plan=previous.read(HERE/'plan.json');old=previous.read(PREVIOUS/'outcome.json')
    for path,h in plan['sources'].items():assert previous.digest(path)==h,path
    for row in plan['rows']:
        stem=f"{row['ordinal']:02d}"
        previous.write(HERE/'rows'/f'{stem}.active.json',dict(status='active'))
        try:
            old_result=old['rows'][f'pair-{stem}']
            assert old_result['status']=='ok'
            assert previous.digest(old_result['excerpt_path'])==old_result['excerpt_sha256']
            iq=np.load(old_result['excerpt_path'],allow_pickle=False)
            families,training,held=previous.matrices(row)
            parts=[families['a'],families['b']];n=len(training)
            times=np.arange(n)/5_000_000;times-=np.mean(times[training])
            samples=iq[:n,0].astype(float)+1j*iq[:n,1]
            train_parts=[p[training] for p in parts]
            separate=[model.single_frequency(p,times[training],samples[training]) for p in train_parts]
            separate_delta=[r['delta_khz'] for r in separate]
            starts,selected=model.joint_fits(train_parts,times[training],samples[training],separate_delta)
            selection=dict(ordinal=row['ordinal'],separate=separate,starts=starts,selected=selected,
                           held_used=False,plan_sha256=previous.digest(HERE/'plan.json'))
            previous.write(HERE/'rows'/f'{stem}.selection.json',selection)
            scores=dict(cached=model.held_score(parts,times,samples,training,held,[0.,0.]),
                        separate=model.held_score(parts,times,samples,training,held,separate_delta))
            assert abs(scores['cached']-old_result['scores']['joint']['held_nmse'])<1e-12
            if selected:scores['joint']=model.held_score(parts,times,samples,training,held,selected['delta_khz'])
            usable=bool(selected and all(r['refinement_success'] and not r['boundary'] for r in separate))
            result=dict(status='ok',ordinal=row['ordinal'],usable=usable,scores=scores,
                        selection_path=str(HERE/'rows'/f'{stem}.selection.json'),
                        selection_sha256=previous.digest(HERE/'rows'/f'{stem}.selection.json'))
        except Exception as error:result=dict(status='failed',reason=f'{type(error).__name__}: {error}')
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
        rows.append(previous.read(path) if path.exists() else dict(ordinal=i,
                    status='failed' if (HERE/'rows'/f'{i:02d}.active.json').exists() else 'not_attempted'))
    valid=[r for r in rows if r['status']=='ok' and r['usable']]
    gains=[r['scores']['separate']-r['scores']['joint'] for r in valid]
    wins=sum(g>0 for g in gains);median=float(np.median(gains)) if gains else None
    files=[HERE/'plan.json',HERE/'receipt.json']+sorted((HERE/'rows').glob('*.json'))
    output=dict(schema='ds11-common-probe-joint-frequency-outcome/v1',rows=rows,usable_cases=len(valid),
                wins= wins,median_gain=median,advancement_passed=bool(len(valid)==6 and wins>=5 and median>0),
                position_fits=0,sources={str(p):previous.digest(p) for p in files})
    previous.write(HERE/'outcome.json',output)
    print(json.dumps({k:v for k,v in output.items() if k!='sources'},indent=2))


if __name__=='__main__':
    {'prepare':prepare,'worker':worker,'batch':batch}[sys.argv[1]]()
