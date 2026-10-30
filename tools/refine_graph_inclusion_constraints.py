"""Bounded matched constrained refits of graph additions with residual failures."""
import argparse,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from probe_algo03_feasible_recovery import gate_slacks
from ds23_feasible_position import feasible_fit
from algo02_scan import pair_passes
from stress_joint_attachment import supervise
from phase_reference_checks import phase_refresh


def residual_only_jobs(jobs,audit):
    causes={}
    for r in audit['results']:
        for v in r['rows']+r['linear_rows']:
            if not v['compatible']:causes.setdefault(r['track_id'],set()).update(v['failures'])
    return [j for j in jobs if causes.get(j['track_id']) and 'multiple_orbital_owners_required' not in causes[j['track_id']]]


def one(args):
    source=read(args.source/'protocol.json');inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0']
    if source['job']['job_id']!=inv['job']['job_id']:raise ValueError('source scan mismatch')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(source,constrained_source=str(args.source),
        source_hashes={name:hashlib.sha256((args.source/name).read_bytes()).hexdigest() for name in ('control.json','target_0.json')},
        start='corresponding unconstrained endpoint; same additional budget for control and target',
        phase_rounds=5,iterations=40,gate_margin=.01,unchanged_model_priors_noise_weights_and_observations=True))
    for role in ('control','target_0'):
        initial=read(args.source/(role+'.json'));extras=initial['target_entries'];node,keep=configuration(d['node'],d['keep'],base.slices,extras)
        means,receipts=prior_means(d,node);arms={}
        for arm,r in initial['arms'].items():
            x=np.asarray(r['endpoint_east_north_km']);reference=np.asarray(r['phase_reference']);history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],node,keep,arm,reference,d['powers'],means,d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                f=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                    lambda z:np.asarray(list(gate_slacks(p,z,d['entries']).values()))-.01,x,p.lower,p.upper,iterations=40)
                x=np.asarray(f['parameters']);phase,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                change=check['phase_change_s'];reference=phase;history.append(dict(fit=f,**check))
            v=summary(p,x,d['entries']);_,_,ids,owners=memberships(p,x,d['entries']);old=set(inv['policy'][arm]['proposed_associated_ids'])
            c=p.calculate(x);diagnostics=[]
            for t in extras:
                sl=p.slices[t['row']];tr=p.scan.tracks[t['track_index']];raw=c['conditional_residual_hz'][sl]
                diagnostics.append(dict(component=t['component'],norad=t['norad'],times_s=tr['times'],CFO_hz=tr['values'],
                    predicted_CFO_hz=tr['values']-raw,residual_hz=raw,original_kept_mask=d['keep'][sl],
                    gate=next(g for g in v['gates']['tracks'] if g['component']==t['component'])))
            v.update(history=history,final_phase_change_s=change,phase_reference_check=check,proposed_associated_ids=sorted(ids),proposed_owners=owners,
                added_points=len(ids-old),lost_points=len(old-ids),targets=diagnostics,new_prior_receipts=receipts,
                minimum_gate_slack=min(gate_slacks(p,x,d['entries']).values()))
            arms[arm]=v
        valid=pair_passes(arms,include_linear=True) and all(v['lost_points']==0 and v['final_phase_change_s']<=.01 for v in arms.values())
        write(args.output/(role+'.json'),dict(job=inv['job'],arms=arms,paired_valid=valid,target_entries=extras,no_production_change=True))
        print(inv['job']['label'],role,'paired',valid,flush=True)


def run(args):
    protocol=read(args.batch/'protocol.json');audit=read(args.batch/'gate_audit.json');jobs=residual_only_jobs(protocol['jobs'],audit)
    if len(jobs)>12 or not 1<=args.workers<=8:raise ValueError('bounded to twelve jobs and eight workers')
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(jobs=jobs,source_batch=str(args.batch),workers=args.workers,seconds_per_job=360,
        selection='all failing paired trials with residual failures and no orbital-owner requirement failure',
        GPS_used=False,future_TLE=False,matched_c=True,unchanged_model=True,
        gate_audit_sha256=hashlib.sha256((args.batch/'gate_audit.json').read_bytes()).hexdigest()))
    def work(j):
        cmd=[sys.executable,__file__,'one','--source',str(args.batch/j['track_id']),'--inventory',j['inventory'],'--output',str(args.output/j['track_id'])]
        r=dict(track_id=j['track_id'],label=j['label'],command=cmd,**supervise(cmd,args.output/(j['track_id']+'.log'),360))
        write(args.output/(j['track_id']+'-terminal.json'),r);return r
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['run','one'])
    for name in ('source','inventory','batch','output'):p.add_argument('--'+name,type=Path,required=name=='output')
    p.add_argument('--workers',type=int,default=8);a=p.parse_args();run(a) if a.mode=='run' else one(a)
