"""Two matched numerical reference limits for a diagnosed clipped-phase case."""
import argparse,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from debug_fast_graph_unassociated import read,write
from stress_joint_attachment import supervise


def run(args):
    source=read(args.source/'protocol.json');inv=read(args.inventory)
    if source['job']['job_id']!=inv['job']['job_id'] or len(source['targets'])!=1:raise ValueError('one matched diagnosed target required')
    target=source['targets'][0];job=dict(track_id=target['track_id'],label=inv['job']['label'],inventory=str(args.inventory))
    args.output.mkdir(parents=True,exist_ok=False);variants=[]
    for limit in (15,30):
        name='reference'+str(limit);root=args.output/name;root.mkdir()
        write(root/'protocol.json',dict(jobs=[job],reference_limit_s=limit,original_model=True,GPS_used=False,future_TLE=False))
        variants.append(dict(name=name,reference_limit_s=limit))
    write(args.output/'protocol.json',dict(job=job,variants=variants,workers=2,seconds_per_job=360,
        source=str(args.source),source_hashes={name:hashlib.sha256((args.source/name).read_bytes()).hexdigest() for name in ('protocol.json','control.json','target_0.json')},
        selection='diagnosed false convergence and exact-orbit mismatch; not position error',
        matched_starts_observations_candidates_priors_and_budgets=True,phase_prior_unchanged=True,
        bank_extension=False,new_TLE=False,reference_domain_checked_before_every_update=True))
    def work(v):
        root=args.output/v['name'];cmd=[sys.executable,str(Path(__file__).with_name('refine_graph_inclusion_constraints.py')),'one',
            '--source',str(args.source),'--inventory',str(args.inventory),'--output',str(root/job['track_id']),
            '--reference-limit-s',str(v['reference_limit_s'])]
        r=dict(job,variant=v,command=cmd,**supervise(cmd,root/(job['track_id']+'.log'),360))
        write(root/(job['track_id']+'-terminal.json'),r);return r
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(work,v) for v in variants]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','inventory','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
