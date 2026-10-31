"""Bounded shared-family recovery trials; never read evaluation coordinates."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

STUDY = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds27-algo04-20261031')
REPO = Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
RELEASE = Path('/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef')

def read(p):
    return json.loads(Path(p).read_text())

def write(p, value):
    Path(p).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def targets():
    result=[]
    for rank in (7, 1, 4, 2):
        audit=read(next((SOURCE/'top10-annotation-audit').glob(f'{rank:02d}-*.json')))
        version=audit['versions']['ALGO04']
        root=Path(version['recovery_root'])
        inventory=Path(version['inventory_matches'][0]['path'])
        validation=root/audit['track_id']/'annotation'
        result.append(dict(case=audit['case'],track_id=audit['track_id'],key=audit['key'],
            inventory=str(inventory),validation=str(validation),recovery=str(root),
            source_hashes={str(p):digest(p) for p in (inventory,validation/'result.json',validation/'protocol.json')}))
    return result

def stage(command, log, timeout=360):
    began=time.monotonic()
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
             PYTHONPATH=f'{RELEASE}/src:{RELEASE}/tools',MPLCONFIGDIR=str(STUDY/'mpl-cache'))
    with Path(log).open('x') as stream:
        try:
            r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,env=env,timeout=timeout,cwd=RELEASE)
            result=dict(returncode=r.returncode,state='complete' if r.returncode==0 else 'failed')
        except subprocess.TimeoutExpired:
            result=dict(returncode=None,state='timeout')
    return dict(result,seconds=time.monotonic()-began,command=list(map(str,command)),timeout_s=timeout)

def work(target, mode):
    out=STUDY/target['case']/mode
    out.parent.mkdir(exist_ok=True)
    receipt=out.parent/(mode+'-receipt.json')
    if receipt.exists():
        return read(receipt)
    flags={'marginal':['--shared-satellite-refresh'],
           'conditional':['--conditional-satellite-refresh'],
           'conditional_feasible':['--conditional-satellite-refresh','--position-fit','incumbent_feasible']}[mode]
    cmd=[sys.executable,str(RELEASE/'tools/algo04_numerical_stage.py'),
         '--reference-limit-s','30','--centered-lbfgsb','--receipt',str(out.parent/(mode+'-numerics.json')),
         str(RELEASE/'tools/include_predictive_annotations.py'),'--inventory',target['inventory'],
         '--validation',target['validation'],'--output',str(out),'--predictive-member',*flags]
    result=dict(case=target['case'],track_id=target['track_id'],mode=mode,fit=stage(cmd,out.parent/(mode+'.log')))
    if result['fit']['state']=='complete':
        cmd=[sys.executable,str(RELEASE/'tools/algo04_numerical_stage.py'),
             '--reference-limit-s','30','--centered-lbfgsb','--receipt',str(out.parent/(mode+'-audit-numerics.json')),
             str(RELEASE/'tools/audit_shared_predictive_inclusion.py'),'--study',target['recovery'],
             '--trial',str(out),'--output',str(out/'exact_owner_replay.json')]
        result['audit']=stage(cmd,out.parent/(mode+'-audit.log'),180)
    write(receipt,result)
    print(json.dumps(result),flush=True)
    return result

if __name__=='__main__':
    ts=targets()
    modes=sys.argv[1:] or ['marginal','conditional']
    name='-'.join(modes)
    protocol=STUDY/('protocol.json' if not sys.argv[1:] else name+'-protocol.json')
    if not protocol.exists():
        write(protocol,dict(targets=ts,modes=modes,arms=['c0','fitted_c'],
            workers=4,stage_timeout_s=360,original_25km_regional_start='conditional_feasible' not in modes,
            downstream_RF_incumbent_continuation='conditional_feasible' in modes,unchanged_RF_gates=True,
            no_GPS_inference=True,causal_only=True,production_changed=False,
            selection='Four strongest stable nominations in DS27 top-ten contiguous residuals',
            source_sha256=digest(__file__)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda job:work(*job),[(t,m) for t in ts for m in modes]))
    write(STUDY/('execution.json' if not sys.argv[1:] else name+'-execution.json'),rows)
