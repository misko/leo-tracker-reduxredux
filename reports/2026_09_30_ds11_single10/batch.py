import concurrent.futures,json,os,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
METHODS=['iid','shared','correlated','contrast','q020','q020_correlated','cone40','q020_cone40','slope','curvature']

def scan(index,plan_path=None):
    rows=[]
    for method in METHODS:
        start=time.monotonic();name=f'{index:02d}_{method}'
        cmd=['uv','run','--no-project','--with','numpy','--with','scipy','python',str(HERE/'run.py'),str(index),method]
        env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONPATH':str(HERE.parents[1])}
        if plan_path is not None:env['SINGLE_BENCH_PLAN']=str(plan_path)
        with (HERE/'runs'/f'{name}.log').open('x') as log:
            try:
                p=subprocess.run(['timeout','--kill-after=5s','90s','nice','-n','19',*cmd],env=env,stdout=log,stderr=subprocess.STDOUT)
                code=p.returncode
            except Exception as e:code=-1;log.write(repr(e))
        receipt=dict(index=index,method=method,exit_code=code,wall_s=time.monotonic()-start)
        (HERE/'runs'/f'{name}.receipt.json').write_text(json.dumps(receipt,indent=2))
        rows.append(receipt);print(json.dumps(receipt),flush=True)
    return rows

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(scan,range(32)))
    (HERE/'batch.json').write_text(json.dumps(results,indent=2))
