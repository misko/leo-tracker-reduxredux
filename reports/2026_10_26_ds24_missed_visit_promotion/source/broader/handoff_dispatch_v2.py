"""Deliver frozen graphs as soon as each reserved-first raw shard terminates."""
import concurrent.futures
import subprocess
import sys
import time
import application as app

def dispatch(case):
    log=app.HERE/'graph_logs_v2'/(case+'.log')
    with log.open('x') as stream:
        try:
            result=subprocess.run([sys.executable,'-B',str(app.HERE/'handoff_v2.py'),'case','--case',case],
                stdout=stream,stderr=subprocess.STDOUT,timeout=130)
            receipt=dict(case=case,exit_code=result.returncode)
        except subprocess.TimeoutExpired:receipt=dict(case=case,status='outer130second_guard')
    app.write(app.HERE/'graph_terminal_v2'/(case+'.json'),receipt)
    print(receipt,flush=True)
    return receipt

def main():
    p=app.read(app.RAW/'protocol.json');pending=list(p['cases']);running={};results=[]
    (app.HERE/'graph_logs_v2').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        while pending or running:
            for case in list(pending):
                if (app.HERE/'graphs'/case/'terminal_seal.json').exists():
                    results.append(dict(case=case,status='already_sealed'));pending.remove(case)
            for future in list(running):
                if future.done():results.append(future.result());del running[future]
            for case in list(pending):
                if len(running)>=2:break
                ready=case in p['no_eligible_cases'] or case in p['reused_cases'] or (app.RAW/'terminal'/(case+'.json')).exists()
                if ready:pending.remove(case);running[pool.submit(dispatch,case)]=case
            if pending or running:time.sleep(2)
    app.write(app.HERE/'handoff_summary_v2.json',dict(cases=results,all24_accounted=len(results)==24,
        successful_cases=[case for case in p['cases'] if (app.HERE/'graphs'/case/'terminal_seal.json').exists()],
        failures=[r for r in results if r.get('exit_code',0)!=0 or r.get('status')=='outer130second_guard']))

if __name__=='__main__':main()
