"""Bounded comparison on every track in the preceding five-case failure audit."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import sys
import hashlib
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    source=args.inclusions/'protocol.json';protocol=read(source);jobs=protocol['jobs']
    if args.resume_from:
        jobs=[job for job in jobs if read(args.resume_from/(job['track_id']+'-terminal.json'))['status']!='complete']
    if len(jobs)>5:raise ValueError('bounded prototype has at most five cases')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        workers=5,seconds_per_case=600,selection='All five previously rejected graph inclusions; no error ranking',
        models=['original','receiver_hz','receiver_fractional'],GPS_used=False,no_production_change=True,
        resume_from=str(args.resume_from) if args.resume_from else None))
    def work(job):
        tid=job['track_id'];command=[sys.executable,str(Path(__file__).with_name('probe_independent_receiver_ramps.py')),
            '--inventory',job['inventory'],'--inclusion',str(args.inclusions/tid),
            '--validation',str(Path(protocol['queue'])/tid),'--output',str(args.output/tid)]
        if args.resume_from:command+=['--resume-from',str(args.resume_from/tid)]
        result=dict(track_id=tid,scan=job['label'],command=command,**supervise(command,args.output/(tid+'.log'),600))
        write(args.output/(tid+'-terminal.json'),result);return result
    with ThreadPoolExecutor(max_workers=5) as pool:
        for future in as_completed([pool.submit(work,job) for job in jobs]):print(future.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inclusions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--resume-from',type=Path);run(p.parse_args())
