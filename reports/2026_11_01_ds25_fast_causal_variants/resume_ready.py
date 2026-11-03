"""Resume ready cases that previously reached the position queue before search."""
import subprocess,sys,os
from concurrent.futures import ThreadPoolExecutor,as_completed
from common import *

processes=subprocess.check_output(['ps','-eo','args'],text=True).splitlines()
active={line.split('--case ')[-1].split()[0] for line in processes if str(ROOT/'position.py')+' --case ' in line}
roster=[z for z in read(ROOT/'protocol.json')['cohort'] if z['case'] not in active and
        (ROOT/'screen'/z['case']/'result.json').exists() and not (ROOT/'position'/z['case']/'result.json').exists()]
write(ROOT/'resume-ready-roster.json',dict(active=sorted(active),ready=roster))

def work(z):
    case=z['case'];log=ROOT/'logs'/('position-resume-'+case+'.log')
    with log.open('w') as f:
        try:
            r=subprocess.run([sys.executable,str(ROOT/'position.py'),'--case',case],stdout=f,stderr=subprocess.STDOUT,timeout=2400,
                env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
            return dict(case=case,returncode=r.returncode,log=str(log))
        except subprocess.TimeoutExpired:return dict(case=case,returncode=-1,log=str(log))
rows=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    for future in as_completed([pool.submit(work,z) for z in roster]):
        r=future.result();rows.append(r);write(ROOT/'position-resume-execution.json',rows);print(len(rows),r,flush=True)
