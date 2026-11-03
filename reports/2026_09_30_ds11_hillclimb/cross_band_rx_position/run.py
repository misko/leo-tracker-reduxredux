"""Bounded geographic comparison of three frozen receiver allocations."""
import concurrent.futures
import hashlib
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
ROOT=HERE.parents[2]
BASE=HILL.parent/'2026_09_30_ds11_single10'
ARMS=('rx1_fixed','symmetric','rx0_fixed')
BOUNDS=[(-12.,12.),(-12.,12.),(-5.,5.)]
PYTHON='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'
def read(p): return json.loads(Path(p).read_text())
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with Path(p).open('x') as f: json.dump(v,f,indent=2,allow_nan=False)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m
def dependencies():
    sys.path.insert(0,str(ROOT/'tools'))
    import ds7_fast_baseline_adapter as fast
    timing=module('rx_position_timing',HILL/'timing/model.py')
    harness=module('rx_position_harness',HILL/'harness.py')
    helper=module('rx_position_audit',HILL/'pilot_fallback00/run.py')
    helper.BOUNDS=BOUNDS
    return fast,timing,harness,helper
def patch(document,corrections):
    assert set(corrections)<=set(t['track_id'] for t in document['tracks'])
    tracks=[]
    for t in document['tracks']:
        delta=np.asarray(corrections.get(t['track_id'],np.zeros(len(t['y']))))
        assert delta.shape==t['y'].shape and np.isfinite(delta).all()
        tracks.append(dict(t,y=t['y']+delta))
    return dict(document,tracks=tracks)
def verify(plan):
    for p,h in plan['sources'].items(): assert digest(p)==h,p
def prepare():
    fixed_path=HILL/'cross_band_rx_fixed/outcome.json';fixed=read(fixed_path)
    assert fixed['summary']['rx1_fixed']['gate_pass']
    sources=dict(fixed['sources']);verify(dict(sources=sources))
    base=read(BASE/'plan.json');scans={};jobs=[]
    for row in fixed['rows']:
        index=row['index'];original_path=BASE/f'runs/{index:02d}_iid.json'
        original=read(original_path)['selected'];assert original['qualified']
        corrections={arm:{} for arm in ARMS}
        for pair in row['corrections']:
            a,b=pair['tracks'];da=np.array(pair['canonical_delta_rx1']);db=np.array(pair['canonical_delta_rx0'])
            for arm,alpha in zip(ARMS,(0.,.5,1.)):
                assert a not in corrections[arm] and b not in corrections[arm]
                corrections[arm][a]=(-alpha*da).tolist();corrections[arm][b]=((1-alpha)*db).tolist()
        scans[str(index)]=dict(input=base['inputs'][index],control={k:original[k] for k in ('x','score','estimate_deg')},corrections=corrections)
        seeds=[original['x']]+[[east,0.,0.] for east in (-2.,0.,2.)]
        jobs.extend(dict(index=index,arm=arm,seed=seed,seed_index=i) for arm in ARMS for i,seed in enumerate(seeds))
    for path in (fixed_path,Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md',HILL/'timing/model.py',HILL/'harness.py',HILL/'pilot_fallback00/run.py'):
        sources[str(path)]=digest(path)
    write(HERE/'plan.json',dict(config=base['config'],scans=scans,jobs=jobs,sources=sources,reference_used=False))
    print(json.dumps(dict(jobs=len(jobs),plan_sha256=digest(HERE/'plan.json'))))
def fit(i):
    started=time.monotonic();plan=read(HERE/'plan.json');verify(plan)
    fast,timing,harness,helper=dependencies();job=plan['jobs'][i];scan=plan['scans'][str(job['index'])]
    document=fast.load_documents(dict(config=plan['config'],inputs=[scan['input']]))[0]
    model=timing.TimingModel([patch(document,scan['corrections'][job['arm']])],plan['config'],'original')
    def objective(x):
        r=model.evaluate(x,gradient=True);return -r['score'],-r['gradient']
    result=minimize(objective,job['seed'],jac=True,method='L-BFGS-B',bounds=BOUNDS,
                    options=dict(maxiter=100,maxfun=160,ftol=1e-13,gtol=1e-6,maxls=25))
    endpoint=helper.audited_endpoint(model,result.x,bool(result.success),harness)
    endpoint.update(success=bool(result.success),message=str(result.message),nfev=int(result.nfev))
    if endpoint['qualified']: endpoint['estimate_deg']=list(model.model.coordinates(result.x))
    write(HERE/f'runs/{i:02d}.json',dict(job=job,endpoint=endpoint,elapsed_s=time.monotonic()-started,plan_sha256=digest(HERE/'plan.json')))
def batch():
    plan=read(HERE/'plan.json');verify(plan);(HERE/'runs').mkdir(exist_ok=True)
    def launch(i):
        stem=HERE/f'runs/{i:02d}';assert not stem.with_suffix('.json').exists()
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1','timeout','--kill-after=5s','90s','nice','-n','19',PYTHON,str(HERE/'run.py'),'fit',str(i)]
        start=time.monotonic()
        with stem.with_suffix('.log').open('x') as log: done=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        write(stem.with_suffix('.receipt.json'),dict(job_index=i,exit_code=done.returncode,wall_s=time.monotonic()-start,plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=i,exit_code=done.returncode)),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(len(plan['jobs']))))
