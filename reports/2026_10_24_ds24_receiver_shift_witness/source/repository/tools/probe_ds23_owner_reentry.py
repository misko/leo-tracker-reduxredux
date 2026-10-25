"""Normalized fine receiver covariance plus independent-owner curve reentry.

This combination is fixed before its random-cohort position evaluation. The
0405 engineering probe motivated it; it is not evidence of generalization.
"""

import argparse
import copy
import gc
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

import probe_ds23_catalogue_reentry as search
from ds23_catalogue_reentry import complete_groups
from ds23_owner_reentry import strongest_per_owner
from ds23_receiver_family_search import fine_receiver_basis
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_consensus_growth import make
from probe_ds23_frequency_events import refit,summary
from probe_ds23_gate_retention_cohort import constrained
from probe_algo03_feasible_recovery import gate_slacks
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from ds23_causal_phase_location import adjust_means
from dbg01_unassociated import ownership
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_owner_reentry'
BULK=Path('/srv/bulk/leo/research/ds23-owner-reentry-20261021')


def prepare():
    old=read(search.OUT/'protocol.json');d={k:old[k] for k in ['engineering','development','confirmation','seed']}
    d.update(source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_owner_reentry.py','ds23_owner_reentry.py','ds23_catalogue_reentry.py','probe_ds23_catalogue_reentry.py']},
        minimum_new_owners=2,one_whole_curve_per_RX_channel='maximum point count, then duration and key',
        receiver_basis='10s spacing,15s width; average pointwise variance matched to original on fixed0..300s grid',
        complete_family_group_control='reports/2026_10_21_ds23_catalogue_reentry',
        catalogue='all original causal candidates; original nominee plus three best same-mask scores',
        original_graph_values_aliases_for_active_points_and_powers_unchanged=True,
        no_GPS_or_postscan_TLE=True,original_curved_and_predictive_evidence_retained=True,
        phase_rounds=5,position_steps=48,gate_constrained_rounds=5,constrained_steps=40,minimum_slack_trigger=-.25,
        exact_pair_incumbent_fallback=True,regional_width_km=25,cold_start=[0,0],workers=10,per_case_seconds=400,
        engineering_0405_observed_prior_to_random_cohort_evaluation=True,
        confirmation_disjoint_from_development_but_previously_studied_same_site=True)
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists() and read(path)!=d:raise ValueError('frozen owner-reentry protocol changed')
    if not path.exists():write(path,d)
    return d


def fine_view(scan):
    changed=copy.copy(scan);changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
    return changed


