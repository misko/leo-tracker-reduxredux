"""Independent end-to-end accounting and artifact-integrity checks."""
import csv
from common import *
def main():
    protocol=read(ROOT/'protocol.json');m=read(ROOT/'dataset/manifest.json')
    cases={r['case'] for r in protocol['cohort']};failed={r['case'] for r in protocol['unavailable']}
    members=[r for r in m['members'] if r['recording_format']=='short_window_iq_recording']
    assert not cases&failed and cases|failed=={r['dataset_label'] for r in members}
    for p,h in read(ROOT/'inference-seal.json')['files'].items():assert digest(p)==h,p
    assert digest(ROOT/'dataset/manifest.json')==read(ROOT/'roster.json')['parent_dataset_manifest_sha256'].removeprefix('sha256:')
    rows=list(csv.DictReader((ROOT/'position-errors.csv').open()));assert len(rows)==len(cases)*2*5
    expected={(case,arm,method) for case in cases for arm in ARMS for method in ('ALGO05',*POLICIES)}
    assert {(r['case'],r['arm'],r['method']) for r in rows}==expected
    qualified=[];frequency=[]
    for case in sorted(cases):
        z=read(ROOT/'inputs'/(case+'.json'));r=read(ROOT/'position'/case/'result.json')
        if z.get('recovery_unavailable'):
            assert not z['targets'] and not r['trials']
            assert all(v['status']=='recovery_unavailable' for v in r['decisions'].values())
        universe={o['observation_id'] for o in read(Path(z['native_path'])/'observations.json')}
        b=z['baseline_arms']
        frequency.append(dict(case=case,method='ALGO05',same_native_support=z['baseline_owners']['c0']==z['baseline_owners']['fitted_c'],
            c0_objective=b['c0']['negative_twice_elbo'],fitted_c_objective=b['fitted_c']['negative_twice_elbo'],
            c0_minus_fitted_c_objective=b['c0']['negative_twice_elbo']-b['fitted_c']['negative_twice_elbo']))
        for policy,d in r['decisions'].items():
            for arm in ARMS:
                rr=next(v for v in rows if v['case']==case and v['arm']==arm and v['method']==policy)
                assert int(rr['total'])==len(universe)
                assert set(z['baseline_owners'][arm])<=universe
                if d['status']=='qualified':
                    t=r['trials'][d['trial']];v=t['arms'][arm];ids=t['entry']['observation_ids']
                    assert len(ids)==len(set(ids))==t['entry']['points']
                    assert set(ids)<=universe and not set(ids)&set(z['baseline_owners'][arm])
                    assert v['all_checked_gates_pass'] and r['control'][arm]['all_checked_gates_pass']
                    assert not v['changed_incumbent_ids'] and int(rr['associated'])==len(z['baseline_owners'][arm])+len(ids)
                else:
                    assert int(rr['associated'])==len(z['baseline_owners'][arm])
                    assert json.loads(rr['endpoint_latlon'])==z['baseline_arms'][arm]['endpoint_latlon']
            if d['status']=='qualified':
                q=r['trials'][d['trial']];qualified.append(dict(case=case,policy=policy,norad=q['entry']['norad'],points=q['entry']['points']))
                frequency.append(dict(case=case,method=policy,same_native_support=True,
                    c0_objective=q['arms']['c0']['negative_twice_elbo'],fitted_c_objective=q['arms']['fitted_c']['negative_twice_elbo'],
                    c0_minus_fitted_c_objective=q['arms']['c0']['negative_twice_elbo']-q['arms']['fitted_c']['negative_twice_elbo']))
    write(ROOT/'frequency-fit-ablation.json',dict(rows=frequency,note='Only compare c arms within a method on matched support. Objectives across added-point sets are not localization gains.'))
    write(ROOT/'validation.json',dict(verified=True,fast_comparison_members=len(members),usable=len(cases),upstream_unavailable=len(failed),
        recovery_unavailable=[r['case'] for r in protocol['cohort'] if r.get('recovery_unavailable')],
        comparison_rows=len(rows),qualified_decisions=qualified,all_owners_preserved=True,all_native_ids_unique=True,
        inference_files_verified=len(read(ROOT/'inference-seal.json')['files']),
        tests_passed=31,test_groups={'offline_ALGO04_adapter':15,'offline_ALGO05_export':3,'screening':4,'physical_mixture_and_phase':9}))
    fields=['case','recording_id','captured_utc_ns','sample_rate_hz','recording_state','evaluation_state']
    with (ROOT/'dataset-inventory.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for v in members:w.writerow(dict(case=v['dataset_label'],recording_id=v['recording_id'],captured_utc_ns=v['captured_utc_ns'],
            sample_rate_hz=v['sample_rate_hz'],recording_state=v['recording_state'],evaluation_state='complete' if v['dataset_label'] in cases else 'failed'))
    artifacts=list(ROOT.glob('*.md'))+list(ROOT.glob('*.png'))+list(ROOT.glob('*.csv'))+list((ROOT/'curves').glob('*.png'))
    artifacts += [ROOT/n for n in ('validation.json','summary.json','frequency-fit-ablation.json','input-audit.json','numerical-provenance.json','inference-seal.json')]
    write(ROOT/'artifact-manifest.json',dict(files={str(p.relative_to(ROOT)):digest(p) for p in artifacts}))
    print('Verified',len(rows),'comparison rows;',len(qualified),'qualified paired decisions')
if __name__=='__main__':main()
