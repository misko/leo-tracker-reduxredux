"""RF-only prior alternatives anchored to the published signed-prior policy.

The selection rule and penalty are unchanged. A small or inconclusive RF
difference retains the current published policy rather than undoing it.
"""

from ds23_prior_evidence_selection import choose_prior
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_incumbent_prior_evidence'
SOURCE = ROOT/'reports/2026_10_19_algo02_ds23_full'
SKEW = ROOT/'reports/2026_10_20_ds23_skew_phase_full'
LOCATION = ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'


def main():
    if (OUT/'execution.json').exists():
        raise FileExistsError('preserve completed incumbent-prior selection')
    OUT.mkdir(exist_ok=True)
    source = read(SKEW/'protocol.json')
    execution = read(SKEW/'execution.json')
    assert execution['all_terminal']
    skew = {r['case']:r for r in execution['results']}
    location = read(LOCATION/'evaluation_audit.json')['evidence']
    write(OUT/'protocol.json', dict(cases=source['cases'],population=source['population'],
        unavailable=source['unavailable'],remaining340=source['additional_confirmation'],
        incumbent='published signed-prior policy, including its original ALGO02 fallbacks',
        rule='retain incumbent unless a qualified alternative improves normalized RF loss by >2log(3) in both c arms; choose c0 winner',
        fixed_model_count=3, prior_symmetric='original symmetric ALGO02', prior_skew='pre-scan qualified asymmetric',
        devised_after_aggregate_prior_studies_not_a_prospective_or_external_location_test=True,
        no_GPS_capture_format_in_selection=True, no_new_fits_gate_relaxation_or_point_removal=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (
            ROOT/'tools/probe_ds23_incumbent_prior_evidence.py',ROOT/'tools/ds23_prior_evidence_selection.py')}))
    results=[]
    for case in source['cases']:
        baseline_path=SOURCE/case/'algo02_result.json'
        original=read(baseline_path)
        loc_path=ROOT/location[case]['path']
        loc=read(loc_path)
        sr=skew[case]
        if 'error' in sr:
            raise ValueError('original asymmetric prior execution failed')
        skew_path=ROOT/sr['position']
        asym=read(skew_path)
        if loc['baseline_arms']!=original['policy_arms'] or asym['baseline_arms']!=original['policy_arms']:
            raise ValueError('mismatched original data authority')
        if loc['original_mask']!=original['mask'] or (asym['qualified'] and asym['original_mask']!=original['mask']):
            raise ValueError('mismatched original observations')
        incumbent=loc['policy_arms']
        incumbent_name='location' if loc['selection']['qualified'] and loc['paired_valid'] else 'original'
        losses={a:incumbent[a]['negative_twice_elbo'] for a in ('c0','fitted_c')}
        alternatives=dict(symmetric=dict(qualified_pre_RF=True,paired_valid=True,
            losses={a:original['policy_arms'][a]['negative_twice_elbo'] for a in losses}))
        if asym['qualified']:
            alternatives['skew']=dict(qualified_pre_RF=True,paired_valid=asym['paired_valid']['skew'],
                losses={a:asym['results']['skew'][a]['negative_twice_elbo'] for a in losses})
        choice=choose_prior(losses,alternatives)
        selected=choice['model']
        arms=(incumbent if selected=='original' else original['policy_arms'] if selected=='symmetric' else asym['results']['skew'])
        choice['selector_token']=selected
        choice['model']=incumbent_name if selected=='original' else 'original' if selected=='symmetric' else 'skew'
        write(OUT/(case+'.json'),dict(case=case,choice=choice,policy_arms=arms,incumbent_model=incumbent_name,
            baseline_sha256=sha(baseline_path),location_sha256=sha(loc_path),skew_sha256=sha(skew_path),
            GPS_used=False,future_TLE_used=False))
        results.append(dict(case=case,model=choice['model'],output_sha256=sha(OUT/(case+'.json'))))
    write(OUT/'execution.json',dict(all_terminal=True,results=results))
    print('Completed',len(results),'incumbent-anchored RF prior choices',flush=True)


if __name__=='__main__':
    main()
