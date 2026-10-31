"""Installed ALGO05 over every usable frozen DS27 ALGO04 export; reporting only."""
import concurrent.futures
import json
import shutil
import time
from pathlib import Path
from algo03_shadow_worker import read,write
from algo04_cache import digest
from algo05_production_worker import verify_release,guarded_replay,verify_candidate,envelope
from leo.contracts.fast_graph_position_v3 import validate_terminal

ROOT=Path('/srv/bulk/leo/research/algo05-promotion-20261031/installed-ds27-v2')
INDEX=Path('/srv/bulk/leo/research/ds27-algo04-20261031/analysis-index.json')

def work(entry):
    out=ROOT/entry['case'];source=Path(entry['algo04_recovery_path'])
    terminal_path=Path(entry['terminal_path']);assert digest(terminal_path)==entry['terminal_sha256'].removeprefix('sha256:')
    incumbent=validate_terminal(read(terminal_path),input_sha256=entry['input_sha256'])
    export=out/'source-export'
    descriptor=read(export/'descriptor.json');assert descriptor['incumbent']==incumbent
    for name,h in descriptor['files'].items():assert digest(export/name)==h
    started=time.monotonic();candidate=None;audit=None;failure=None
    try:
        result=guarded_replay(out,deadline=started+1200);audit=result['read_audit']
        if result.get('selected'):candidate=verify_candidate(result,out)
    except Exception as error:failure=f'{type(error).__name__}: {error}'
    terminal=envelope(incumbent,candidate,audit,time.monotonic()-started,failure)
    write(out/'terminal.json',terminal)
    result=dict(case=entry['case'],decision=terminal['decision'],failure=failure,seconds=terminal['recovery_seconds'],
        added=len(candidate['target_ids']) if candidate else 0,read_audit_verified=bool(audit and audit['verified']))
    print(json.dumps(result),flush=True);return result

if __name__=='__main__':
    verify_release();entries=read(INDEX)['cases'];entries=[e for e in entries if e['state']=='complete']
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(work,entries))
    write(ROOT/'execution.json',results)
