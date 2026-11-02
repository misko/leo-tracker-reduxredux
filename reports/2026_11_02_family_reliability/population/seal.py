"""Seal all205 audited decisions before producing any cohort GPS aggregate."""
import os
from pathlib import Path
import subprocess
import sys
import time
from algo06_science.common import read

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]

if __name__=='__main__':
    os.setpriority(os.PRIO_PROCESS,0,10)
    while not (ROOT/'resume_completion.json').exists():time.sleep(5)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH='src:tools')
    subprocess.run([sys.executable,str(ROOT/'audit.py'),'--workers','12'],cwd=REPO,env=env,check=True)
    audit=read(ROOT/'final_audit_summary.json')
    assert audit['cases']==205,'Every recording needs a final audited receipt before aggregation'
    subprocess.run([sys.executable,str(ROOT/'summarize.py')],cwd=REPO,env=env,check=True)
    print('SEALED:205 audited decisions; cohort GPS aggregates now generated',flush=True)
