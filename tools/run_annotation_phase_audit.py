"""Bounded retrospective audit, prioritizing recovery candidates and DS24."""
import argparse,csv,hashlib,sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def select(rows,members,recovered,claimed,limit):
    eligible=[r for r in rows if r['state']=='conditionally_supported_identity' and members.get(r['track_id'],False)
        and not r.get('phase_audit_source') and r['track_id'] not in claimed]
    eligible.sort(key=lambda r:(r['track_id'] not in recovered,'DS24' not in r['scopes'],-int(r['points']),r['track_id']))
    return eligible[:limit]


def run(args):
    if not 1<=args.limit<=32 or not 1<=args.workers<=12:raise ValueError('bounded to 32 tracks and twelve workers')
    rows=list(csv.DictReader(args.ledger.open()));members={r['track_id']:r['engine_member'] for r in read(args.queue/'protocol.json')['rows']}
    recovered=set();recovery_sources=[]
    for root in sorted(args.study.glob('graph-inclusion-batch*-v1')):
        protocol=root/'protocol.json'
        if not protocol.exists():continue
        for j in read(protocol)['jobs']:
            path=root/j['track_id']/'target_0.json'
            if path.exists() and read(path)['paired_valid']:
                recovered.add(j['track_id']);recovery_sources.append(str(path))
    args.output.mkdir(parents=True,exist_ok=True)
    claimed={j['track_id'] for path in args.output.glob('attempt-*/protocol.json') for j in read(path)['jobs']}
    selected=select(rows,members,recovered,claimed,args.limit);attempt=args.output/f'attempt-{len(list(args.output.glob("attempt-*")))+1}';attempt.mkdir()
    jobs=[dict(track_id=r['track_id'],label=r['label'],annotation=str(Path(r['annotation_source']).parent),
        points=int(r['points']),previous_full_data_candidate=r['track_id'] in recovered) for r in selected]
    hashes={str(args.ledger):hashlib.sha256(args.ledger.read_bytes()).hexdigest()}
    for j in jobs:
        for name in ('protocol.json','result.json'):
            path=Path(j['annotation'])/name;hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(attempt/'protocol.json',dict(jobs=jobs,workers=args.workers,seconds_per_job=180,source_hashes=hashes,
        priority='prior paired-passing graph candidates, then DS24, then remaining supported identities; points descending',
        previous_candidate_sources=recovery_sources,claim_preservation=True,GPS_used=False,no_reoptimization=True,
        remaining_supported_eligible=len(select(rows,members,recovered,claimed,10**9))))
    def work(j):
        out=attempt/(j['track_id']+'.json');cmd=[sys.executable,str(Path(__file__).with_name('audit_annotation_phase.py')),
            '--annotations',j['annotation'],'--inventories',str(args.inventories),'--output',str(out)]
        row=dict(j,command=cmd,**supervise(cmd,attempt/(j['track_id']+'.log'),180))
        write(attempt/(j['track_id']+'-terminal.json'),row);return row
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ledger','queue','study','inventories','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--limit',type=int,default=32);p.add_argument('--workers',type=int,default=12);run(p.parse_args())
