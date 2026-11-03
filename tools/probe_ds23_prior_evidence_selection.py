"""Apply the frozen RF-only selector to completed matched causal-prior trials."""

from ds23_prior_evidence_selection import choose_prior
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_prior_evidence_selection'
SOURCE = ROOT/'reports/2026_10_19_algo02_ds23_full'
SKEW = ROOT/'reports/2026_10_20_ds23_skew_phase_full'
LOCATION = ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'


def main():
    if (OUT/'execution.json').exists():
        raise FileExistsError('preserve completed prior model selection')
    OUT.mkdir(exist_ok=True)
    protocol = read(SKEW/'protocol.json')
    execution = read(SKEW/'execution.json')
    assert execution['all_terminal']
    skew = {r['case']:r for r in execution['results']}
    location = read(LOCATION/'evaluation_audit.json')['evidence']
    write(OUT/'protocol.json', dict(cases=protocol['cases'], population=protocol['population'],
        unavailable=protocol['unavailable'], remaining340=protocol['additional_confirmation'],
        rule='choose normalized c0 RF bound winner only if both c arms improve by > 2log(3); otherwise original',
        fixed_model_count=3, same_original_observations_aliases_and_priors_except_phase_distribution=True,
        rule_devised_after_aggregate_skew_regression_not_an_untouched_prospective_test=True,
        RF_rule_uses_neither_geographic_errors_nor_capture_format=True,
        no_new_fits_or_gate_relaxation=True, no_GPS_future_TLE_or_measurement_trimming=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (
            ROOT/'tools/ds23_prior_evidence_selection.py', ROOT/'tools/probe_ds23_prior_evidence_selection.py')}))
    results=[]
    for case in protocol['cases']:
        baseline_path = SOURCE/case/'algo02_result.json'
        baseline = read(baseline_path)
        loc_path = ROOT/location[case]['path']
        loc = read(loc_path)
        r = skew[case]
        if 'error' in r:
            raise ValueError('prior experiment had an execution failure')
        skew_path = ROOT/r['position']
        asym = read(skew_path)
        if loc['baseline_arms'] != baseline['policy_arms'] or asym['baseline_arms'] != baseline['policy_arms']:
            raise ValueError('priors do not share the original baseline')
        if loc['original_mask'] != baseline['mask'] or (asym['qualified'] and asym['original_mask'] != baseline['mask']):
            raise ValueError('prior trials do not share the original observations')
        losses = {arm:baseline['policy_arms'][arm]['negative_twice_elbo'] for arm in ('c0','fitted_c')}
        alternatives = {}
        if loc['selection']['qualified']:
            alternatives['location'] = dict(qualified_pre_RF=True, paired_valid=loc['paired_valid'],
                losses={a:loc['arms'][a]['negative_twice_elbo'] for a in losses})
        if asym['qualified']:
            alternatives['skew'] = dict(qualified_pre_RF=True, paired_valid=asym['paired_valid']['skew'],
                losses={a:asym['results']['skew'][a]['negative_twice_elbo'] for a in losses})
        choice = choose_prior(losses, alternatives)
        arms = (baseline['policy_arms'] if choice['model']=='original' else
                loc['arms'] if choice['model']=='location' else asym['results']['skew'])
        write(OUT/(case+'.json'), dict(case=case, choice=choice, policy_arms=arms,
            baseline_sha256=sha(baseline_path), location_sha256=sha(loc_path), skew_sha256=sha(skew_path),
            GPS_used=False, future_TLE_used=False))
        results.append(dict(case=case, model=choice['model'], output_sha256=sha(OUT/(case+'.json'))))
    write(OUT/'execution.json', dict(all_terminal=True, results=results))
    print('Completed', len(results), 'RF-only prior choices', flush=True)


if __name__ == '__main__':
    main()
