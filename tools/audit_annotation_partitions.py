"""Timestamp-only audit of existing and alternative randomized track partitions."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from leo.analysis.research.grouped_prediction import grouped_split,replay_split,geometry_partition_schedule
from stress_joint_attachment import supervise

SEEDS=[20261029,94721,4081]
POOL=SEEDS+np.random.default_rng(20261029).integers(0,2**31-1,64).tolist()


def one(args):
    args.output.mkdir(parents=True,exist_ok=False);job=read(args.job);inv=read(job['inventory']);d=context(inv);p,_=d['problems']['c0'];rows=[]
    for row in job['rows']:
        track=d['scan'].tracks[row['track_index']];focus=track['times'];times=p.flat_times if row['engine_member'] else np.r_[p.flat_times,focus]
        original=[]
        if len(np.unique(np.floor(focus/12)))>=3:
            for seed in SEEDS:
                _,_,split=grouped_split(times,focus,seed=seed);train,held=replay_split(focus,split)
                original.append(dict(seed=seed,train=int(train.sum()),held=int(held.sum()),usable=bool(train.sum()>=8 and held.sum()>=4),
                    target_held_blocks=sorted(set(np.floor(focus[held]/12).astype(int).tolist()))))
        schedule=geometry_partition_schedule(times,focus,seeds=POOL)
        rows.append(dict(track_id=row['track_id'],component=row['component'],label=row['label'],points=len(focus),
            engine_member=row['engine_member'],times_s=focus,original=original,
            original_distinct_usable=len({tuple(r['target_held_blocks']) for r in original if r['usable']}),schedule=schedule))
    write(args.output/'result.json',dict(job=inv['job'],rows=rows,only_timestamps_used=True,seed_pool=POOL,block_s=12,guard_s=2,
        original_source=str(args.job),no_identity_or_position_selection=True))


def batch(args):
    args.output.mkdir(parents=True,exist_ok=False);groups=defaultdict(list)
    for r in read(args.study/'systematic-annotation-v1/protocol.json')['rows']:
        if 'DS24' in r['scopes']:groups[r['job_id']].append(r)
    jobs=[]
    for jobid,rows in groups.items():
        job=dict(job_id=jobid,inventory=rows[0]['inventory'],rows=rows);path=args.output/(jobid+'-job.json');write(path,job);jobs.append(dict(job_id=jobid,path=str(path)))
    write(args.output/'protocol.json',dict(jobs=jobs,workers=8,seconds_per_scan=300,scope='all 289 inventoried DS24 tracks',
        seed_pool=POOL,block_s=12,guard_s=2,minimum_target_train=8,minimum_target_held=4,required_distinct_target_holdouts=3,
        selection_uses_times_only=True))
    def work(j):
        r=supervise([sys.executable,str(Path(__file__)),'one','--job',j['path'],'--output',str(args.output/j['job_id'])],args.output/(j['job_id']+'.log'),300)
        write(args.output/(j['job_id']+'-terminal.json'),dict(job=j,**r));return j['job_id'],r['status']
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['one','batch'])
    p.add_argument('--study',type=Path);p.add_argument('--job',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();batch(a) if a.mode=='batch' else one(a)
