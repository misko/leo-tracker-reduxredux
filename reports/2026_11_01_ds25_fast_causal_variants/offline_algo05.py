"""Exact installed ALGO05 replay from a hash-checked private ALGO04 export."""
import argparse,time,json
from pathlib import Path
from offline_algo04 import export_recovery
from algo05_production_worker import verify_release,guarded_replay,verify_candidate,envelope
from algo03_shadow_worker import read,write
from leo.contracts.fast_graph_position_v3 import validate_terminal

def run(a):
    verify_release();start=time.monotonic();inc=read(a.source_terminal)
    validate_terminal(inc,input_sha256=inc['input_sha256'])
    a.output.mkdir(parents=True,exist_ok=True)
    if (a.output/'source-export/descriptor.json').exists():
        from offline_algo04 import digest
        descriptor=read(a.output/'source-export/descriptor.json')
        assert descriptor['incumbent']==inc
        assert all(digest(a.output/'source-export'/n)==h for n,h in descriptor['files'].items())
        assert not (a.output/'launch.json').exists(), 'Resume is only allowed before numerical execution'
    else:
        descriptor,_,_=export_recovery(a.source_terminal,a.source_recovery,a.output/'source-export',inc)
    # The byte-copy helper was first written for V2; this export is explicitly V3.
    descriptor['model_version']=inc['model_version']
    (a.output/'source-export/descriptor.json').write_text(json.dumps(descriptor,indent=2,allow_nan=False)+'\n')
    candidate=None;audit=None;failure=None
    try:
        result=guarded_replay(a.output,deadline=start+1200);audit=result['read_audit']
        if result.get('selected'):candidate=verify_candidate(result,a.output)
    except Exception as e:failure=f'{type(e).__name__}: {e}'
    t=envelope(inc,candidate,audit,time.monotonic()-start,failure)
    write(a.output/'terminal.json',t)
    print(json.dumps(dict(state='complete',decision=t['decision'],failure=failure)),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source-terminal','source-recovery','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