def seal():
    plan=read(HERE/'plan.json');verify(plan);selected={};attempts=[]
    for i,job in enumerate(plan['jobs']):
        receipt=read(HERE/f'runs/{i:02d}.receipt.json');assert receipt['plan_sha256']==digest(HERE/'plan.json')
        result=read(HERE/f'runs/{i:02d}.json') if receipt['exit_code']==0 else None
        if result: assert result['job']==job and result['plan_sha256']==receipt['plan_sha256']
        attempts.append(dict(job=job,receipt=receipt,result=result))
    for index in plan['scans']:
        selected[index]={}
        for arm in ARMS:
            valid=[a['result']['endpoint'] for a in attempts if str(a['job']['index'])==index and a['job']['arm']==arm and a['result'] and a['result']['endpoint']['qualified']]
            selected[index][arm]=max(valid,key=lambda x:x['score']) if valid else None
    write(HERE/'selections.json',dict(selected=selected,attempts=attempts,reference_used=False,plan_sha256=digest(HERE/'plan.json')))
    print(json.dumps(dict(qualified=sum(v is not None for r in selected.values() for v in r.values()),total=24)))
def assess():
    plan=read(HERE/'plan.json');verify(plan);selection=read(HERE/'selections.json');assert selection['plan_sha256']==digest(HERE/'plan.json')
    _,_,harness,_=dependencies();rows=[]
    for index,scan in plan['scans'].items():
        row=dict(index=int(index),baseline_error_m=harness.distance(scan['control']['estimate_deg']),errors_m={})
        for arm,endpoint in selection['selected'][index].items(): row['errors_m'][arm]=harness.distance(endpoint['estimate_deg']) if endpoint else None
        rows.append(row)
    baseline=np.array([r['baseline_error_m'] for r in rows]);summary={}
    for arm in ARMS:
        values=[r['errors_m'][arm] for r in rows];complete=all(v is not None for v in values)
        summary[arm]=dict(qualified=sum(v is not None for v in values),gate_pass=False)
        if complete:
            summary[arm].update(median_m=float(np.median(values)),mean_m=float(np.mean(values)),p90_m=float(np.quantile(values,.9)),maximum_m=float(max(values)),wins=int(sum(a<b for a,b in zip(values,baseline))))
            summary[arm]['gate_pass']=bool(summary[arm]['wins']>=6 and np.median(values)<=.9*np.median(baseline))
    write(HERE/'outcome.json',dict(rows=rows,summary=summary,baseline_median_m=float(np.median(baseline)),primary='rx1_fixed',promotion=False,selection_sha256=digest(HERE/'selections.json'),plan_sha256=digest(HERE/'plan.json')))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':
    if sys.argv[1]=='fit':fit(int(sys.argv[2]))
    else:{'prepare':prepare,'batch':batch,'seal':seal,'assess':assess}[sys.argv[1]]()
