"""Fixed-observation confidence controls; no GPS or RF-based mask trimming."""

import argparse
from pathlib import Path
import numpy as np
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_fixed_confidence'


def confidence_controls(confidence,support):
    c,s=np.asarray(confidence,float),np.asarray(support,float)
    if c.ndim!=1 or c.shape!=s.shape or not np.isfinite(c).all() or not np.isfinite(s).all() or np.any((c<0)|(c>1)) or np.any((s<=0)|(s>1)):
        raise ValueError('one finite confidence [0,1] and positive support <=1 per fragment required')
    return dict(unit=np.ones(len(c)),confidence_only=np.clip(c,.05,1),
                support_confidence=s*(.05+.95*c),confident_only=np.ones(len(c)))


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    keep=np.array(primary['mask'],bool);model=learned['hyperparameters_from_pre_RF_TLE_only']
    weight_input=read(WEIGHTS/case/'result.json');confidence=np.array(weight_input['confidence'])
    support=np.array(weight_input['results']['cross_rx_support']['weights'])
    base=problem(scan,node,'c0',keep);_,receipt=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage']);results={}
    for method,powers in confidence_controls(confidence,support).items():
        mask=keep.copy()
        if method=='confident_only':
            for c,sl in zip(confidence,base.slices,strict=True):
                if c<.95:mask[sl]=False
        if mask.any():
            arms={arm:refit(scan,node,mask,arm,powers,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
            failures=sorted({r['component'] for arm in arms for r in arms[arm]['gates']['tracks'] if not r['compatible']})
        else:arms={};failures=['no_confident_evidence']
        results[method]=dict(arms=arms,mask=mask,powers=powers,paired_valid=not failures,failures=failures,
                             policy_arms=primary['arms'] if failures else arms,
                             fallback_to_primary=bool(failures))
        print(case,method,'paired valid',not failures,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,baseline=primary['arms'],fixed_primary_mask=keep,
        confidence=confidence,support=support,GPS_used=False,source_sha256=sha(Path(__file__)),
        learned_input_sha256=sha(LEARNED/(case+'.json')),weight_input_sha256=sha(WEIGHTS/case/'result.json'),
        no_gate_based_trimming=True,hard_selection_threshold=.95,
        scores_with_different_powers_are_not_compared_for_model_selection=True,
        confidence_is_a_frozen_conditional_proxy_not_calibrated_probability=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
