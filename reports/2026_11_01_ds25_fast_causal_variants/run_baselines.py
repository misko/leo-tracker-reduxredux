"""Bounded ALGO04/05 runs; retry historical ALGO03 process-audit failures once."""
import os,subprocess,time,signal,concurrent.futures
from prepare import *
R3=Path('/opt/leo-fast-graph/e67f67484c4f54316b33dfd8e12f6e68d09d1e13')
R4=Path('/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef')
R5=Path('/opt/leo-fast-graph/4675ec446f2889d92eeea902c234f3f91ab48007')
def call(root,script,args,log):
    env=dict(os.environ,PYTHONPATH=str(root/'src')+':'+str(root/'tools'),PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    with log.open('x') as f:
        p=subprocess.Popen([str(root/'venv/bin/python'),'-B',str(script),*map(str,args)],stdout=f,stderr=subprocess.STDOUT,cwd=root,env=env,start_new_session=True)
        try:return p.wait(timeout=1250)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();return -9
def one(row):
    case=row['case'];folder=WORK/'cases'/case;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'receipt.json').exists():return read(folder/'receipt.json')
    if row['state']!='ready':return row
    start=time.monotonic();result=dict(case=case,state='failed')
    try:
        source=Path(row['source_terminal']);recovery=Path(row['source_recovery'])
        assert digest(source)==row['terminal_sha256']
        if not row['historical_read_audit_verified']:
            out=folder/'retry-algo03'
            code=call(R3,R3/'tools/algo03_production_worker.py',['--snapshot',recovery/'snapshot/descriptor.json','--preparation-seconds','0',
                      '--output',out,'--maximum-seconds','1200'],folder/'retry-algo03.log')
            t=read(out/'terminal.json');result['ALGO03_retry_returncode']=code
            if not (t.get('read_audit') or {}).get('verified'):raise ValueError('Fresh ALGO03 process audit failed; retain original baseline separately')
            assert t['baseline']==read(source)['baseline']
            source=out/'terminal.json';recovery=out/'recovery'
        out4=folder/'algo04'
        if not (out4/'terminal.json').exists():
            result['ALGO04_returncode']=call(R4,ROOT/'offline_algo04.py',['--source-terminal',source,'--source-recovery',recovery,'--output',out4],folder/'algo04.log')
        out5=WORK/'baselines'/case
        if not (out5/'terminal.json').exists():
            result['ALGO05_returncode']=call(R5,ROOT/'offline_algo05.py',['--source-terminal',out4/'terminal.json','--source-recovery',out4/'recovery','--output',out5],folder/'algo05.log')
        t=read(out5/'terminal.json');result.update(state=t['state'],decision=t['decision'],terminal=str(out5/'terminal.json'),failure=t.get('failure'))
    except Exception as e:result.update(reason=f'{type(e).__name__}: {e}')
    result['seconds']=time.monotonic()-start;write(folder/'receipt.json',result);print(result,flush=True);return result
if __name__=='__main__':
    rows=read(ROOT/'roster.json')['cases'];results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        for f in concurrent.futures.as_completed([pool.submit(one,r) for r in rows]):
            results.append(f.result());write(ROOT/'baseline-execution.json',results)
