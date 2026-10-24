"""Run each channel half in an isolated process with eight total worker slots."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
ENV=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
         MKL_NUM_THREADS='1',PYTHONPATH='/tmp/algo03-feasible-deps:src:tools')


def one(group,case):
    root=ROOT/group
    with (root/(case+'.log')).open('w') as log:
        r=subprocess.run([str(REPO/'.venv/bin/python'),'-B',str(root/'engine/run_baseline.py'),
                           '--cases',case,'--workers','1'],cwd=REPO,env=ENV,stdout=log,stderr=subprocess.STDOUT)
    p=root/case/'baseline_execution.json'
    result=json.loads(p.read_bytes()) if p.exists() else dict(case=case,status='supervisor_failed',returncode=r.returncode)
    return dict(result,group=group)


if __name__=='__main__':
    members=json.loads((ROOT/'ch1_4/sample.json').read_bytes())['selected']
    jobs=[(group,m['dataset_label']) for m in sorted(members,key=lambda m:m['captured_utc_ns']) for group in ('ch1_4','ch5_8')]
    rows=[];start=time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one,*job) for job in jobs]):
            row=future.result();rows.append(row);print(json.dumps(row),flush=True)
            for group in ('ch1_4','ch5_8'):
                sub=[r for r in rows if r['group']==group]
                (ROOT/group/'execution.json').write_text(json.dumps(dict(all_terminal=len(sub)==34,total=34,completed=len(sub),receipts=sub),indent=2)+'\n')
            tmp=ROOT/'execution.tmp';tmp.write_text(json.dumps(dict(all_terminal=len(rows)==68,total=68,completed=len(rows),seconds=time.monotonic()-start,receipts=rows),indent=2)+'\n')
            tmp.replace(ROOT/'execution.json')
