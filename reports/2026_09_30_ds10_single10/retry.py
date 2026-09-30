import concurrent.futures,json,os,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def run(pair):
    i,method=pair;name=f'{i:02d}_{method}';start=time.monotonic()
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONPATH':str(HERE.parents[1])}
    with (HERE/'runs'/f'{name}.retry.log').open('x') as log:
        p=subprocess.run(['timeout','--kill-after=5s','90s','nice','-n','19','uv','run','--no-project','--with','numpy','--with','scipy','python',str(HERE/'run.py'),str(i),method],env=env,stdout=log,stderr=subprocess.STDOUT)
    receipt=dict(index=i,method=method,exit_code=p.returncode,wall_s=time.monotonic()-start)
    (HERE/'runs'/f'{name}.retry.receipt.json').write_text(json.dumps(receipt,indent=2));print(receipt,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,[(i,m) for i in range(3) for m in ('slope','curvature')]))
