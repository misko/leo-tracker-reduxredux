"""Label fixed fitted evidence separately from unadopted membership screens."""
from collections import Counter
import hashlib
from diagnose import ROOT,INPUT,CASES,ARMS,read,write,frozen_published_owners,inventory

def finalize(case):
    out=ROOT/case
    if not (out/'audit.json').exists():return None
    z=read(INPUT/'inputs'/(case+'.json'));owners=frozen_published_owners(case,z);z['baseline_owners']=owners
    write(out/'published_owners.json',owners);write(out/'inventory.json',inventory(None,z))
    rr=read(out/'track_residuals.json');checks=[]
    for arm in ARMS:
        fitids=[o for r in rr if r['arm']==arm for o in r['observation_ids']]
        if len(fitids)!=len(set(fitids)):raise ValueError('duplicated fitted native point')
        if set(fitids)!=set(owners[arm]):raise ValueError('fitted native IDs differ from published owners')
        pub=read(out/('published_gates_'+arm+'.json'))
        pub['published_owners_count']=len(owners[arm]);pub['membership_screen_scope']='unadopted endpoint proposals, including incidental graph extensions; not published coverage'
        pub['exact_check_scope']='replace one named family orbit at a time, keep coefficients fixed, replay ALL surviving gates; a failing gate may belong to another family'
        pub['fixed_fitted_native_ids']=sorted(fitids);write(out/('published_gates_'+arm+'.json'),pub)
        for path in out.glob('*-'+arm+'.json'):
            row=read(path)
            if 'omitted_norad' not in row:continue
            omit=row['omitted_norad'];removed=sorted(o for o,n in owners[arm].items() if n==omit)
            fixed={o:n for o,n in owners[arm].items() if n!=omit}
            curve={o for r in rr if r['arm']==arm and r['kind']=='curved_conditional' and r['norad']!=omit for o in r['observation_ids']}
            if len(curve)!=row['active_points']:raise ValueError('changed curved fit evidence')
            row.update(fixed_fitted_native_ids=sorted(fixed),fixed_fitted_native_count=len(fixed),
                fixed_fitted_native_sha256=hashlib.sha256('\n'.join(sorted(fixed)).encode()).hexdigest(),
                intentional_omitted_native_ids=removed,intentional_omitted_native_count=len(removed),
                membership_screen_scope='unadopted post-fit membership proposals; observations in fixed_fitted_native_ids alone enter likelihood',
                proposed_unrelated_lost_ids=[o for o in row['lost_ids'] if o not in removed],
                proposed_omitted_ids_still_owned=[o for o in removed if o in row['proposed_owners']],
                proposed_reassigned_non_omitted_ids=[o for o in row['reassigned_ids'] if o not in removed],
                membership_delta_reference='exact composed ALGO06 frozen published owners, including explicitly accepted ALGO06 recovery')
            row['exact_check_scope']=pub['exact_check_scope']
            write(path,row)
        checks.append(dict(arm=arm,published_native=len(owners[arm]),fixed_fit_native=len(fitids),identical_ids=True,
            incidental_unpublished_extensions_at_saved_endpoint=len(pub['added_ids'])))
    plan=read(out/'fit-plan.json')
    matched_tags=[p.name[:-len('-c0.json')] for p in out.glob('matched_*-c0.json')]
    for tag in ['continue','regional_center','phase_sigma_x2']+[f'omit_{n}' for n in plan['selected']]+matched_tags:
        paths=[out/(tag+'-'+a+'.json') for a in ARMS]
        if all(p.exists() for p in paths):write(out/(tag+'.json'),{a:read(p) for a,p in zip(ARMS,paths)})
    write(out/'native_evidence_validation.json',checks);return checks

if __name__=='__main__':
    for case in CASES:
        print(case,finalize(case),flush=True)
    pairs=[];common=[];maxeval=0;maxrounds=0
    for case in CASES:
        out=ROOT/case;plan=read(out/'fit-plan.json')
        for tag in ['continue','regional_center','phase_sigma_x2']+[f'omit_{n}' for n in plan['selected']]:
            pair=read(out/(tag+'.json'));assert set(pair)==set(ARMS)
            assert pair['c0']['omitted_norad']==pair['fitted_c']['omitted_norad']
            assert pair['c0']['phase_scale']==pair['fitted_c']['phase_scale']
            assert pair['c0']['fixed_fitted_native_ids']==pair['fitted_c']['fixed_fitted_native_ids']
            for row in pair.values():
                maxrounds=max(maxrounds,len(row['history']));maxeval=max(maxeval,max(h['nfev'] for h in row['history']))
            pairs.append((case,tag))
        for p in out.glob('matched_*.json'):
            if p.stem.endswith(('-c0','-fitted_c')):continue
            pair=read(p);assert pair['c0']['fixed_fitted_native_ids']==pair['fitted_c']['fixed_fitted_native_ids'];common.append((case,p.stem))
    assert len(pairs)==70 and len(common)==13 and maxrounds<=15 and maxeval<=140
    write(ROOT/'validation.json',dict(original_matched_policy_pairs=len(pairs),original_trial_rows=2*len(pairs),common_position_phase_start_pairs=len(common),
        baseline_native_identity_set_equalities=20,published_coverage_count_invariant=True,trial_observation_sets_match_across_c_arms=True,max_observed_phase_rounds=maxrounds,max_observed_objective_evaluations_per_round=maxeval,
        all_case_statuses={case:read(ROOT/case/'completion.json')['status'] for case in CASES},all_common_start_statuses={case:read(ROOT/case/'matched-completion.json')['status'] for case in CASES}))