def run(case):
    path=BULK/(case+'.json')
    if path.exists():return dict(case=case,cached=True,status=read(path)['status'])
    protocol=prepare();started=time.monotonic();d=dict(case=case,trials=[],fine_basis=True)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('400second owner-reentry budget')));signal.alarm(400)
    try:
        scan,node,mask,powers,means,hyper,entries,signed,source=context_signed(case);inc=signed['policy_arms']
        d.update(incumbent_arms=inc,policy_arms=inc)
        p=make(scan,node,mask,'c0',inc['c0']['phase_reference'],powers,means,hyper,entries)
        delta=p.calculate(np.array(inc['c0']['endpoint_east_north_km']))['negative_twice_elbo']-inc['c0']['negative_twice_elbo']
        if abs(delta)>1e-5:raise ValueError('signed incumbent RF replay failed')
        from evaluate_ds23_phase_refreshed import extend_associations
        lookup={t['key']:t for t in scan.tracks};occupied=set()
        for arm in ARMS:
            original=make(scan,node,mask,arm,inc[arm]['phase_reference'],powers,means,hyper,entries)
            x=np.array(inc[arm]['endpoint_east_north_km']);metrics=summary(original,x,entries)['gates']
            extended=extend_associations(original,x,metrics)
            occupied.update(ownership([dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']]))
        groups=[strongest_per_owner(g,p) for g in complete_groups(p,occupied)]
        groups.sort(key=lambda g:(-g['added_points'],g['original_index'],g['rows']));groups=groups[:2]
        widths,receipts=phase_widths(scan,list(range(len(scan.norads))));allmeans=forecast_phase_mean(receipts,hyper['shrinkage'])
        if signed['accepted']:allmeans=adjust_means(allmeans,receipts,hyper,signed['selection'])
        np.testing.assert_allclose(allmeans[p.labels],means,atol=1e-12,rtol=0)
        fine=fine_view(scan);chosen=None
        for group in groups:
            offers=search.catalogue_offers(p,np.array(inc['c0']['endpoint_east_north_km']),powers,allmeans,widths,hyper,group)
            write(BULK/(case+f"_group{group['original_index']}_offers.json"),dict(group=group,offers=offers))
            mask2=mask.copy()
            for k in group['rows']:mask2[p.slices[k]]=True
            passing=[]
            for offer in offers:
                changed=copy.deepcopy(node);changed['seed']['state']['smooth']=np.zeros((2,fine.rx_basis[0].shape[1]))
                for k,alias in zip(group['rows'],offer['aliases'],strict=True):
                    changed['seed']['rows'][k].update(candidate_index=offer['candidate_index'],candidate_norad=offer['norad']);changed['aliases'][k]=alias
                labels=sorted({r['candidate_index'] for r in changed['seed']['rows']})
                if {e['candidate_index'] for e in entries}-set(labels):continue
                means2=allmeans[labels];pair={}
                for arm in ARMS:
                    pair[arm]=refit(fine,changed,mask2,arm,powers,means2,hyper,[],entries);gc.collect()
                good=valid(pair);receipt=dict(attempted=False)
                if not good:
                    minima=[]
                    for arm in ARMS:
                        q=make(fine,changed,mask2,arm,pair[arm]['phase_reference'],powers,means2,hyper,entries)
                        minima.append(min(gate_slacks(q,np.array(pair[arm]['endpoint_east_north_km']),entries).values()))
                    receipt['minimum_unconstrained_slacks']=minima
                    if min(minima)>=-.25:
                        previous=pair;pair=constrained(fine,changed,mask2,powers,means2,hyper,entries,pair)
                        good=valid(pair);receipt.update(attempted=True,unconstrained_arms=previous)
                trial=dict(group=group,offer=offer,arms=pair,paired_valid=good,mask=mask2,node=changed,means=means2,constraint_receipt=receipt)
                d['trials'].append(trial)
                if good:passing.append(trial)
                write(BULK/(case+'_checkpoint.json'),d)
            if passing:chosen=min(passing,key=lambda t:t['arms']['c0']['negative_twice_elbo']);break
        d.update(status='complete',selected=chosen,policy_arms=chosen['arms'] if chosen else inc,
            original_mask=mask,powers=powers,entries=entries,hyper=hyper,original_means=means,
            signed_incumbent_path=str(source.relative_to(ROOT)),signed_incumbent_sha256=sha(source),no_GPS=True,no_future_TLE=True)
    except Exception as exc:d.update(status='budget_exhausted' if isinstance(exc,TimeoutError) else 'failed',error=repr(exc))
    finally:signal.alarm(0)
    d['seconds']=time.monotonic()-started;d['protocol_sha256']=sha(OUT/'protocol.json');write(path,d);gc.collect()
    result=dict(case=case,status=d['status'],accepted=bool(d.get('selected')),seconds=d['seconds'],error=d.get('error'));print(result,flush=True);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','engineering','development','confirmation'],required=True)
    args=parser.parse_args();protocol=prepare()
    if args.stage=='prepare':return
    receipts=[]
    with ProcessPoolExecutor(max_workers=min(10,len(protocol[args.stage]))) as pool:
        for f in as_completed([pool.submit(run,c) for c in protocol[args.stage]]):
            receipts.append(f.result());write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,total=len(protocol[args.stage])))
    write(OUT/(args.stage+'_execution.json'),dict(receipts=receipts,all_terminal=True))


if __name__=='__main__':main()
