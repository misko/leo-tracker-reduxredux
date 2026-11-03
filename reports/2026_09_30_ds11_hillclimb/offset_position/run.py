"""Bounded two-scan full-mixture CFO marginalization fits."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize
from model import MarginalModel,fast

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
spec=importlib.util.spec_from_file_location('position_util',HILL/'cross_band_rx_position/run.py')
util=importlib.util.module_from_spec(spec);spec.loader.exec_module(util)
read,write,digest=util.read,util.write,util.digest


def prepare():
    path=HILL/'offset_quadrature/outcome.json';benchmark=read(path);assert benchmark['summary']['numerical_gate_pass']
    sources=dict(benchmark['sources']);util.verify(dict(sources=sources))
    base=HILL.parent/'2026_09_30_ds11_single10';plan=read(base/'plan.json');scans={};jobs=[]
    for index in (0,16):
        control=read(base/f'runs/{index:02d}_iid.json')['selected'];assert control['qualified']
        doc=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
        check=MarginalModel(doc,plan['config']).evaluate(control['x'])
        previous=next(s for s in benchmark['scans'] if s['index']==index)['orders']['32']
        assert abs(check['score']-previous['score'])<1e-6
        assert np.max(abs(check['gradient']-previous['gradient']))<1e-6
        scans[str(index)]=dict(input=plan['inputs'][index],control={k:control[k] for k in ('x','score','estimate_deg')},marginal_control_score=check['score'])
        jobs.extend(dict(index=index,seed=seed,seed_index=i) for i,seed in enumerate([control['x']]+[[e,0.,0.] for e in (-2.,0.,2.)]))
    for p in (path,Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md',HILL/'cross_band_rx_position/run.py',HILL/'pilot_fallback00/run.py',HILL/'harness.py',HILL/'timing/model.py'):
        sources[str(p)]=digest(p)
    write(HERE/'plan.json',dict(config=plan['config'],scans=scans,jobs=jobs,sources=sources,reference_used=False))
    print(json.dumps(dict(jobs=len(jobs),plan_sha256=digest(HERE/'plan.json'))))


def fit(i):
    started=time.monotonic();plan=read(HERE/'plan.json');util.verify(plan)
    _,_,harness,helper=util.dependencies();job=plan['jobs'][i];scan=plan['scans'][str(job['index'])]
    doc=fast.load_documents(dict(config=plan['config'],inputs=[scan['input']]))[0];model=MarginalModel(doc,plan['config'])
    def objective(x):
        r=model.evaluate(x);return -r['score'],-r['gradient']
    result=minimize(objective,job['seed'],jac=True,method='L-BFGS-B',bounds=util.BOUNDS,
                    options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
    endpoint=helper.audited_endpoint(model,result.x,bool(result.success),harness)
    coarse=model.evaluate(result.x);fine=MarginalModel(doc,plan['config'],64).evaluate(result.x)
    endpoint.update(success=bool(result.success),message=str(result.message),nfev=int(result.nfev),
                    quadrature_value_error=abs(coarse['score']-fine['score']),
                    quadrature_gradient_error=float(np.max(abs(coarse['gradient']-fine['gradient']))))
    endpoint['qualified']=endpoint['qualified'] and endpoint['quadrature_value_error']<1e-6 and endpoint['quadrature_gradient_error']<1e-3
    if endpoint['qualified']:endpoint['estimate_deg']=list(model.model.coordinates(result.x))
    write(HERE/f'runs/{i:02d}.json',dict(job=job,endpoint=endpoint,elapsed_s=time.monotonic()-started,plan_sha256=digest(HERE/'plan.json')))


def batch():
    plan=read(HERE/'plan.json');util.verify(plan);(HERE/'runs').mkdir(exist_ok=True)
    def launch(i):
        stem=HERE/f'runs/{i:02d}';started=time.monotonic()
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1','timeout','--kill-after=5s','90s','nice','-n','19',util.PYTHON,str(HERE/'run.py'),'fit',str(i)]
        with stem.with_suffix('.log').open('x') as log:done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        write(stem.with_suffix('.receipt.json'),dict(job_index=i,exit_code=done.returncode,wall_s=time.monotonic()-started,plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=i,exit_code=done.returncode)),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(len(plan['jobs']))))


def seal():
    plan=read(HERE/'plan.json');util.verify(plan);attempts=[];selected={}
    for i,job in enumerate(plan['jobs']):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt['plan_sha256']==digest(HERE/'plan.json')
        result=read(HERE/f'runs/{i:02d}.json') if receipt['exit_code']==0 else None
        if result:assert result['job']==job and result['plan_sha256']==receipt['plan_sha256']
        attempts.append(dict(job=job,receipt=receipt,result=result))
    for index in plan['scans']:
        valid=[a['result']['endpoint'] for a in attempts if str(a['job']['index'])==index and a['result'] and a['result']['endpoint']['qualified']]
        selected[index]=max(valid,key=lambda e:e['score']) if valid else None
    write(HERE/'selections.json',dict(selected=selected,attempts=attempts,reference_used=False,plan_sha256=digest(HERE/'plan.json')))
    print(json.dumps(dict(qualified_outputs=sum(v is not None for v in selected.values()))))


def assess():
    plan=read(HERE/'plan.json');util.verify(plan);s=read(HERE/'selections.json');assert s['plan_sha256']==digest(HERE/'plan.json')
    _,_,harness,_=util.dependencies();rows=[]
    for index,scan in plan['scans'].items():
        selected=s['selected'][index]
        rows.append(dict(index=int(index),baseline_error_m=harness.distance(scan['control']['estimate_deg']),
                         marginal_error_m=harness.distance(selected['estimate_deg']) if selected else None))
    output=dict(rows=rows,gate_pass=all(r['marginal_error_m'] is not None and r['marginal_error_m']<r['baseline_error_m'] for r in rows),
                promotion=False,plan_sha256=digest(HERE/'plan.json'),selection_sha256=digest(HERE/'selections.json'))
    write(HERE/'outcome.json',output);print(json.dumps(output,indent=2))


if __name__=='__main__':
    if sys.argv[1]=='fit':fit(int(sys.argv[2]))
    else:{'prepare':prepare,'batch':batch,'seal':seal,'assess':assess}[sys.argv[1]]()
