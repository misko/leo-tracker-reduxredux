"""Recompute ALGO02 support powers after the RF-selected 268 reassociation.

This follows the original weighting definition, without using position truth.
New generalized scores are not compared with old scores at different powers.
"""

import numpy as np
from algo02_scan import pair_passes
from evaluate_ds23_family_weighting import confidence_for,family_weights
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_complete_reassociation import context,build,summarize
from probe_algo03_feasible_recovery import refit as constrained_refit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from run_algo01_ds23_sample import ROOT,read,write,sha
from investigate_dsx01_localization_failures import fit

PARENT=ROOT/'reports/2026_10_20_algo03_feasible_hybrids'
OUT=ROOT/'reports/2026_10_20_algo03_reassociated_support'


def main():
    if OUT.exists():raise FileExistsError('preserve reassociated support control')
    OUT.mkdir();selection=read(PARENT/'execution.json')['best_qualified_trial']
    source=PARENT/f"trial_{selection['index']:02d}.json";chosen=read(source)
    scan,_,keep,_,old=context('DS23-0268');node=chosen['node'];entries=chosen['entries']
    model=old['hyperparameters_from_pre_RF_TLE_only'];labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    _,receipts=phase_widths(scan,labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    base=build(scan,node,keep,'c0',np.zeros(len(labels)),np.array(old['weights']),means,model)
    confidence=confidence_for(scan,node,keep,dict(arms={'c0':dict(record=chosen['arms']['c0'])}))
    powers,owners,counts=family_weights(base.rows,base.members,scan.tracks,confidence,'cross_rx_support',
                                       [int(keep[sl].sum()) for sl in base.slices])
    write(OUT/'protocol.json',dict(case='DS23-0268',selected_parent_sha256=sha(source),powers=powers,
        original_powers=old['weights'],confidence=confidence,
        active_family_owners={str(int(scan.norads[j])):sorted(v) for j,v in owners.items()},
        source_sha256=sha(ROOT/'tools/probe_algo03_reassociated_support.py'),
        same_original_data_labels_aliases_noise_and_physical_prior_scales=True,
        RF_selection_precedes_weight_update=True,no_generalized_score_comparison_across_powers=True,
        no_GPS_or_post_scan_TLE_input=True))
    pair={}
    for arm in ('c0','fitted_c'):
        ref=np.zeros(len(labels));x=np.zeros(2);history=[]
        for epoch in range(5):
            p=build(scan,node,keep,arm,ref,powers,means,model,entries)
            f=fit(p,x,iterations=48);x=np.asarray(f['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(epoch=epoch,fit=f,phase_change_s=float(max(abs(phase-ref)))));ref=phase
        pair[arm]=summarize(p,x,entries,history)
    valid=pair_passes(pair,include_linear=True)
    if not valid:
        constrained={arm:constrained_refit(scan,node,keep,powers,means,model,arm,
            pair[arm]['endpoint_east_north_km'],pair[arm]['phase_reference'],entries) for arm in ('c0','fitted_c')}
    else:constrained=None
    write(OUT/'result.json',dict(unconstrained_arms=pair,unconstrained_paired_valid=valid,
        constrained_arms=constrained,constrained_paired_valid=pair_passes(constrained,include_linear=True) if constrained else False,
        original_selected_arms=chosen['arms'],original_ALGO02_arms=old['policy_arms'],
        powers_changed_from_original=int(np.count_nonzero(powers!=old['weights']))))
    print('unconstrained valid',valid,'constrained valid',bool(constrained and pair_passes(constrained,include_linear=True)),flush=True)


if __name__=='__main__':main()
