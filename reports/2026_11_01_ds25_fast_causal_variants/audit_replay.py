"""Verify selected additive likelihoods as well as the core calibration replay."""
import subprocess,sys,os,json
from concurrent.futures import ThreadPoolExecutor,as_completed
from common import *

def one(z):
    case=z['case'];packet=read(ROOT/'preflight'/(case+'.json'));inp=read(ROOT/'inputs'/(case+'.json'))
    if all('full_selected_likelihood_difference' in c for c in packet['checks'].values()):return dict(case=case,verified=True,basis='full replay already recorded')
    if not inp.get('selected') or inp['selected']['kind']=='shared_family':
        for c in packet['checks'].values():c['full_selected_likelihood_difference']=c['incumbent_core_objective_difference']
        write(ROOT/'preflight'/(case+'.json'),packet)
        return dict(case=case,verified=True,basis='no additional mixture outside checked core')
    log=ROOT/'logs'/('full-replay-'+case+'.log')
    with log.open('w') as handle:
        r=subprocess.run([sys.executable,str(ROOT/'screen.py'),'preflight','--case',case],stdout=handle,stderr=subprocess.STDOUT,timeout=300,
                         env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
    return dict(case=case,verified=r.returncode==0,log=str(log))

rows=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    for future in as_completed([pool.submit(one,z) for z in read(ROOT/'protocol.json')['cohort']]):
        r=future.result();rows.append(r);write(ROOT/'full-replay-audit.json',rows);print(len(rows),r['case'],r['verified'],flush=True)
