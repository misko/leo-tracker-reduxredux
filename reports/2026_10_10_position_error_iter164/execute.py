"""One explicit164 slice, no retries or automatic cohort selection."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from ports import HERE,ROOT,POLICY,dependencies,search_slice,continue_slice
from inference_binding import make_loader


def admission_failure(plan,member,phase,directory,error):
    """Seal metadata/dependency failure before any scientific slice is claimed."""
    from leo.contracts.digests import canonical_digest
    path=Path(directory)/phase/'result.json';path.parent.mkdir(parents=True,exist_ok=True)
    row=dict(protocol_sha256=canonical_digest(plan),label=member['label'],
             status='failed' if phase=='search' else 'not-run-search-failed',
             reason=str(error),binding_status=member.get('binding_status'),
             binding_error=member.get('binding_error'),operational={},fallback_available=False)
    if phase!='search':row['branch']=phase
    else:row.update(complete=False,searches={},point_failures=[])
    with path.open('x') as f:json.dump(row,f,indent=2)
    return row

def verify(plan):
    interpreter='/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
    if sys.executable!=interpreter or plan['runtime']['interpreter']!=interpreter:
        raise ValueError('immutable47e executable required')
    for name,expected in plan['runtime']['sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise ValueError('runtime changed '+name)
    if plan['policy']!=POLICY:raise ValueError('runtime policy changed')
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(name)!='1':raise ValueError('singlethread required')
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('closure changed '+name)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('label');parser.add_argument('phase',choices=('search','native','zero'))
    parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json')
    parser.add_argument('--output',type=Path,default=HERE/'results')
    args=parser.parse_args();plan=json.loads(args.protocol.read_text())
    verify(plan)
    members=[m for m in plan['members'] if m['label']==args.label]
    if len(members)!=1:raise ValueError('label outside cohort')
    member=members[0]
    directory=args.output/args.label
    if member.get('binding_status')!='complete' or member.get('binding') is None:
        row=admission_failure(plan,member,args.phase,directory,
            'Inference binding failed: '+str(member.get('binding_error')))
        print(args.label,args.phase,row['status'],flush=True)
        return
    try:
        entry,driver,adapter=dependencies();loader=make_loader(entry,member)
    except Exception as error:
        row=admission_failure(plan,member,args.phase,directory,
            'Dependency admission failed: '+repr(error))
        print(args.label,args.phase,row['status'],flush=True)
        return
    if args.phase=='search':result=search_slice(plan,member,directory/'search',loader,driver)
    else:result=continue_slice(plan,member,args.phase,directory/args.phase,directory/'search',loader,driver,adapter)
    print(args.label,args.phase,result['status'],flush=True)

if __name__=='__main__':main()
