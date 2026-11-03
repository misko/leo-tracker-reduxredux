"""Bounded free-height fits; no geographic reference scoring."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize
from model import Model,STEPS,fast
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
spec=importlib.util.spec_from_file_location('height_util',HILL/'cross_band_rx_position/run.py')
util=importlib.util.module_from_spec(spec);spec.loader.exec_module(util)
read,write,digest=util.read,util.write,util.digest
BOUNDS=[(-12,12),(-12,12),(-5,5),(-1,1)]
def prepare():
    source=HILL/'height_sensitivity/outcome.json';sources=dict(read(source)['sources']);util.verify(dict(sources=sources))
    base=HILL.parent/'2026_09_30_ds11_single10';original=read(base/'plan.json');scans={};jobs=[]
    for index in (0,16):
        control=read(base/f'runs/{index:02d}_iid.json')['selected'];assert control['qualified']
        doc=fast.load_documents(dict(config=original['config'],inputs=[original['inputs'][index]]))[0]
        x=control['x']+[0.];check=Model(doc,original['config']).evaluate(x)
        assert abs(check['score']-control['score'])<1e-6
        scans[str(index)]=dict(input=original['inputs'][index],control_x=x,control_score=check['score'],control_held=check['held'])
        jobs.extend(dict(index=index,seed=seed) for seed in (x,[0.,0.,0.,0.]))
    for p in (source,base/'plan.json',Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md',HILL/'cross_band_rx_position/run.py'):
        sources[str(p)]=digest(p)
    write(HERE/'plan.json',dict(config=original['config'],scans=scans,jobs=jobs,sources=sources,reference_used=False))
    print(json.dumps(dict(jobs=len(jobs),plan_sha256=digest(HERE/'plan.json'))))
def fit(i):
    start=time.monotonic();p=read(HERE/'plan.json');util.verify(p);job=p['jobs'][i];scan=p['scans'][str(job['index'])]
    doc=fast.load_documents(dict(config=p['config'],inputs=[scan['input']]))[0];m=Model(doc,p['config'])
    def objective(x):
        r=m.evaluate(x);return -r['score'],-r['gradient']
    fit=minimize(objective,job['seed'],jac=True,method='L-BFGS-B',bounds=BOUNDS,
                 options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
    r=m.evaluate(fit.x);fd=[]
    for axis,step in enumerate(STEPS):
        d=np.eye(4)[axis]*step;fd.append((m.evaluate(fit.x+d,False)['score']-m.evaluate(fit.x-d,False)['score'])/(2*step))
    discrepancy=float(np.max(abs(r['gradient']-fd)));maximum=float(np.max(abs(r['gradient'])))
    boundary=any(min(x-lo,hi-x)<.001 for x,(lo,hi) in zip(fit.x,BOUNDS))
    qualified=bool(fit.success and not boundary and np.isfinite(fit.x).all() and np.isfinite(r['score']) and maximum<=.01 and discrepancy<=.02)
    write(HERE/f'runs/{i:02d}.json',dict(job=job,x=fit.x.tolist(),score=r['score'],qualified=qualified,
          boundary=boundary,success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
          gradient_max_abs=maximum,audit_max_abs=discrepancy,elapsed_s=time.monotonic()-start,plan_sha256=digest(HERE/'plan.json')))
def batch():
    p=read(HERE/'plan.json');util.verify(p);(HERE/'runs').mkdir(exist_ok=True)
    def launch(i):
        stem=HERE/f'runs/{i:02d}';start=time.monotonic()
        cmd=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1','timeout','--kill-after=5s','90s',
             'nice','-n','19',util.PYTHON,str(HERE/'run.py'),'fit',str(i)]
        with stem.with_suffix('.log').open('x') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
        write(stem.with_suffix('.receipt.json'),dict(job_index=i,exit_code=r.returncode,wall_s=time.monotonic()-start,plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=i,exit_code=r.returncode)),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(len(p['jobs']))))
def seal():
    p=read(HERE/'plan.json');util.verify(p);attempts=[];selected={}
    for i,job in enumerate(p['jobs']):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt['plan_sha256']==digest(HERE/'plan.json')
        result=read(HERE/f'runs/{i:02d}.json') if receipt['exit_code']==0 else None
        if result:assert result['job']==job and result['plan_sha256']==receipt['plan_sha256']
        attempts.append(dict(job=job,receipt=receipt,result=result))
    for index in p['scans']:
        valid=[a['result'] for a in attempts if str(a['job']['index'])==index and a['result'] and a['result']['qualified']]
        selected[index]=max(valid,key=lambda r:r['score']) if valid else None
    write(HERE/'selections.json',dict(selected=selected,attempts=attempts,reference_used=False,plan_sha256=digest(HERE/'plan.json')))
def assess():
    p=read(HERE/'plan.json');util.verify(p);s=read(HERE/'selections.json');assert s['plan_sha256']==digest(HERE/'plan.json');rows=[]
    for index,scan in p['scans'].items():
        selected=s['selected'][index];row=dict(index=int(index),qualified=selected is not None,height_m=None,held_gain=None)
        if selected:
            doc=fast.load_documents(dict(config=p['config'],inputs=[scan['input']]))[0];r=Model(doc,p['config']).evaluate(selected['x'],False)
            assert abs(r['score']-selected['score'])<1e-6
            row.update(height_m=1000*selected['x'][3],held_gain=r['held']-scan['control_held'],training_gain=r['score']-scan['control_score'])
        rows.append(row)
    outcome=dict(rows=rows,gate_pass=all(r['qualified'] and r['held_gain']>0 for r in rows),reference_used=False,
                 plan_sha256=digest(HERE/'plan.json'),selection_sha256=digest(HERE/'selections.json'))
    write(HERE/'outcome.json',outcome);print(json.dumps(outcome,indent=2))
if __name__=='__main__':
    if sys.argv[1]=='fit':fit(int(sys.argv[2]))
    else:dict(prepare=prepare,batch=batch,seal=seal,assess=assess)[sys.argv[1]]()
