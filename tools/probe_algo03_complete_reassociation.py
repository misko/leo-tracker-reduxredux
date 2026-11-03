"""Compare cold-discovered hypotheses on identical curved and predictive data.

Unlike DBG01's conditional restart pool, predictive identities can change.
No measurement, prior, alias period, residual gate or reference site is altered.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_predictive_reassociation import proposal_pools,select_assignment,block_objective
from ds23_predictive_linear import attach_predictive_linear
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context as load_context,refit as curved_refit,SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state
from run_dsx01_joint_descent import signature
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

DBG=ROOT/'reports/2026_10_20_dbg01_algo02_ds23_0268'
OUT=ROOT/'reports/2026_10_20_algo03_complete_reassociation_v2'
ARMS=('c0','fitted_c')


@lru_cache(maxsize=2)
def context(case):return load_context(case)


def build(scan,node,keep,arm,reference,powers,means,model,entries=()):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    attach_predictive_linear(p,entries,powers);calculate=p.calculate
    @lru_cache(maxsize=8)
    def cached(x):return calculate(np.asarray(x))
    p.calculate=lambda x:cached(tuple(np.asarray(x,float)))
    return p


def summarize(p,x,entries,history):
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;linear=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=p.scan.tracks[e['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*p.scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0)
        linear.append(dict(component=e['component'],norad=e['norad'],points=e['points'],
            observation_ids=e['observation_ids'],compatible=valid,rms_hz=float(terms['rms'][0]),
            bias_hz=float(terms['bias'][0]),noise={k:v[0] for k,v in noise.items()}))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),phase_reference=p.reference,state=p.state(x),
        history=history,final_phase_change_s=history[-1]['phase_change_s'],gates=retained_metrics(p,x),linear_gates=linear,
        negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        curved_negative_twice_elbo=curved['negative_twice_elbo'],
        linear_calibration_max_coefficient_difference=float(max(abs(c['coefficient']-curved['coefficient']))))


def trial(index):
    protocol=read(OUT/'protocol.json');case=protocol['case'];hypothesis=read(OUT/'hypotheses.json')['nodes'][index]
    output=OUT/f'trial_{index:02d}.json'
    if output.exists():raise FileExistsError('preserve complete-data association trial')
    scan,_,keep,_,old=context(case);model=old['hyperparameters_from_pre_RF_TLE_only'];powers=np.array(old['weights'])
    labels=sorted({r['candidate_index'] for r in hypothesis['seed']['rows']})
    _,receipts=phase_widths(scan,labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    original_entries=old['linear_entries'] if old['linear_paired_valid'] else []
    started=time.monotonic()
    initial={a:curved_refit(scan,hypothesis,keep,powers,means,model,a) for a in ARMS}
    anchors={a:np.array(initial[a]['endpoint_east_north_km']) for a in ARMS}
    references={a:np.array(initial[a]['phase_reference']) for a in ARMS}
    history={a:[] for a in ARMS};assignment_history=[];entries=copy.deepcopy(original_entries);previous=copy.deepcopy(entries)
    pair={}
    for epoch in range(5):
        p=build(scan,hypothesis,keep,'c0',references['c0'],powers,means,model)
        if original_entries:
            pools=proposal_pools(p,anchors['c0'],previous,powers)
            choice=select_assignment(pools,top_k=3,sweeps=3)
            entries=[pool[i]['entry'] for pool,i in zip(pools,choice['indices'],strict=True)]
            # Independent replay of the selected density under the original
            # predictive factor implementation, before optimization.
            check=build(scan,hypothesis,keep,'c0',references['c0'],powers,means,model,entries)
            c=check.calculate(anchors['c0']);curved=check.curved_calculate(anchors['c0'])
            replay=c['negative_twice_elbo']-curved['negative_twice_elbo']
            if abs(replay-choice['objective'])>1e-5:
                raise ValueError('assignment density does not replay original predictive likelihood')
            ids=[o for e in entries for o in e['observation_ids']]
            expected=[o for e in original_entries for o in e['observation_ids']]
            if ids!=expected or len(set(ids))!=len(ids):raise ValueError('changed predictive measurement ownership')
        else:choice=dict(indices=[],objective=0.,history=[],evaluations=0)
        switches=sum((a['candidate_index'],a['alias'])!=(b['candidate_index'],b['alias']) for a,b in zip(entries,previous,strict=True))
        assignment_history.append(dict(epoch=epoch,choice=choice,entries=entries,changes=switches))
        for arm in ARMS:
            p=build(scan,hypothesis,keep,arm,references[arm],powers,means,model,entries)
            fitted=fit(p,anchors[arm],iterations=48);x=np.asarray(fitted['parameters']);anchors[arm]=x
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            change=float(max(abs(phase-references[arm])));references[arm]=phase
            history[arm].append(dict(epoch=epoch,fit=fitted,phase_change_s=change))
            pair[arm]=summarize(p,x,entries,history[arm])
        previous=copy.deepcopy(entries)
    valid=pair_passes(pair,include_linear=True)
    write(output,dict(case=case,hypothesis_index=index,node=hypothesis,initial_curved_pair=initial,
        arms=pair,entries=entries,assignment_history=assignment_history,paired_valid=valid,
        assignment_stable=assignment_history[-1]['changes']==0,
        same_original_curved_mask_and_predictive_physical_observations=True,
        c0_assignment_schedule_shared_with_fitted_c=True,
        linear_observations_never_calibrate_nuisance_at_fixed_position=True,
        no_GPS_postscan_TLE_new_data_or_threshold_relaxation=True,
        seconds=time.monotonic()-started))
    result=dict(index=index,valid=valid,stable=assignment_history[-1]['changes']==0,
        c0_loss=pair['c0']['negative_twice_elbo'],seconds=time.monotonic()-started)
    print(result,flush=True);return result


def prepare():
    if OUT.exists():raise FileExistsError('preserve complete-data association experiment')
    OUT.mkdir();case='DS23-0268';scan,node,keep,_,old=context(case)
    original=read(SOURCE/case/'fit_radio_noise.json')
    candidates=[copy.deepcopy(node)]+[copy.deepcopy(c['node']) for c in original['choices']]
    candidates += [read(DBG/f'discovery_{i:02d}.json')['node'] for i in range(13)]
    nodes=[];seen=set();population=[r['component'] for r in node['seed']['rows']]
    for candidate in candidates:
        if [r['component'] for r in candidate['seed']['rows']]!=population:raise ValueError('different curved point population')
        candidate['seed']['state']=zero_state(scan);key=signature(candidate)
        if key not in seen:seen.add(key);nodes.append(candidate)
    write(OUT/'hypotheses.json',dict(nodes=nodes,no_hypothesis_excluded_for_missing_predictive_family=True,
        discovery_bindings={f'discovery_{i:02d}.json':sha(DBG/f'discovery_{i:02d}.json') for i in range(13)}))
    write(OUT/'protocol.json',dict(case=case,hypotheses=len(nodes),workers=16,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_predictive_reassociation.py'),
        baseline_sha256=sha(SOURCE/case/'algo02_result.json'),hypotheses_sha256=sha(OUT/'hypotheses.json'),
        paired_arms=ARMS,initial_curved_phase_rounds=5,EM_rounds=5,position_steps_per_round=48,
        predictive_candidates='all currently curved-supported families in each same-scan cold-discovered branch',
        maximum_single_track_shortlist=3,incumbent_alias_and_label_retained_if_present=True,
        assignment_coordinate_sweeps=3,full_shared_predictive_covariance=True,
        same_original_observations_noise_powers_physical_priors_and_gate_thresholds=True,
        selection='qualified stable paired trial with lowest normalized c0 loss; must beat original by 2 log(hypotheses+1)',
        labels_and_aliases_shared_between_c_arms=True,GPS_not_used_for_inference=True,
        no_point_removal_or_silent_loss_of_predictive_factors=True))


def main():
    prepare();protocol=read(OUT/'protocol.json');receipts=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=16) as executor:
        for future in as_completed([executor.submit(trial,i) for i in range(protocol['hypotheses'])]):
            receipts.append(future.result());write(OUT/'progress.json',dict(completed=len(receipts),total=protocol['hypotheses']))
    _,_,_,_,old=context(protocol['case']);baseline=old['policy_arms']['c0']['negative_twice_elbo']
    eligible=[r for r in receipts if r['valid'] and r['stable']]
    chosen=min(eligible,key=lambda r:r['c0_loss']) if eligible else None;penalty=2*np.log(protocol['hypotheses']+1)
    accepted=chosen is not None and baseline-chosen['c0_loss']>penalty
    write(OUT/'execution.json',dict(receipts=receipts,seconds=time.monotonic()-started,all_terminal=True,
        baseline_c0_loss=baseline,search_penalty=penalty,best_qualified_trial=chosen,accepted=bool(accepted),
        selected_policy_hypothesis=chosen['index'] if accepted else None))
    print('complete',chosen,'accepted',accepted,flush=True)


if __name__=='__main__':main()
