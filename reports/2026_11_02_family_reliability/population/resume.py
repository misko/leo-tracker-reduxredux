"""One authorized second bounded execution window for unfinished records."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from algo06_science.common import read,write

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
LOCK=threading.Lock()
COMPLETE={'accepted','guard_rejected','no_RF_trigger','preserved_existing_ALGO07'}

def main():
    os.setpriority(os.PRIO_PROCESS,0,10)
    # Avoid exceeding the authorized twelve total numerical workers.
    while not ((ROOT/'completion.json').exists() and (ROOT/'initial_audit_summary.json').exists()):time.sleep(5)
    policy=read(ROOT/'protocol.json');records=policy['cases']
    window_path=ROOT/'resume_window.json'
    if window_path.exists():window=read(window_path)
    else:
        window=dict(start_utc_ns=time.time_ns(),max_seconds=1200)
        write(window_path,window)
    elapsed=time.time()-window['start_utc_ns']/1e9
    began=time.monotonic()-elapsed;deadline=time.monotonic()+max(0.,1200-elapsed)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH='src:tools')
    claimed=set();attempts=[]
    def unfinished(record):
        path=ROOT/'cases'/record['case']/'result.json'
        if not path.exists():return True
        row=read(path)
        if row['status'] in COMPLETE:return False
        if row['status'] in ('case_cap','resume_case_cap','resume_total_cap'):return False
        if 'Selected family lacks existing physical modes' in row.get('reason',''):return False
        if 'Baseline full native union mismatch' in row.get('reason',''):return False
        return True
    def loop(index):
        while time.monotonic()<deadline:
            if index>=8 and not (ROOT/'extra_completion.json').exists():
                time.sleep(5)
                continue
            with LOCK:
                available=[r for r in records if r['case'] not in claimed and unfinished(r)]
                if not available:return
                record=available[0];case=record['case'];claimed.add(case)
            archived=None
            folder=ROOT/'cases'/case;folder.mkdir(parents=True,exist_ok=True)
            with (folder/'worker.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                path=folder/'result.json'
                if path.exists():
                    old=read(path)
                    if not unfinished(record):continue
                    archived=folder/('before-resume-'+str(time.time_ns())+'.json');path.replace(archived)
            item=dict(case=case,window='second_bounded_resume',prior_receipt=str(archived) if archived else None)
            try:
                with (ROOT/(case+'-resume.log')).open('w') as f:
                    subprocess.run([sys.executable,str(ROOT/'run.py'),'--case',case],cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT,
                        timeout=min(600,deadline-time.monotonic()),check=True)
                row=read(path);item.update(status=row['status'],seconds=row['seconds'])
            except Exception as exc:
                item.update(status='resume_cap_or_failure',reason=repr(exc))
                partial=read(path) if path.exists() else {}
                if partial:write(folder/('partial-resume-'+str(time.time_ns())+'.json'),partial)
                partial.update(case=case,dataset=record['dataset'],identities=record['identities'],baseline=record['baseline'],
                    baseline_selected=record['selected'],accepted=False,status='resume_case_cap' if isinstance(exc,subprocess.TimeoutExpired) else 'resume_failed',reason=repr(exc),
                    protocol_sha256=hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest(),
                    source_input=record['input_path'],source_input_sha256=record['input_sha256'],
                    selected_output={a:dict(record['baseline'][a],source='exact_saved_ALGO07') for a in ('c0','fitted_c')},
                    development_case=case in policy['development_cases'])
                write(path,partial)
            with LOCK:
                attempts.append(item);write(ROOT/'resume_attempts.json',attempts)
            print('resume',index,case,item['status'],round(time.monotonic()-began),flush=True)
    with ThreadPoolExecutor(max_workers=12) as pool:list(pool.map(loop,range(12)))
    write(ROOT/'resume_completion.json',dict(seconds=time.monotonic()-began,max_seconds=1200,workers=12,attempted=len(attempts),attempts=attempts))

if __name__=='__main__':main()
