"""Reuse qualified bounded fits; seal training selection before geographic score."""
import concurrent.futures
import importlib.util
from pathlib import Path
import subprocess
import sys
import time
import json

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
spec=importlib.util.spec_from_file_location('calibrated_height_fit',HILL/'height_robustness/run.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
shared.HERE=HERE
read,write,digest=shared.read,shared.write,shared.digest

def prepare():
    base=HILL.parent/'2026_09_30_ds11_single10'
    original=read(base/'plan.json');evidence=read(HERE/'evidence.json')
    sources=dict(read(HILL/'fixed_height/preflight.json')['sources']);jobs=[]
    for index in (0,16):
        path=base/f'runs/{index:02d}_iid.json';control=read(path)['selected']
        assert control['qualified'];sources[str(path)]=digest(path)
        for height in (0,evidence['fixed_model_height_m']):
            for seed in (control['x'],[0.,0.,0.]):
                jobs.append(dict(index=index,height_m=height,seed=seed))
    for path in (Path(__file__),HERE/'PROTOCOL.md',HERE/'evidence.json',HILL/'height_robustness/run.py',
                 HILL/'height_robustness/test_run.py',HILL/'altitude_evidence/external-evidence.json'):
        sources[str(path)]=digest(path)
    plan=dict(config=original['config'],inputs=original['inputs'],jobs=jobs,sources=sources)
    shared.verify(plan);write(HERE/'plan.json',plan)

def batch():
    plan=read(HERE/'plan.json');shared.verify(plan);(HERE/'runs').mkdir(exist_ok=True)
    def launch(number):
        stem=HERE/f'runs/{number:02d}';start=time.monotonic()
        with stem.with_suffix('.log').open('x') as log:
            r=subprocess.run(['timeout','--kill-after=5s','90s',sys.executable,str(Path(__file__)),'fit',str(number)],stdout=log,stderr=subprocess.STDOUT)
        write(stem.with_suffix('.receipt.json'),dict(exit_code=r.returncode,wall_s=time.monotonic()-start,plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=number,exit_code=r.returncode)),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(launch,range(len(plan['jobs']))))

def seal():
    plan=read(HERE/'plan.json');shared.verify(plan);attempts=[];sources={str(HERE/'plan.json'):digest(HERE/'plan.json')}
    for number,job in enumerate(plan['jobs']):
        rp=HERE/f'runs/{number:02d}.receipt.json';receipt=read(rp);sources[str(rp)]=digest(rp)
        assert receipt['plan_sha256']==digest(HERE/'plan.json')
        result=None
        if receipt['exit_code']==0:
            path=HERE/f'runs/{number:02d}.json';result=read(path);sources[str(path)]=digest(path)
            assert result['job']==job and result['plan_sha256']==receipt['plan_sha256']
        attempts.append(result)
    rows=[]
    for index in (0,16):
        for height in (0,read(HERE/'evidence.json')['fixed_model_height_m']):
            selected=shared.select([r for r in attempts if r and r['job']['index']==index and r['job']['height_m']==height])
            rows.append(dict(index=index,height_m=height,selected=selected))
    write(HERE/'selections.json',dict(rows=rows,sources=sources,reference_used=False))

def assess():
    plan=read(HERE/'plan.json');shared.verify(plan);sealed=read(HERE/'selections.json');shared.verify(sealed)
    base=HILL.parent/'2026_09_30_ds11_single10'
    spec=importlib.util.spec_from_file_location('height_geographic_assessment',base/'summarize.py')
    geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    rows=[]
    for index in (0,16):
        arms={}
        for r in sealed['rows']:
            if r['index']!=index:continue
            selected=r['selected'];arm='control' if r['height_m']==0 else 'calibrated'
            arms[arm]=dict(qualified=selected is not None,error_m=None)
            if selected:
                doc=shared.fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
                model=shared.fixed.Model(doc,plan['config'],r['height_m'])
                estimate=model.coordinates(selected['x'])
                arms[arm].update(error_m=geo.distance(estimate),estimate_deg=list(estimate))
        rows.append(dict(index=index,arms=arms,improves=all(a['qualified'] for a in arms.values()) and arms['calibrated']['error_m']<arms['control']['error_m']))
    result=dict(rows=rows,screen_pass=all(r['improves'] for r in rows),scope='approximate station-calibrated reanalysis; causal orbit banks',
                sources={str(p):digest(p) for p in (HERE/'selections.json',HERE/'plan.json',Path(__file__),base/'summarize.py')})
    write(HERE/'summary.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':
    if sys.argv[1]=='fit':shared.fit(int(sys.argv[2]))
    else:dict(prepare=prepare,batch=batch,seal=seal,assess=assess)[sys.argv[1]]()
