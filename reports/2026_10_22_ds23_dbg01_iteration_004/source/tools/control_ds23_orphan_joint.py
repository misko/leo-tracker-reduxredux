"""Frozen-endpoint shared-prediction control, before geographic scoring."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import probe_ds23_orphan_position as position
from ds23_orphan_joint_predictive import JointPredictiveOrphans
from ds23_orphan_predictive_mixture import OrphanPrediction,orphan_rows
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=position.parent.OUT/'joint_linear_control'


def one(job):
    case,arm,label,point=job;d=position.parent.context.engine.current_setup(case)
    x=np.asarray(point);p,saved=position.fixed(d,arm,x)
    original=p.curved_calculate(x)['coefficient'].copy()
    prediction=OrphanPrediction(p,orphan_rows(d),d['powers'],draw_power=4,bias_sigma_hz=0.)
    oracle=JointPredictiveOrphans(prediction,x,d['entries']);proposals=oracle.proposals();trials=[]
    for seed in position.parent.SEEDS:
        r=oracle.integrate(proposals,power=14,seed=seed,nodes=64,details=True)
        finer=oracle.integrate(proposals,power=14,seed=seed,nodes=128)
        r.update(seed=seed,quadrature_difference=abs(r['relative_negative_twice_log_likelihood']-finer['relative_negative_twice_log_likelihood']))
        trials.append(r)
    values=[r['relative_negative_twice_log_likelihood'] for r in trials]
    qualified=bool(max(values)-min(values)<=.5 and all(r['effective_nuisance_draws']>=32 and r['quadrature_difference']<=.05 for r in trials))
    np.testing.assert_array_equal(original,p.curved_calculate(x)['coefficient'])
    result=dict(case=case,arm=arm,label=label,point=x,trials=trials,qualified=qualified,
        old_linear_density_replay_difference=oracle.old_linear_density_difference,
        combined_negative_twice_objective=saved['negative_twice_elbo']+float(np.mean(values)),
        original_record=saved,original_curved_calibration_coefficients_unchanged=True,
        joint_linear_orphan_predictive_covariance_preserved=True,no_new_position_optimization_or_GPS=True)
    write(OUT/(case+'_'+arm+'_'+label+'.json'),result)
    print(case,arm,label,'joint',[r['relative_negative_twice_log_likelihood'] for r in trials],
          'ESS',[r['effective_nuisance_draws'] for r in trials],'qualified',qualified,flush=True)
    return dict(case=case,arm=arm,label=label,status='complete')


def main():
    position.parent.context.configure();OUT.mkdir(exist_ok=True)
    selection=read(position.OUT/'selection.json');jobs=[]
    for selected in selection['rows']:
        case=selected['case'];d=position.parent.context.engine.current_setup(case)
        for arm in ['c0','fitted_c']:
            jobs.append((case,arm,'incumbent',d['arms'][arm]['endpoint_east_north_km']))
            if selected['selected'][arm] is not None:jobs.append((case,arm,'composite_RF_proposal',selected['selected'][arm]['point']))
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve joint covariance control')
    write(OUT/'protocol.json',dict(jobs=jobs,source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_orphan_joint_predictive.py'),
        RF_selection_sha256=sha(position.OUT/'selection.json'),draws=16384,seeds=list(position.parent.SEEDS),
        joint_predictive_conditioning_only_no_linear_calibration_substitution=True,
        no_new_position_search_or_geographic_outcome_used=True))
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,jobs))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
