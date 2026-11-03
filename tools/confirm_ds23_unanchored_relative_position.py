"""Frozen scan-disjoint20 confirmation of the relative-only RF position model."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

from probe_ds23_unanchored_relative_position import one,VARIANTS,CASES as DEVELOPMENT
from run_algo01_ds23_sample import ROOT,read,write,sha

PARENT=ROOT/'reports/2026_10_22_ds23_unanchored_relative_position'
INPUT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase/unanchored_relative_inputs'
SOURCE=Path('/srv/bulk/leo/research/ds23-multilane-confirmation-20261020/protocol.json')
OUT=PARENT/'confirmation20'


def no_offer(case,variant):
    from probe_ds23_sign_carrier_position import context_signed
    signed=context_signed(case)[7]
    result=dict(case=case,variant=variant,status='no_offer',accepted=False,
        reason='fewer_than_two_qualified_relative_groups_or_three_nominated_satellites',
        original_signed_incumbent=signed['policy_arms'],input_sha256=sha(INPUT/(case+'.json')))
    write(OUT/(case+'_'+variant+'.json'),result);return result


def main():
    OUT.mkdir(exist_ok=True);cases=read(SOURCE)['cases'];assert len(cases)==20 and not set(cases)&set(DEVELOPMENT)
    eligible={c:read(INPUT/(c+'.json'))['eligible'] for c in cases}
    protocol=dict(cases=cases,development_cases=DEVELOPMENT,source_original_RF_cohort_sha256=sha(SOURCE),
        variants=VARIANTS,prespecified_default='physical_bias424',
        prespecified_auxiliary_policy='minimum normalized relative-data ELBO among gate-passing variants, uniform model prior',
        same_RF_observations_and_noise_all_variants=True,eligible=eligible,
        unavailable_scans_use_exact_original_incumbent=True,failed_gates_and_jobs_use_exact_original_incumbent=True,
        mean_and_median_include_all20_scans=True,
        source_development_audit_sha256=sha(PARENT/'independent_audit_and_evaluation.json'),
        input_sha256={c:sha(INPUT/(c+'.json')) for c in cases},
        selection_and_default_frozen_before_new_method_confirmation_errors=True,
        no_GPS_or_future_TLE_or_new_RF_or_new_IQ=True,same_site_confirmation_not_new_location=True,
        position_cold_start=[0,0],region_width_km=25,phase_rounds=5,iterations=48,
        workers=12,per_fit_seconds=180,c0_and_fitted_c_equal_due_same_RX_RF_cancellation=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_unanchored_relative_position.py',ROOT/'tools/ds23_unanchored_relative_position.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('relative-only confirmation protocol changed')
    if not path.exists():write(path,protocol)
    rows=[];tasks=[]
    with ProcessPoolExecutor(max_workers=12) as pool:
        for case in cases:
            for variant,physical,bias in VARIANTS:
                path=OUT/(case+'_'+variant+'.json')
                if path.exists():rows.append(read(path))
                elif not eligible[case]:tasks.append(pool.submit(no_offer,case,variant))
                else:tasks.append(pool.submit(one,case,variant,physical,bias,OUT))
        rows.extend(f.result() for f in as_completed(tasks))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,no_geographic_confirmation_evaluation_yet=True))


if __name__=='__main__':main()
