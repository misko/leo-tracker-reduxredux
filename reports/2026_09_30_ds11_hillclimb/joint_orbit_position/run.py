"""Bounded geographic pilot with frozen shared candidate/revision priors."""
import concurrent.futures
import importlib.util
from pathlib import Path
import subprocess
import sys
import time
import json
import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
sys.path.insert(0,str(HILL/'joint_orbit_uncertainty'))
from model import JointOrbit
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
benchmark=module('orbit_context',HILL/'joint_orbit_uncertainty/run.py')
util=module('orbit_position_util',HILL/'cross_band_rx_position/run.py')
read,write,digest=util.read,util.write,util.digest
ARMS=('zero','orbit','linear')

def select(attempts,index,arm):
    valid=[a['result']['endpoint'] for a in attempts if a['job']['index']==index and a['job']['arm']==arm
           and a['result'] and a['receipt']['exit_code']==0 and a['result']['endpoint']['qualified']]
    return max(valid,key=lambda e:e['score']) if valid else None

def gate(rows):
    return bool(rows) and all(all(r['errors_m'][a] is not None for a in ARMS)
        and all(r['errors_m']['orbit']<r['errors_m'][a] for a in ('iid','zero','linear')) for r in rows)

def prepare():
    prediction_path=HILL/'joint_orbit_prediction/outcome.json';prediction=read(prediction_path)
    assert prediction['gate_pass'];sources=dict(prediction['sources']);util.verify(dict(sources=sources))
    jobs=[];scans={}
    for index in (0,16):
        _,_,_,_,_,x,_,bound=benchmark.context(index);sources.update(bound)
        control=read(HILL.parent/f'2026_09_30_ds11_single10/runs/{index:02d}_iid.json')['selected']
        scans[str(index)]=dict(control={k:control[k] for k in ('x','score','estimate_deg')})
        jobs.extend(dict(index=index,arm=arm,seed=seed,seed_index=i)
                    for arm in ARMS for i,seed in enumerate([x.tolist(),[0.,0.,0.]]))
    for path in (prediction_path,Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md',
                 HILL/'cross_band_rx_position/run.py',HILL/'harness.py',HILL/'pilot_fallback00/run.py',HILL/'timing/model.py'):
        sources[str(path)]=digest(path)
    write(HERE/'plan.json',dict(scans=scans,jobs=jobs,sources=sources,reference_used=False))
    print(json.dumps(dict(jobs=len(jobs),plan_sha256=digest(HERE/'plan.json'))))

def fit(i):
    started=time.monotonic();plan=read(HERE/'plan.json');util.verify(plan);job=plan['jobs'][i]
    _,_,harness,helper=util.dependencies()
    doc,older,config,mapping,scan,_,priors,_=benchmark.context(job['index'])
    variant=job['arm'];weights=priors['priors']['orbit' if variant=='zero' else variant]['weights']
    model=JointOrbit(doc,older,config,mapping,scan['groups'],scan['singletons'],variant,weights)
    def objective(x):
        r=model.evaluate(x);return -r['score'],-r['gradient']
    result=minimize(objective,job['seed'],jac=True,method='L-BFGS-B',bounds=util.BOUNDS,
                    options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
    endpoint=helper.audited_endpoint(model,result.x,bool(result.success),harness)
    endpoint.update(success=bool(result.success),message=str(result.message),nfev=int(result.nfev))
    if endpoint['qualified']:endpoint['estimate_deg']=list(model.model.coordinates(result.x))
    write(HERE/f'runs/{i:02d}.json',dict(job=job,endpoint=endpoint,elapsed_s=time.monotonic()-started,
                                     plan_sha256=digest(HERE/'plan.json')))

def batch():
    plan=read(HERE/'plan.json');util.verify(plan);(HERE/'runs').mkdir(exist_ok=True)
    def launch(i):
        stem=HERE/f'runs/{i:02d}';started=time.monotonic()
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',
                 'timeout','--kill-after=5s','90s','nice','-n','19',util.PYTHON,str(HERE/'run.py'),'fit',str(i)]
        with stem.with_suffix('.log').open('x') as log:done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        write(stem.with_suffix('.receipt.json'),dict(job_index=i,exit_code=done.returncode,
              wall_s=time.monotonic()-started,plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=i,exit_code=done.returncode)),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(len(plan['jobs']))))

def seal():
    plan=read(HERE/'plan.json');util.verify(plan);attempts=[]
    for i,job in enumerate(plan['jobs']):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt['plan_sha256']==digest(HERE/'plan.json')
        result=read(HERE/f'runs/{i:02d}.json') if receipt['exit_code']==0 else None
        if result:assert result['job']==job and result['plan_sha256']==receipt['plan_sha256']
        attempts.append(dict(job=job,receipt=receipt,result=result))
    selected={index:{arm:select(attempts,int(index),arm) for arm in ARMS} for index in plan['scans']}
    write(HERE/'selections.json',dict(selected=selected,attempts=attempts,reference_used=False,
                                    plan_sha256=digest(HERE/'plan.json')))
    print(json.dumps(dict(qualified_outputs=sum(v is not None for arms in selected.values() for v in arms.values()))))

def assess():
    plan=read(HERE/'plan.json');util.verify(plan);selections=read(HERE/'selections.json')
    assert selections['plan_sha256']==digest(HERE/'plan.json');_,_,harness,_=util.dependencies();rows=[]
    for index,scan in plan['scans'].items():
        errors=dict(iid=harness.distance(scan['control']['estimate_deg']))
        for arm in ARMS:
            selected=selections['selected'][index][arm]
            errors[arm]=harness.distance(selected['estimate_deg']) if selected else None
        rows.append(dict(index=int(index),errors_m=errors))
    outcome=dict(rows=rows,gate_pass=gate(rows),promotion=False,plan_sha256=digest(HERE/'plan.json'),
                 selection_sha256=digest(HERE/'selections.json'))
    write(HERE/'outcome.json',outcome);print(json.dumps(outcome,indent=2))

if __name__=='__main__':
    if sys.argv[1]=='fit':fit(int(sys.argv[2]))
    else:dict(prepare=prepare,batch=batch,seal=seal,assess=assess)[sys.argv[1]]()
