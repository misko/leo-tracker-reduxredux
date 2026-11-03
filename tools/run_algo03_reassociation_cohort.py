"""Bounded cohort test using only each scan's already-saved cold RF branches.

This measures transfer of the complete-data reassociation/constrained-fit
mechanism. It explicitly has fewer discovery proposals than the 268 deep dive.
"""

import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

import probe_algo03_complete_reassociation as engine
from algo02_scan import pair_passes
from ds23_predictive_reassociation import family_pattern_product
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_feasible_recovery import refit as constrained_refit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state

OUT=ROOT/'reports/2026_10_20_algo03_reassociation_cohort'


def run(case):
    directory=OUT/case;directory.mkdir();scan,node,keep,base,old=engine.context(case)
    source=engine.SOURCE/case;choices=read(source/'fit_radio_noise.json')['choices']
    nodes=[copy.deepcopy(node)]+[copy.deepcopy(c['node']) for c in choices]
    for n in nodes:n['seed']['state']=zero_state(scan)
    active={r['component'] for r in old['policy_arms']['c0']['gates']['tracks']}
    hypotheses,receipt=family_pattern_product(nodes,active,maximum=512)
    write(directory/'all_hypotheses.json',dict(nodes=hypotheses,receipt=receipt))
    model=old['hyperparameters_from_pre_RF_TLE_only'];powers=np.asarray(old['weights'])
    anchors=[np.zeros(2),np.array(read(source/'result.json')['arms']['c0']['record']['endpoint_east_north_km'])]
    screens=[];started=time.monotonic()
    for index,n in enumerate(hypotheses):
        labels=sorted({r['candidate_index'] for r in n['seed']['rows']});_,rs=phase_widths(scan,labels)
        means=forecast_phase_mean(rs,model['shrinkage']);scores=[]
        for anchor in anchors:
            reference=np.zeros(len(labels))
            for _ in range(5):
                p=engine.build(scan,n,keep,'c0',reference,powers,means,model)
                phase=np.clip(p.state(anchor)['phases'][p.labels],-15,15);reference=phase
            c=p.calculate(anchor);visibility=float(np.sum(np.maximum(0,-c['elevation'][keep])**2)/4)
            scores.append(float(c['negative_twice_elbo']+visibility))
        screens.append(dict(index=index,scores=scores))
    chosen={0}
    for k in range(2):chosen.update(r['index'] for r in sorted(screens,key=lambda r:r['scores'][k])[:12])
    chosen=sorted(chosen)
    write(directory/'screen.json',dict(anchors=anchors,rows=screens,chosen=chosen))
    write(directory/'hypotheses.json',dict(nodes=[hypotheses[i] for i in chosen],source_indices=chosen))
    write(directory/'protocol.json',dict(case=case,hypotheses=len(chosen),original_hypotheses=len(hypotheses),
        engine_sha256=sha(ROOT/'tools/probe_algo03_complete_reassociation.py'),
        source_baseline_sha256=sha(source/'algo02_result.json'),all_original_measurements_retained=True))
    engine.OUT=directory;trials=[]
    for index in range(len(chosen)):trials.append(engine.trial(index))
    baseline=old['policy_arms']['c0']['negative_twice_elbo'];penalty=2*np.log(len(hypotheses)+1)
    offered=sorted([r for r in trials if not r['valid'] and r['c0_loss']<baseline-penalty],key=lambda r:r['c0_loss'])[:6]
    constrained=[]
    for record in offered:
        d=read(directory/f"trial_{record['index']:02d}.json");n=d['node']
        labels=sorted({r['candidate_index'] for r in n['seed']['rows']});_,rs=phase_widths(scan,labels)
        means=forecast_phase_mean(rs,model['shrinkage'])
        pair={arm:constrained_refit(scan,n,keep,powers,means,model,arm,
            d['arms'][arm]['endpoint_east_north_km'],d['arms'][arm]['phase_reference'],d['entries'])
              for arm in ('c0','fitted_c')}
        result=dict(index=record['index'],paired_valid=pair_passes(pair,include_linear=True),arms=pair,
                    c0_loss=pair['c0']['negative_twice_elbo'],entries=d['entries'],node=n)
        write(directory/f"constrained_{record['index']:02d}.json",result)
        constrained.append(dict(index=record['index'],valid=result['paired_valid'],stable=True,
                                c0_loss=result['c0_loss'],constrained=True))
    qualified=[dict(r,constrained=False) for r in trials if r['valid'] and r['stable']]+[r for r in constrained if r['valid']]
    best=min(qualified,key=lambda r:r['c0_loss']) if qualified else None
    accepted=best is not None and baseline-best['c0_loss']>penalty
    policy=old['policy_arms'];new_entries=old['linear_entries'] if old['linear_paired_valid'] else []
    if accepted:
        prefix='constrained' if best['constrained'] else 'trial'
        d=read(directory/f"{prefix}_{best['index']:02d}.json");policy=d['arms'];new_entries=d['entries']
    write(directory/'result.json',dict(case=case,accepted=bool(accepted),best_qualified=best,
        trials=trials,constrained=constrained,search_penalty=penalty,baseline_c0_loss=baseline,
        policy_arms=policy,baseline_arms=old['policy_arms'],entries=new_entries,
        original_predictive_entries=old['linear_entries'] if old['linear_paired_valid'] else [],
        proposal_hypotheses=len(hypotheses),full_finalists=len(chosen),seconds=time.monotonic()-started,
        no_GPS_TLE_change_new_RF_or_point_removal=True,
        proposal_coverage_is_saved_original_branches_not_13_new_cold_starts=True))
    summary=dict(case=case,accepted=bool(accepted),hypotheses=len(hypotheses),seconds=time.monotonic()-started)
    print(summary,flush=True);return summary


def main():
    if OUT.exists():raise FileExistsError('preserve bounded generalization experiment')
    OUT.mkdir();cases=read(ROOT/'reports/2026_10_19_algo03_frame_predictive_v2/protocol.json')['cases']+['DS23-0268']
    write(OUT/'protocol.json',dict(cases=cases,workers=21,development_cohort=20,additional_debug_case='DS23-0268',
        source_sha256=sha(Path(__file__)),engine_sha256=sha(ROOT/'tools/probe_algo03_complete_reassociation.py'),
        helper_sha256=sha(ROOT/'tools/ds23_predictive_reassociation.py'),
        original_ALGO02_sources_and_inputs_unchanged=True,
        same_fixed_hybrid_EM_and_constrained_rules_applied_to_every_case=True,
        no_GPS_for_selection_or_inference=True,maximum_product=512,top_per_RF_anchor=12,
        EM_rounds=5,position_steps_per_round=48,constrained_phase_rounds=5,SLSQP_steps=40,
        maximum_RF_preferred_failed_finalists_for_constraints=6,
        lower_proposal_budget_than_scan268_deep_dive_disclosed=True))
    started=time.monotonic();receipts=[]
    with ProcessPoolExecutor(max_workers=21) as executor:
        for future in as_completed([executor.submit(run,case) for case in cases]):
            receipts.append(future.result());write(OUT/'progress.json',dict(completed=len(receipts),total=len(cases)))
    write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True,seconds=time.monotonic()-started))


if __name__=='__main__':main()
