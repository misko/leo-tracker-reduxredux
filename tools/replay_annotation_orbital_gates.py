"""Replay unchanged fits after separating prior-only from learned orbit modes."""
import argparse
import copy
from pathlib import Path
import numpy as np
from annotate_track_predictively import prior_means,training_factory
from diagnose_all_large_tracks import context,ARMS
from debug_fast_graph_unassociated import read,write,memberships
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from algo02_scan import pair_passes


def run(args):
    for case in ['ds24-0018','ds24-0099','v02','v08']:
        pr=read(args.study/f'predictive-annotation-{case}-v1/protocol.json')
        inv=read(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
        for stem,policy,control in [('predictive-orbit','active_uncertainty',False),
                ('predictive-orbit-control','active_uncertainty',True),('predictive-target-orbit','target_uncertainty',False)]:
            out=args.study/f'{stem}-{case}-v2';out.mkdir(exist_ok=False)
            for name in ['curved_only','with_predictive']:
                source=args.study/f'{stem}-{case}-v1'/f'{name}.json';old=read(source)
                node=copy.deepcopy(d['node']);keep=d['keep'].copy();j=None;component=None
                if not control:
                    component=pr['target']['component'];p0,_=d['problems']['c0']
                    k=next(k for k,r in enumerate(p0.rows) if r['component']==component)
                    norad=old['annotation']['norad'];j=int(np.flatnonzero(d['scan'].norads==norad)[0])
                    node['seed']['rows'][k].update(candidate_index=j,candidate_norad=norad)
                    node['aliases'][k]=old['alias'];keep[p0.slices[k]]=True
                means,_=prior_means(d,node);powers=np.ones(len(d['powers']));pair={}
                for arm in ARMS:
                    saved=old['arms'][arm];x=np.array(saved['endpoint_east_north_km'])
                    p=make_event_problem(d['scan'],node,keep,arm,np.array(saved['phase_reference']),powers,means,d['model'],[],
                        base_problem_factory=training_factory(d,policy,j))
                    entries=d['entries'] if name=='with_predictive' else []
                    attach_event_predictive(p,entries,powers);cached(p);r=summary(p,x,entries)
                    for key in ['RMS_hz','negative_twice_elbo']:
                        if not np.isclose(r[key],saved[key],rtol=1e-10,atol=1e-5):raise ValueError(f'fit replay mismatch {case} {arm} {key}')
                    _,_,ids,_=memberships(p,x,entries);baseline=set(inv['policy'][arm]['proposed_associated_ids'])
                    r=dict(saved,**r,proposed_associated_ids=sorted(ids),added_points=len(ids-baseline),lost_points=len(baseline-ids),
                        failed_existing=[g['component'] for g in r['gates']['tracks'] if not g['compatible'] and g['component']!=component],
                        targets=[g for g in r['gates']['tracks'] if g['component']==component],
                        orbital_owner_gate_families=sorted(p.orbital_owner_gate_families),
                        prior_only_families=sorted(set(p.supported)-p.orbital_owner_gate_families))
                    pair[arm]=r
                passed=pair_passes(pair,include_linear=True) and all(r['lost_points']==0 for r in pair.values())
                write(out/f'{name}.json',dict(old,arms=pair,paired_valid=passed,replayed_from=str(source),
                    original_paired_valid=old['paired_valid'],fit_unchanged_verified=True,
                    gate_change='preserve incumbent two-owner requirements; added prior-only modes do not create a new owner requirement'))
                print(case,stem,name,passed,[(a,r['added_points'],r['lost_points']) for a,r in pair.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);run(p.parse_args())
