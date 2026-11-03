"""Replay the installed ALGO05 recovery over exact immutable ALGO04 exports."""
import json,time,sys,concurrent.futures
from pathlib import Path
from algo05_production_worker import verify_release,guarded_replay,verify_candidate,envelope
from algo03_shadow_worker import read,write

ROOT=Path(__file__).resolve().parent
def one(row):
    output=Path(row['export']).parent
    if (output/'terminal.json').exists():return dict(case=row['case'],state='complete',cached=True)
    descriptor=read(output/'source-export/descriptor.json');incumbent=descriptor['incumbent']
    candidate=None;audit=None;failure=None;started=time.monotonic()
    try:
        result=guarded_replay(output,deadline=started+1200);audit=result['read_audit']
        if result.get('selected'):candidate=verify_candidate(result,output)
    except Exception as error:failure=f'{type(error).__name__}: {error}'
    terminal=envelope(incumbent,candidate,audit,time.monotonic()-started,failure)
    write(output/'terminal.json',terminal)
    result=dict(case=row['case'],state='complete',decision=terminal['decision'],failure=failure,seconds=terminal['recovery_seconds'])
    print(json.dumps(result),flush=True);return result

if __name__=='__main__':
    verify_release()
    rows=read(ROOT/'baseline-roster.json')['cases']
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(one,[r for r in rows if r['state']=='ready']))
    write(ROOT/'baseline-execution.json',results)
