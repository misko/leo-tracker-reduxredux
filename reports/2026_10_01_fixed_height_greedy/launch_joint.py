"""90-second external bound and persistent receipt for joint-mode attempts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def launch(unit,folder,proposal=None,seed_limit=3,student_df=None):
    output=Path(folder)/f'{unit}-joint.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    path=output.with_suffix('.launch.json')
    if path.exists() or output.exists(): raise FileExistsError(path)
    command=[sys.executable,str(HERE/'joint_replay.py'),unit,'--output',str(output),'--seed-limit',str(seed_limit)]
    if proposal: command+=['--proposal',str(proposal)]
    if student_df is not None: command+=['--student-df',str(student_df)]
    env=os.environ.copy()
    env.update({key:'1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
    env['PYTHONPATH']=str(ROOT/'src')
    start=time.monotonic()
    receipt={'unit_id':unit,'command':command,'timeout_seconds':90}
    try:
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        receipt.update(status='complete' if result.returncode==0 else 'error',returncode=result.returncode,
                       stdout=result.stdout,stderr=result.stderr)
    except subprocess.TimeoutExpired as e:
        receipt.update(status='timeout',stdout=str(e.stdout or ''),stderr=str(e.stderr or ''))
    receipt['wall_seconds']=time.monotonic()-start
    if output.exists():
        native=json.loads(output.read_text());receipt['native_status']=native['status']
        receipt['exception']=native.get('exception')
        receipt['fits']=[{k:f[k] for k in ('converged','reason','iterations')} for f in native['fits']]
    with path.open('x') as f: json.dump(receipt,f,indent=2)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('stdout','stderr','command')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('unit');p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--proposal',type=Path);p.add_argument('--seed-limit',type=int,default=3)
    p.add_argument('--student-df',type=float)
    a=p.parse_args();launch(a.unit,a.folder,a.proposal,a.seed_limit,a.student_df)
