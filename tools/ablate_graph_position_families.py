"""Matched deletion of RF-influential incumbent families around an addition."""
import argparse,sys,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import defaultdict
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from phase_reference_checks import phase_refresh
from algo02_scan import pair_passes
from stress_joint_attachment import supervise


def omit_family(keep,rows,slices,entries,norad):
    mask=np.array(keep,bool,copy=True)
    for row,sl in zip(rows,slices,strict=True):
        if row['candidate_norad']==norad:mask[sl]=False
    return mask,[e for e in entries if e['norad']!=norad]


def one(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0'];saved=read(args.trial/'target_0.json');target=saved['target_entries'][0]
    if args.omit==target['norad']:raise ValueError('target omitted from comparison')
    keep,entries=omit_family(d['keep'],base.rows,base.slices,d['entries'],args.omit)
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=inv['job'],target=target,omitted_norad=args.omit,
        same_omission_control_target_both_c=True,complete_curved_and_predictive_family_omission=True,
        start=[0,0],box_width_km=25,phase_rounds=5,iterations=48,GPS_used=False,future_TLE=False,
        diagnostic_only=True,no_production_change=True))
    baseline={}
    for arm,(p,x) in d['problems'].items():
        _,_,ids,owners=memberships(p,x,d['entries']);baseline[arm]={oid for oid in ids if owners[oid]!=args.omit}
    for role,targets in [('control',[]),('target_0',[target])]:
        node,active=configuration(d['node'],keep,base.slices,targets);means,_=prior_means(d,node);arms={}
        for arm in ('c0','fitted_c'):
            x=np.zeros(2);reference=np.zeros(len(means));history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],node,active,arm,reference,d['powers'],means,d['model'],[],**kw)
                attach_event_predictive(p,entries,d['powers']);cached(p);f=fit(p,x,iterations=48);x=np.asarray(f['parameters'])
                reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference);history.append(dict(fit=f,**check))
            v=summary(p,x,entries);_,_,ids,owners=memberships(p,x,entries)
            if args.omit in owners.values():raise ValueError('omitted family remains associated')
            v.update(history=history,final_phase_change_s=check['phase_change_s'],phase_reference_check=check,
                proposed_associated_ids=sorted(ids),proposed_owners=owners,remaining_incumbent_points_lost=len(baseline[arm]-ids))
            arms[arm]=v
        passed=pair_passes(arms,include_linear=True) and all(v['final_phase_change_s']<=.01 and not v['remaining_incumbent_points_lost'] for v in arms.values())
        write(args.output/(role+'.json'),dict(job=inv['job'],omitted_norad=args.omit,arms=arms,paired_valid=passed,target_entries=targets,no_accepted_associations=True))
        print(inv['job']['label'],args.omit,role,passed,flush=True)


def run(args):
    r=read(args.influence/'result.json');rank=defaultdict(float)
    for arm in r['arms'].values():
        local=defaultdict(float)
        for c in arm['changes']:local[c['norad']]+=c['residual_energy_change']
        for norad,change in local.items():rank[norad]+=abs(change)
    selected=sorted(rank,key=lambda n:(-rank[n],n))[:4]
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=r['job'],jobs=selected,ranking=[dict(norad=n,absolute_energy_change=rank[n]) for n in sorted(rank,key=lambda n:-rank[n])],
        selection='four largest absolute incumbent residual-energy changes summed across c arms; no GPS ranking',
        source_hash=hashlib.sha256((args.influence/'result.json').read_bytes()).hexdigest(),workers=4,seconds_per_job=360))
    def work(n):
        cmd=[sys.executable,__file__,'one','--inventory',str(args.inventory),'--trial',str(args.trial),'--omit',str(n),'--output',str(args.output/str(n))]
        v=dict(norad=n,command=cmd,**supervise(cmd,args.output/(str(n)+'.log'),360));write(args.output/(str(n)+'-terminal.json'),v);return v
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,n) for n in selected]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['one','run'])
    for name in ('inventory','trial','influence','output'):p.add_argument('--'+name,type=Path,required=name!='influence')
    p.add_argument('--omit',type=int);a=p.parse_args();run(a) if a.mode=='run' else one(a)
