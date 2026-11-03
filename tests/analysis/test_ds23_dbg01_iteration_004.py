from copy import deepcopy

from run_ds23_dbg01_iteration_004 import reusable_inventory,batch_cases


def test_reusing_an_old_trial_requires_exact_incumbent_IDs_and_RF_endpoints():
    original={a:dict(accepted_observation_ids=['a','b'],active_curved_points=2,
        predictive_points=0,endpoint=[1.,2.]) for a in ['c0','fitted_c']}
    assert reusable_inventory(original,deepcopy(original))
    changed=deepcopy(original);changed['fitted_c']['accepted_observation_ids']=['a','c']
    assert not reusable_inventory(original,changed)
    changed=deepcopy(original);changed['c0']['endpoint']=[1.,2.001]
    assert not reusable_inventory(original,changed)


def test_iteration_four_moves_past_closed_batches_and_keeps_all_benchmark_rows():
    ranked=[81,326,35,41,111,390,405,221,322,272]
    rows=[dict(case=f'DS23-{n:04}',policy='equal_assignment_priors',arm='fitted_c',
               policy_error_km=str(20-k)) for k,n in enumerate(ranked)]
    assert batch_cases(rows)==['DS23-0221','DS23-0322']
    assert len(rows)==10
