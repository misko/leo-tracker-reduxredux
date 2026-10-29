"""Advance frozen native-branch annotations in bounded, nonduplicating batches."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
from debug_fast_graph_unassociated import read, write
from stress_joint_attachment import supervise


def select_jobs(eligible, previous, limit, allow_same_scan=False):
    if not 1 <= limit <= 8:
        raise ValueError('bounded batch requires 1..8 jobs')
    claimed={j['branch']['branch_id'] for j in previous}
    seen_scans={j['job']['job_id'] for j in previous}
    remaining=[j for j in eligible if j['branch']['branch_id'] not in claimed]
    remaining.sort(key=lambda j:(j['job']['job_id'] in seen_scans,-j['branch']['points'],j['branch']['branch_id']))
    selected=[];scans=set()
    for j in remaining:
        if not allow_same_scan and j['job']['job_id'] in scans:continue
        selected.append(j);scans.add(j['job']['job_id'])
        if len(selected)==limit:break
    return selected


def run(args):
    previous=[]
    for path in args.previous:
        previous.extend(read(path/'protocol.json')['jobs'])
    eligible=read(args.cohort/'protocol.json')['all_eligible']
    jobs=select_jobs(eligible,previous,args.limit,args.allow_same_scan)
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,previous=[str(p) for p in args.previous],eligible_cohort=str(args.cohort),
        selection='Unclaimed branches, unseen scans first, points descending',
        allow_same_scan=args.allow_same_scan,
        workers=8,seconds_per_case=600,distinct_partitions=True,phase_step_s=.025,
        preserves_all_previous_claims=True,GPS_used=False,future_TLE=False))
    def work(j):
        bid=j['branch']['branch_id'];command=[sys.executable,str(Path(__file__).with_name('annotate_predictive_only.py')),
            '--inventory',j['job']['inventory'],'--track',bid,'--native-branches',j['source'],
            '--output',str(args.output/bid),'--distinct-partitions','--uncalibrated-phase-mixture','--phase-step','.025']
        r=dict(job=j,command=command,**supervise(command,args.output/(bid+'.log'),600))
        write(args.output/(bid+'-terminal.json'),r)
        return dict(scan=j['job']['label'],branch_id=bid,status=r['status'],seconds=r['seconds'])
    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(work,j) for j in jobs]):print(future.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['cohort','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--previous',type=Path,nargs='+',required=True);p.add_argument('--limit',type=int,default=8)
    p.add_argument('--allow-same-scan',action='store_true',help='Fill bounded batches with distinct alternatives from the same scan')
    run(p.parse_args())
