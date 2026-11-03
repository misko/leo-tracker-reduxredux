"""Bounded all-catalogue proposals and simultaneous two/three/four-family fits."""

import argparse
import itertools
import time
from pathlib import Path
import numpy as np
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import candidate_profile,changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_learned_prior_restarts import refit_start
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

OUT=ROOT/'reports/2026_10_19_ds23_joint_family_search'


def joint_operations(singles,max_families=4,alternatives=2):
    """Retain alternatives even when their isolated fit fails a shared gate."""
    ranked=sorted(singles,key=lambda r:(not r['valid'],r['loss'],r['source'],r['target']))
    families=list(dict.fromkeys(r['source'] for r in ranked))[:max_families]
    pools={j:sorted([r for r in singles if r['source']==j],key=lambda r:r['loss'])[:alternatives] for j in families}
    result=[]
    for size in range(2,len(families)+1):
        for group in itertools.combinations(families,size):
            for choices in itertools.product(*(pools[j] for j in group)):
                result.append([c for r in choices for c in r['changes']])
    return result


def run(case):
    started=time.monotonic();scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution'];baseline=primary['arms']['c0']
    keep=np.array(primary['mask'],bool);model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    p=problem(scan,node,'c0',keep,np.array(baseline['phase_reference']));state=baseline['state']
    endpoint=np.array(baseline['endpoint_east_north_km'])
    anchors=[endpoint,np.zeros(2)]+[np.clip(endpoint+d,-12.5,12.5) for d in ([2,0],[-2,0],[0,2],[0,-2])]
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
    means=forecast_phase_mean(receipts,model['shrinkage']);widths=np.array(widths)*model['multiplier']
    proposals={}
    for anchor_index,anchor in enumerate(anchors):
        frequency,elevation,derivative=phase_linear_frequency(scan.geometry,*latlon(anchor));screens={}
        for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
            active=keep[sl]
            if not active.any():continue
            track=scan.tracks[i];q=track['rf_hz']/11.5e9;indices=scan.index[i][active]
            y=track['values']-scan.hardware(track,np.array(state['beta']))
            y-=q*scan.rx_basis[i]@np.array(state['smooth'])[track['receiver']-1]
            screens[k]=candidate_profile(y[active],q*(frequency[:,indices]+derivative[:,indices]*means[:,None]),
                q*derivative[:,indices],elevation[:,indices],scan.radio_sigma_hz,widths)
        for incumbent in p.labels:
            members=[k for k,r in enumerate(p.rows) if r['candidate_index']==incumbent]
            active_members=[k for k in members if k in screens]
            if not active_members:continue
            cost=sum(screens[k]['cost'] for k in active_members)
            ordered=[int(j) for j in np.argsort(cost) if j!=incumbent and np.isfinite(cost[j])][:3]
            for j in ordered:
                # Inactive fragments move with their whole family; their aliases
                # do not affect the frozen-observation likelihood.
                changes=[dict(row_index=k,candidate_index=j,alias=int(screens[k]['aliases'][j]) if k in screens else int(node['aliases'][k])) for k in members]
                record=dict(source=int(incumbent),target=j,changes=changes,screen_cost=float(cost[j]),anchor=anchor_index)
                key=(incumbent,j)
                if key not in proposals or record['screen_cost']<proposals[key]['screen_cost']:proposals[key]=record
    selected=[]
    for j in p.labels:
        selected.extend(sorted([r for r in proposals.values() if r['source']==j],key=lambda r:r['screen_cost'])[:3])
    singles=[];joint=[];OUT.mkdir(parents=True,exist_ok=True)

    def score(changes):
        candidate=changed_node(scan,node,changes);probe=problem(scan,candidate,'c0',keep)
        _,receipt=phase_widths(scan,probe.labels);mu=forecast_phase_mean(receipt,model['shrinkage'])
        r=refit_start(scan,candidate,keep,'c0',powers,mu,model['multiplier'],model['nu'],[0.,0.])
        return dict(changes=changes,record=r,loss=r['negative_twice_elbo'],
                    valid=all(t['compatible'] for t in r['gates']['tracks']))

    for proposal in selected:
        r=score(proposal['changes']);r.update(source=proposal['source'],target=proposal['target'],screen=proposal)
        singles.append(r)
    operations=joint_operations(singles)
    for changes in operations:
        joint.append(score(changes))
        if len(joint)%12==0:print(case,'joint',len(joint),'of',len(operations),flush=True)
    improved=sorted([r for r in singles+joint if r['valid'] and r['loss']<baseline['negative_twice_elbo']-1e-7],key=lambda r:r['loss'])
    paired=[];chosen=None
    for proposal in improved[:5]:
        candidate=changed_node(scan,node,proposal['changes']);probe=problem(scan,candidate,'c0',keep)
        _,receipt=phase_widths(scan,probe.labels);mu=forecast_phase_mean(receipt,model['shrinkage'])
        arms={arm:refit_start(scan,candidate,keep,arm,powers,mu,model['multiplier'],model['nu'],[0.,0.]) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for r in arms.values() for t in r['gates']['tracks'])
        paired.append(dict(changes=proposal['changes'],arms=arms,valid=valid))
        if valid:chosen=paired[-1];break
    best=min([r for r in singles+joint if r['valid']],key=lambda r:r['loss'],default=None)
    write(OUT/(case+'.json'),dict(case=case,singles=singles,joint=joint,paired_finalists=paired,chosen=chosen,
        baseline=primary['arms'],policy_arms=primary['arms'] if chosen is None else chosen['arms'],best_valid=best,
        candidate_count=len(scan.norads),anchors=anchors,fixed_mask=keep,powers=powers,GPS_used=False,
        source_sha256=sha(Path(__file__)),learned_input_sha256=sha(LEARNED/(case+'.json')),
        seconds=time.monotonic()-started,maximum_simultaneous_families=4,alternatives_per_joint_family=2,
        all_single_proposals_evaluated=len(selected),all_planned_joint_operations_evaluated=len(operations),
        same_causal_catalogue_and_physical_priors=True,no_exhaustiveness_claim=True,
        selection_uses_normalized_c0_ELBO_and_paired_gates=True,original_points_never_trimmed=True))
    print(case,'complete',len(singles),len(joint),'chosen',chosen is not None,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
