"""One bounded sample-count refinement of frozen orphan importance proposals."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

import probe_ds23_orphan_adaptive as parent
from ds23_orphan_adaptive_importance import AdaptiveOrphans
from ds23_orphan_predictive_mixture import OrphanPrediction,orphan_rows
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=parent.OUT/'refinement16384'


def one(job):
    case,arm,bias=job;began=time.monotonic();d=parent.context.engine.current_setup(case);saved=d['arms'][arm]
    p=parent.context.engine.baseline.build(d,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    prediction=OrphanPrediction(p,orphan_rows(d),d['powers'],draw_power=4,bias_sigma_hz=bias)
    oracle=AdaptiveOrphans(prediction,x)
    source=parent.OUT/(case+'_'+arm+f'_bias{int(bias)}_qualification.json')
    proposals=read(source)['proposals']
    proposals=[dict(q,mean=np.asarray(q['mean']),root=np.asarray(q['root'])) for q in proposals]
    trials=[]
    for seed in parent.SEEDS:
        r=oracle.integrate(proposals,power=14,seed=seed,nodes=64,details=True)
        control=oracle.integrate(proposals,power=14,seed=seed,nodes=128)
        r.update(seed=seed,quadrature_difference=abs(r['relative_negative_twice_log_likelihood']-control['relative_negative_twice_log_likelihood']))
        trials.append(r)
    difference=abs(trials[0]['relative_negative_twice_log_likelihood']-trials[1]['relative_negative_twice_log_likelihood'])
    qualified=bool(difference<=.5 and all(t['effective_nuisance_draws']>=32 and t['quadrature_difference']<=.05 for t in trials))
    record=dict(case=case,arm=arm,bias_sigma_hz=bias,trials=trials,seed_loss_difference=difference,qualified=qualified,
        proposals_reused_sha256=sha(source),no_model_or_proposal_or_threshold_changes=True,
        no_geographic_evaluation_or_position_search=True,seconds=time.monotonic()-began)
    write(OUT/source.name,record)
    print(case,arm,bias,'refined',[t['relative_negative_twice_log_likelihood'] for t in trials],
          'ESS',[t['effective_nuisance_draws'] for t in trials],'qualified',qualified,flush=True)
    return dict(case=case,arm=arm,bias=bias,status='complete',qualified=qualified)


def main():
    parent.context.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve sample refinement')
    record=dict(parent_protocol_sha256=sha(parent.OUT/'protocol.json'),source_sha256=sha(Path(__file__)),
        cases=read(parent.OUT/'protocol.json')['cases'],draws=16384,
        old_model_proposals_seeds_quadrature_and_qualification_thresholds_unchanged=True,
        one_bounded_sample_count_escalation_only=True,no_new_geographic_scoring_or_position_search=True)
    write(OUT/'protocol.json',record);rows=[]
    jobs=[(c,a,b) for c in record['cases'] for a in ['c0','fitted_c'] for b in [0.,300.]]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(one,j) for j in jobs]):rows.append(f.result())
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
