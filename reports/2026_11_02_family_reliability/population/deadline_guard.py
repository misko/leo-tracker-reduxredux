"""Enforce original resume deadline across manager reloads and retained locks."""
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time
from algo06_science.common import read,write

ROOT=Path(__file__).resolve().parent

if __name__=='__main__':
    os.setpriority(os.PRIO_PROCESS,0,10)
    window=read(ROOT/'resume_window.json');stop=window['start_utc_ns']/1e9+1200
    while time.time()<stop:
        if (ROOT/'resume_completion.json').exists():
            write(ROOT/'deadline_guard.json',dict(status='finished_before_deadline',records=[]));raise SystemExit(0)
        time.sleep(min(2,max(.01,stop-time.time())))
    policy=read(ROOT/'protocol.json');by_case={r['case']:r for r in policy['cases']};records=[]
    process_rows=subprocess.check_output(['ps','-eo','pid,etimes,args'],text=True).splitlines()
    # Stop the manager first so blocked lock waiters cannot spawn after cutoff.
    for line in process_rows:
        fields=line.split(None,2)
        if len(fields)==3 and fields[2].endswith('/population/resume.py') and 'python' in fields[2]:
            try:os.kill(int(fields[0]),signal.SIGTERM)
            except ProcessLookupError:pass
    for line in process_rows:
        fields=line.split(None,2)
        if len(fields)<3 or '/population/run.py --case ' not in fields[2] or 'python' not in fields[2]:continue
        case=fields[2].rsplit(' --case ',1)[-1].strip()
        if case not in by_case:continue
        pid=int(fields[0]);folder=ROOT/'cases'/case;path=folder/'result.json';partial=read(path) if path.exists() else {}
        if partial.get('status') in ('accepted','guard_rejected','no_RF_trigger','preserved_existing_ALGO07'):continue
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:continue
        source=by_case[case]
        if partial:write(folder/('deadline-partial-'+str(time.time_ns())+'.json'),partial)
        partial.update(case=case,dataset=source['dataset'],identities=source['identities'],baseline=source['baseline'],baseline_selected=source['selected'],
            accepted=False,status='resume_total_cap',reason='Original1200s resume window exhausted; no further RF retries',
            protocol_sha256=hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest(),source_input=source['input_path'],source_input_sha256=source['input_sha256'],
            selected_output={a:dict(source['baseline'][a],source='exact_saved_ALGO07') for a in ('c0','fitted_c')},development_case=case in policy['development_cases'])
        write(path,partial);records.append(dict(case=case,pid=pid,worker_elapsed_seconds=int(fields[1])))
    write(ROOT/'deadline_guard.json',dict(status='original_deadline_enforced',original_stop_utc_ns=int(stop*1e9),records=records))
    if not (ROOT/'resume_completion.json').exists():
        attempts=read(ROOT/'resume_attempts.json') if (ROOT/'resume_attempts.json').exists() else []
        write(ROOT/'resume_completion.json',dict(status='original_deadline_enforced',seconds=1200,max_seconds=1200,workers=12,
            recorded_manager_attempts=len(attempts),attempts=attempts,deadline_records=records))
