"""One explicit151 slice, no retries or automatic cohort selection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from ports import HERE,ROOT,POLICY,dependencies,search_slice,continue_slice
from inference_binding import make_loader

def verify(plan):
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
    member=members[0];entry,driver,adapter=dependencies();loader=make_loader(entry,member)
    directory=args.output/args.label
    if args.phase=='search':result=search_slice(plan,member,directory/'search',loader,driver)
    else:result=continue_slice(plan,member,args.phase,directory/args.phase,directory/'search',loader,driver,adapter)
    print(args.label,args.phase,result['status'],flush=True)

if __name__=='__main__':main()
