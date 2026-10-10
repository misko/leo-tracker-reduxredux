"""Explicit resource batches, two serial shards, authoritative slices only."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from execute import HERE,verify

TERMINAL={'complete','failed','incomplete','budget-exhausted','not-run-search-failed'}


def authoritative_status(directory,label,phase,digest):
    folder=Path(directory)/label/phase;path=folder/'result.json'
    if path.exists():
        row=json.loads(path.read_text())
        if row.get('protocol_sha256')!=digest or row.get('label')!=label:
            raise ValueError('foreign result')
        if phase!='search' and row.get('branch')!=phase:raise ValueError('swapped branch')
        if row.get('status') not in TERMINAL:raise ValueError('nonterminal result')
        return row['status']
    slices=folder/'slices';claims=sorted(slices.glob('*.started.json'))
    suffix='.finished.json' if phase=='search' else '.done.json'
    done=sorted(slices.glob('*'+suffix))
    expected={p.name.replace('.started.json',suffix) for p in claims}
    if {p.name for p in done}!=expected:
        raise ValueError('orphan/mismatched slice; no retry')
    if not claims:return None
    for claim in claims:
        row=json.loads(claim.read_text());finish=claim.with_name(claim.name.replace('.started.json',suffix))
        completed=json.loads(finish.read_text())
        if row.get('protocol_sha256')!=digest or completed.get('protocol_sha256')!=digest:
            raise ValueError('foreign slice')
        if phase!='search':
            if completed.get('label')!=label or completed.get('branch')!=phase:
                raise ValueError('foreign completed slice')
            if 'slice' in row and completed.get('slice')!=row['slice']:
                raise ValueError('mismatched slice number')
        if completed.get('status')!='pending':raise ValueError('missing terminal result')
    return 'pending'


def run_member(member,invoke,read_status):
    phases={}
    for phase,cap in (('search',6),('native',2),('zero',2)):
        status=read_status(member['label'],phase)
        for _ in range(cap):
            if status in TERMINAL:break
            if status not in (None,'pending'):raise ValueError('unknown phase status')
            status=invoke(member['label'],phase)
        if status not in TERMINAL:raise ValueError('phase exhausted without terminal receipt')
        phases[phase]=status
    return phases


def validate_batches(plan):
    labels=[m['label'] for m in plan['members']];batches=plan['execution_batches']
    flattened=[label for batch in batches for label in batch]
    if len(labels)!=193 or len(set(labels))!=193 or len(flattened)!=193 or set(flattened)!=set(labels):
        raise ValueError('exact193 partition required')
    if not batches or len(batches[0])!=4 or any(len(b)!=16 for b in batches[1:-1]) or not 1<=len(batches[-1])<=16:
        raise ValueError('resource batch sizes differ')
    return {m['label']:m for m in plan['members']}


def prior_batches(directory,index,digest,batches):
    for previous in range(index):
        for shard in (0,1):
            path=Path(directory)/f'batch-{previous}-shard-{shard}.json'
            row=json.loads(path.read_text())
            claim=json.loads(path.with_name(path.stem+'.claim.json').read_text())
            if any(claim.get(k)!=v for k,v in dict(protocol_sha256=digest,batch=previous,shard=shard).items()):
                raise ValueError('foreign prior batch claim')
            if row.get('protocol_sha256')!=digest or row.get('batch')!=previous or row.get('shard')!=shard:
                raise ValueError('foreign prior batch')
            if any('controller_failure' in member for member in row.get('members',[])):
                raise ValueError('prior controller failure requires root review')
            if row.get('status')!='terminal':raise ValueError('prior resource checkpoint not terminal')
            if [m.get('label') for m in row.get('members',[])]!=batches[previous][shard::2]:
                raise ValueError('prior checkpoint member coverage differs')
            if any(set(m.get('phases',{}))!={'search','native','zero'}
                   or any(s not in TERMINAL for s in m['phases'].values())
                   for m in row['members']):
                raise ValueError('prior checkpoint lacks terminal phases')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('shard',type=int,choices=(0,1))
    parser.add_argument('--batch',type=int,required=True)
    parser.add_argument('--protocol',type=Path,default=HERE/'protocol.json')
    parser.add_argument('--output',type=Path,default=HERE/'results')
    args=parser.parse_args();plan=json.loads(args.protocol.read_text());verify(plan)
    members=validate_batches(plan)
    if not 0<=args.batch<len(plan['execution_batches']):raise ValueError('batch outside frozen inventory')
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan);args.output.mkdir(parents=True,exist_ok=True)
    prior_batches(args.output,args.batch,digest,plan['execution_batches'])
    identity=dict(protocol_sha256=digest,batch=args.batch,shard=args.shard)
    terminal=args.output/f'batch-{args.batch}-shard-{args.shard}.json'
    if terminal.exists():
        row=json.loads(terminal.read_text())
        if any(row.get(k)!=v for k,v in identity.items()):raise ValueError('foreign batch')
        claim=json.loads(terminal.with_name(terminal.stem+'.claim.json').read_text())
        if any(claim.get(k)!=v for k,v in identity.items()):raise ValueError('foreign batch claim')
        if row.get('status')!='terminal' or any('controller_failure' in m for m in row.get('members',[])):
            raise ValueError('failed controller cannot be reused')
        if [m.get('label') for m in row.get('members',[])]!=plan['execution_batches'][args.batch][args.shard::2]:
            raise ValueError('batch member coverage differs')
        if any(set(m.get('phases',{}))!={'search','native','zero'} or any(s not in TERMINAL for s in m['phases'].values()) for m in row['members']):
            raise ValueError('batch phase coverage differs')
        return
    claim=terminal.with_name(terminal.stem+'.claim.json')
    with claim.open('x') as f:json.dump(identity,f)
    def read(label,phase):return authoritative_status(args.output,label,phase,digest)
    def invoke(label,phase):
        subprocess.run([sys.executable,str(HERE/'execute.py'),label,phase,'--protocol',str(args.protocol),'--output',str(args.output)],check=True)
        status=read(label,phase)
        if status is None:raise ValueError('child produced no authoritative receipt')
        return status
    rows=[]
    for label in plan['execution_batches'][args.batch][args.shard::2]:
        try:row=dict(label=label,phases=run_member(members[label],invoke,read))
        except Exception as error:
            rows.append(dict(label=label,controller_failure=repr(error)));break
        rows.append(row)
    status='controller-failed' if any('controller_failure' in r for r in rows) else 'terminal'
    with terminal.open('x') as f:json.dump(dict(identity,status=status,members=rows),f,indent=2)


if __name__=='__main__':main()
