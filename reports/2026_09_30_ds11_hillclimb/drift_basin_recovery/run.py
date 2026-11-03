"""Recover possible original-IID basins from frozen drift-fit endpoints."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
spec=importlib.util.spec_from_file_location('frozen_position_helpers',HILL/'cross_band_rx_position/run.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
read,write,digest=parent.read,parent.write,parent.digest


def deduplicate(attempts):
    jobs=[]
    for ordinal,a in enumerate(attempts):
        if not a['result'] or not a['result']['endpoint']['qualified']:continue
        index=a['job']['index'];x=a['result']['endpoint']['x']
        if any(j['index']==index and np.linalg.norm(np.array(j['seed'][:2])-x[:2])<=.001 and abs(j['seed'][2]-x[2])<=.001 for j in jobs):continue
        jobs.append(dict(index=index,seed=x,parent_job=ordinal))
    return jobs


def prepare():
    previous_plan=HILL/'cross_band_rx_position/plan.json';previous_selection=HILL/'cross_band_rx_position/selections.json'
    p=read(previous_plan);parent.verify(p);s=read(previous_selection)
    assert s['plan_sha256']==digest(previous_plan)
    sources=dict(p['sources'])
    for path in (previous_plan,previous_selection,HILL/'cross_band_rx_position/run.py',Path(__file__),HERE/'PROTOCOL.md',HERE/'test_run.py'):
        sources[str(path)]=digest(path)
    plan=dict(config=p['config'],scans={i:dict(input=r['input'],control=r['control']) for i,r in p['scans'].items()},jobs=deduplicate(s['attempts']),sources=sources,reference_used=False)
    write(HERE/'plan.json',plan)
    print(json.dumps(dict(jobs=len(plan['jobs']),plan_sha256=digest(HERE/'plan.json'))))


def fit(i):
    start=time.monotonic();plan=read(HERE/'plan.json');parent.verify(plan)
    fast,timing,harness,helper=parent.dependencies();job=plan['jobs'][i];scan=plan['scans'][str(job['index'])]
    doc=fast.load_documents(dict(config=plan['config'],inputs=[scan['input']]))[0]
    model=timing.TimingModel([doc],plan['config'],'original')
    def objective(x):
        r=model.evaluate(x,gradient=True);return -r['score'],-r['gradient']
    result=minimize(objective,job['seed'],jac=True,method='L-BFGS-B',bounds=parent.BOUNDS,
                    options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
    endpoint=helper.audited_endpoint(model,result.x,bool(result.success),harness)
    endpoint.update(success=bool(result.success),message=str(result.message))
    if endpoint['qualified']:endpoint['estimate_deg']=list(model.model.coordinates(result.x))
    write(HERE/f'runs/{i:02d}.json',dict(job=job,endpoint=endpoint,elapsed_s=time.monotonic()-start,plan_sha256=digest(HERE/'plan.json')))


def batch():
    plan=read(HERE/'plan.json');parent.verify(plan);(HERE/'runs').mkdir(exist_ok=True)
    def launch(i):
        path=HERE/f'runs/{i:02d}';start=time.monotonic()
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1','timeout','--kill-after=5s','90s','nice','-n','19',parent.PYTHON,str(HERE/'run.py'),'fit',str(i)]
        with path.with_suffix('.log').open('x') as log:done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        write(path.with_suffix('.receipt.json'),dict(job_index=i,exit_code=done.returncode,wall_s=time.monotonic()-start,plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=i,exit_code=done.returncode)),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(len(plan['jobs']))))


def seal():
    plan=read(HERE/'plan.json');parent.verify(plan);attempts=[];selected={}
    for i,job in enumerate(plan['jobs']):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt['plan_sha256']==digest(HERE/'plan.json')
        result=read(HERE/f'runs/{i:02d}.json') if receipt['exit_code']==0 else None
        if result:assert result['job']==job and result['plan_sha256']==receipt['plan_sha256']
        attempts.append(dict(job=job,receipt=receipt,result=result))
    for index,scan in plan['scans'].items():
        best=dict(scan['control']);replacement=False
        for a in attempts:
            if str(a['job']['index'])!=index or not a['result']:continue
            e=a['result']['endpoint']
            if e['qualified'] and e['score']>best['score']+1e-6:best=e;replacement=True
        selected[index]=dict(endpoint=best,replacement=replacement,score_gain=best['score']-scan['control']['score'])
    write(HERE/'selections.json',dict(selected=selected,attempts=attempts,reference_used=False,plan_sha256=digest(HERE/'plan.json')))
    print(json.dumps({k:dict(replacement=v['replacement'],score_gain=v['score_gain']) for k,v in selected.items()}))


def assess():
    plan=read(HERE/'plan.json');parent.verify(plan);s=read(HERE/'selections.json');assert s['plan_sha256']==digest(HERE/'plan.json')
    _,_,harness,_=parent.dependencies();rows=[]
    for index,r in s['selected'].items():
        rows.append(dict(index=int(index),replacement=r['replacement'],score_gain=r['score_gain'],
                         baseline_error_m=harness.distance(plan['scans'][index]['control']['estimate_deg']),
                         selected_error_m=harness.distance(r['endpoint']['estimate_deg'])))
    output=dict(rows=rows,replacements=sum(r['replacement'] for r in rows),
                baseline_median_m=float(np.median([r['baseline_error_m'] for r in rows])),
                selected_median_m=float(np.median([r['selected_error_m'] for r in rows])),
                plan_sha256=digest(HERE/'plan.json'),selection_sha256=digest(HERE/'selections.json'))
    write(HERE/'outcome.json',output);print(json.dumps(output,indent=2))


if __name__=='__main__':
    if sys.argv[1]=='fit':fit(int(sys.argv[2]))
    else:{'prepare':prepare,'batch':batch,'seal':seal,'assess':assess}[sys.argv[1]]()
