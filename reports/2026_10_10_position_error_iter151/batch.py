"""Two explicit serial shards; durable pending receipts only, no retries."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from execute import HERE,verify

TERMINAL={'complete','failed','incomplete','budget-exhausted','not-run-search-failed'}

def run_member(member,invoke,read_status):
    result={}
    for phase,maximum in (('search',6),('native',2),('zero',2)):
        status=read_status(member['label'],phase)
        for _ in range(maximum):
            if status in TERMINAL:break
            if status not in (None,'pending'):raise ValueError('unknown authoritative status')
            status=invoke(member['label'],phase)
        if status not in TERMINAL:raise ValueError('phase exhausted without terminal receipt')
        result[phase]=status
    return result

def member_receipt(member, invoke, read_status):
    """Preserve controller failure without inventing scientific endpoints."""
    try:
        return dict(label=member['label'], phases=run_member(member, invoke, read_status))
    except Exception as error:
        return dict(label=member['label'], controller_failure=repr(error))

def authoritative_status(directory,label,phase,digest):
    folder=Path(directory)/label/phase
    path=folder/'result.json'
    if path.exists():
        row=json.loads(path.read_text())
        if row['protocol_sha256']!=digest or row.get('label')!=label:raise ValueError('foreign result')
        if phase!='search' and row.get('branch')!=phase:raise ValueError('swapped branch')
        return row['status']
    # Missing result is pending only when every previous claim finished.
    slices=folder/'slices';claims=sorted(slices.glob('*.started.json'))
    if not claims:return None
    for claim in claims:
        row=json.loads(claim.read_text())
        if row['protocol_sha256']!=digest:raise ValueError('foreign claim')
    done=sorted(slices.glob('*.finished.json' if phase=='search' else '*.done.json'))
    if len(done)!=len(claims):raise ValueError('claimed slice without finish; no retry')
    last=json.loads(done[-1].read_text())
    if last['protocol_sha256']!=digest or last['status']!='pending':raise ValueError('missing authoritative terminal')
    return 'pending'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('shard',type=int,choices=(0,1))
    parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json');parser.add_argument('--output',type=Path,default=HERE/'results')
    args=parser.parse_args();plan=json.loads(args.protocol.read_text());verify(plan)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan);args.output.mkdir(parents=True,exist_ok=True)
    terminal=args.output/f'batch-{args.shard}.json'
    if terminal.exists():
        if json.loads(terminal.read_text())['protocol_sha256']!=digest:raise ValueError('foreign batch')
        return
    with (args.output/f'batch-{args.shard}.claim.json').open('x') as f:json.dump(dict(protocol_sha256=digest,shard=args.shard),f)
    def read(label,phase):return authoritative_status(args.output,label,phase,digest)
    def invoke(label,phase):
        subprocess.run([sys.executable,str(HERE/'execute.py'),label,phase,'--protocol',str(args.protocol),'--output',str(args.output)],check=True)
        status=read(label,phase)
        if status is None:raise ValueError('process produced no authoritative receipt')
        return status
    rows=[]
    for member in plan['members'][args.shard::2]:
        rows.append(member_receipt(member,invoke,read))
    with terminal.open('x') as f:json.dump(dict(protocol_sha256=digest,shard=args.shard,members=rows),f,indent=2)

if __name__=='__main__':main()
