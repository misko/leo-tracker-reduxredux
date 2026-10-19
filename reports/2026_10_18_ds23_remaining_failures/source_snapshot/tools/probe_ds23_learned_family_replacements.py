"""Bounded simultaneous whole-family replacements under the causal learned prior."""

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

OUT=ROOT/'reports/2026_10_18_ds23_learned_family_replacements'


def run(case):
    started=time.monotonic();scan=final_scan(case)
    original=read(SOURCE/case/'result.json');node=original['final_node']
    learned=read(LEARNED/(case+'.json'));source=learned['results']['mean_and_distribution']
    keep=np.array(source['mask'],bool);model=learned['hyperparameters_from_pre_RF_TLE_only']
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    baseline=source['arms']['c0'];endpoint=np.array(baseline['endpoint_east_north_km'])
    p=problem(scan,node,'c0',keep,np.array(baseline['phase_reference']))
    state=baseline['state']
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
    means=forecast_phase_mean(receipts,model['shrinkage']);widths=np.array(widths)*model['multiplier']
    anchors=[endpoint,np.zeros(2)]+[np.clip(endpoint+d,-12.5,12.5) for d in ([2,0],[-2,0],[0,2],[0,-2])]
    proposals={}
    for anchor_index,anchor in enumerate(anchors):
        frequency,elevation,derivative=phase_linear_frequency(scan.geometry,*latlon(anchor))
        screens={}
        for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
            active=keep[sl]
            if not active.any():continue
            track=scan.tracks[i];q=track['rf_hz']/11.5e9;indices=scan.index[i][active]
            y=track['values']-scan.hardware(track,np.array(state['beta']))
            y-=q*scan.rx_basis[i]@np.array(state['smooth'])[track['receiver']-1]
            f=q*frequency[:,indices];d=q*derivative[:,indices]
            screens[k]=candidate_profile(y[active],f+d*means[:,None],d,elevation[:,indices],scan.radio_sigma_hz,widths)
        for incumbent in p.labels:
            members=[k for k,r in enumerate(p.rows) if r['candidate_index']==incumbent and k in screens]
            if not members:continue
            cost=sum(screens[k]['cost'] for k in members)
            ordered=[int(j) for j in np.argsort(cost) if j!=incumbent and np.isfinite(cost[j])][:2]
            for candidate in ordered:
                changes=[dict(row_index=k,candidate_index=candidate,alias=int(screens[k]['aliases'][candidate])) for k in members]
                proposal=dict(original_family_index=incumbent,original_norad=int(scan.norads[incumbent]),
                    replacement_index=candidate,replacement_norad=int(scan.norads[candidate]),changes=changes,
                    screen_cost=float(cost[candidate]),anchor_index=anchor_index)
                key=(incumbent,candidate)
                if key not in proposals or proposal['screen_cost']<proposals[key]['screen_cost']:proposals[key]=proposal
    # Two all-bank alternatives per original family; no GPS candidate whitelist.
    selected=[]
    for incumbent in p.labels:
        selected.extend(sorted([r for r in proposals.values() if r['original_family_index']==incumbent],key=lambda r:r['screen_cost'])[:2])
    trials=[];OUT.mkdir(parents=True,exist_ok=True)

    def score(changes):
        candidate_node=changed_node(scan,node,changes)
        probe=problem(scan,candidate_node,'c0',keep)
        _,r=phase_widths(scan,probe.labels);mu=forecast_phase_mean(r,model['shrinkage'])
        result=refit_start(scan,candidate_node,keep,'c0',weights,mu,model['multiplier'],model['nu'],[0.,0.])
        return dict(changes=changes,record=result,valid=all(t['compatible'] for t in result['gates']['tracks']),
            selection_loss=result['negative_twice_elbo'])

    for proposal in selected:
        trial=score(proposal['changes']);trial['proposal']=proposal;trials.append(trial)
        print(case,'whole-family single',len(trials),'valid',trial['valid'],'ELBO',round(trial['selection_loss'],3),flush=True)
    pool=[];families=set()
    for trial in sorted(trials,key=lambda r:(not r['valid'],r['selection_loss'])):
        incumbent=trial['proposal']['original_family_index']
        if incumbent not in families:pool.append(trial);families.add(incumbent)
        if len(pool)==6:break
    joint=[];truncated=False
    for size in (2,3):
        for combination in itertools.combinations(pool,size):
            if time.monotonic()-started>270:truncated=True;break
            changes=[c for trial in combination for c in trial['changes']]
            result=score(changes);joint.append(result)
            print(case,'simultaneous families',size,len(joint),'valid',result['valid'],'ELBO',round(result['selection_loss'],3),flush=True)
        if truncated:break
    candidates=[r for r in trials+joint if r['valid']]
    best=min(candidates,key=lambda r:r['selection_loss']) if candidates else None
    baseline_loss=baseline['negative_twice_elbo']
    accepted=best is not None and best['selection_loss']<baseline_loss
    finalists={}
    if best is not None:
        candidate_node=changed_node(scan,node,best['changes']);probe=problem(scan,candidate_node,'c0',keep)
        _,r=phase_widths(scan,probe.labels);mu=forecast_phase_mean(r,model['shrinkage'])
        finalists={arm:refit_start(scan,candidate_node,keep,arm,weights,mu,model['multiplier'],model['nu'],[0.,0.]) for arm in ('c0','fitted_c')}
        accepted=accepted and all(t['compatible'] for r in finalists.values() for t in r['gates']['tracks'])
    write(OUT/(case+'.json'),dict(case=case,single_trials=trials,joint_trials=joint,best=best,
        best_paired_finalists=finalists,accepted_over_incumbent=accepted,baseline_loss=baseline_loss,
        fixed_mask=keep,weights_frozen_for_control=True,GPS_used=False,elapsed_s=time.monotonic()-started,
        joint_budget_truncated=truncated,candidate_count=len(scan.norads),proposal_anchors=anchors,
        source_sha256=sha(Path(__file__)),prior_input_sha256=sha(LEARNED/(case+'.json')),
        no_exhaustiveness_claim=True,
        screen_is_gaussian_phase_constant_approximation_final_fit_has_full_learned_prior=True,
        diagnostic_not_a_promoted_replacement_policy=True))
    print(case,'done accepted',accepted,'single',len(trials),'joint',len(joint),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
