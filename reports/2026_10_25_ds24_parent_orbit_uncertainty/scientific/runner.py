"""Two-stage bounded RF execution. Fixed controls precede separately authorized fits."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from contextlib import contextmanager
from pathlib import Path
import signal
import time
import traceback

import numpy as np
import adapter as a
import parent_diagnostics as dg

r=a.r
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
CASES=tuple(f'DS24-{i:04d}' for i in range(10,14))
METHODS=('matched_cold_baseline','retained_uncertainty')
OWNERSHIP=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')
PROTOCOL=HERE/'protocol.json'


@contextmanager
def alarm(seconds):
    if seconds<=0:raise TimeoutError('scientific budget exhausted before stage')
    old=signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded scientific stage timeout')))
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:yield
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)


def bindings_ok(protocol):
    for path,digest in protocol['source_input_hashes'].items():
        if r.sha(path)!=digest:raise ValueError('frozen source/input changed: '+path)


def verify(stage):
    protocol=r.read(PROTOCOL)
    if r.sha(PROTOCOL)!=r.read(HERE/'protocol_seal.json')['protocol_sha256']:raise ValueError('protocol changed')
    bindings_ok(protocol)
    approval=r.read(ROOT/'audit/preflight.json')
    if not approval.get('all_passed') or approval.get('protocol_sha256')!=r.sha(PROTOCOL):
        raise ValueError('matching independent source/math preflight required')
    if stage=='fits':
        go=r.read(ROOT/'coordinator_go.json')
        if not go.get('approved') or go.get('protocol_sha256')!=r.sha(PROTOCOL):raise ValueError('coordinator fit-stage go required')
        if go.get('fixed_seal_sha256')!=r.sha(HERE/'fixed_seal.json'):raise ValueError('coordinator go does not bind fixed-state seal')
        if not r.read(HERE/'fixed_summary.json')['triage']['proceed_all_four_cases']:raise ValueError('materiality triage did not pass')
    return protocol


def array_save(path,**arrays):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    np.savez_compressed(path,**arrays)
    return dict(path=str(path),sha256=r.sha(path))


def role_membership(d,p):
    curved=[oid for i,sl in zip(p.members,p.slices,strict=True)
        for oid,keep in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if keep]
    predictive=[oid for row in d['entries'] for oid in row['observation_ids']]
    if len(curved)!=len(set(curved)) or len(predictive)!=len(set(predictive)) or set(curved)&set(predictive):
        raise ValueError('likelihood point ownership not unique')
    return dict(curved_observation_ids=curved,predictive_observation_ids=predictive,
        curved_unique=len(curved),predictive_unique=len(predictive),union_unique=len(curved)+len(predictive),
        total_GLRT=len(p.native_observation_ids),union_ids_sha256=a.fingerprint(sorted(curved+predictive)),
        original_labels=list(p.labels),original_aliases=list(p.alias),original_keep_sha256=a.fingerprint(p.keep),
        entries_sha256=a.fingerprint(d['entries']),powers_sha256=a.fingerprint(d['powers']))


def fixed_case(case,deadline):
    began=time.monotonic();record=dict(case=case,status='failed',arms={},GPS_or_position_errors_used=False)
    try:
        with alarm(min(120.,deadline-began)):
            d=r.context(case)
            frozen=r.read(PROTOCOL)['cases'][case]
            original_ownership=r.read(frozen['original_ownership_path'])
            reference=dict(original_reference_arms={},coverage={},likelihood_membership=None)
            for arm in r.ARMS:
                saved=d['arms'][arm];x=np.asarray(saved['endpoint_east_north_km']);ref=np.asarray(saved['phase_reference'])
                old=a.build(d,arm,ref,METHODS[0]);new=a.build(d,arm,ref,METHODS[1])
                original=a.summarize(old,x,d['entries'])
                original.update(final_phase_change_s=saved.get('final_phase_change_s',saved['history'][-1]['phase_change_s']),
                    history=saved['history'])
                refcov=a.coverage(old,x,d['entries'],original)
                archived=original_ownership['coverage'][arm]
                old_membership=role_membership(d,old);new_membership=role_membership(d,new)
                membership_exact=old_membership==new_membership
                archive_match=refcov['accepted_observation_ids']==archived['accepted_observation_ids']
                objective_replay=float(original['negative_twice_elbo']-saved['negative_twice_elbo'])
                reference['original_reference_arms'][arm]=original;reference['coverage'][arm]=refcov
                reference['likelihood_membership']=old_membership
                controls=dg.equivalence(d,arm,x,ref,old,new)
                oldprobe=dg.objective_probe(old,x);newprobe=dg.objective_probe(new,x)
                info=dg.primary_information(d,old,new,x)
                own=dg.design(d,new,x)
                delta=newprobe['gradient']-oldprobe['gradient']
                proxy=-.5*np.linalg.solve(info['base']['information'],delta)
                oracle=dg.dense_oracle(info['base']['u'],info['base']['weights'],info['base']['prior'],info['extra'])
                matrix=array_save(HERE/'arrays'/f'{case}_{arm}_fixed.npz',
                    old_j=info['base']['j'],old_u=info['base']['u'],old_weights=info['base']['weights'],
                    old_prior=info['base']['prior'],extra_columns=info['extra'],augmented_u=info['new_u'],
                    augmented_prior=info['new_prior'],old_information=info['base']['information'],
                    augmented_information=info['information'],original_weak_axis=info['weak'],
                    own_refitted_information=own['information'],own_j=own['j'],own_u=own['u'],
                    own_weights=own['weights'],own_prior=own['prior'])
                newsummary=a.summarize(new,x,d['entries'])
                numeric=bool(controls['all_passed'] and archive_match and membership_exact and abs(objective_replay)<1e-3
                    and oldprobe['gradient_qualified'] and newprobe['gradient_qualified']
                    and info['base']['mean_derivative_qualified'] and own['mean_derivative_qualified']
                    and info['PSD_information_loss'] and oracle['passed']
                    and abs(oldprobe['center']['decomposition_error'])<1e-6
                    and abs(newprobe['center']['decomposition_error'])<1e-6
                    and all(q['center']['final_log_precision_change']<=1e-5 for q in (oldprobe,newprobe)))
                record['arms'][arm]=dict(original_endpoint_east_north_km=x,phase_reference=ref,
                    baseline=oldprobe,candidate=newprobe,model_change_gradient=delta,
                    movement_proxy_km=proxy,movement_proxy_norm_km=float(np.linalg.norm(proxy)),
                    old_information=info['base']['information'],primary_augmented_information=info['information'],
                    own_refitted_information_diagnostic=own['information'],original_weak_axis=info['weak'],
                    old_weak_variance_km2=info['old_weak_variance_km2'],new_weak_variance_km2=info['new_weak_variance_km2'],
                    weak_variance_fractional_change=info['weak_variance_fractional_change'],
                    PSD_information_loss=info['PSD_information_loss'],information_loss_eigenvalues=info['information_loss_eigenvalues'],
                    mean_derivative_relative_error=info['base']['mean_derivative_relative_error'],
                    own_mean_derivative_relative_error=own['mean_derivative_relative_error'],controls=controls,dense_oracle=oracle,
                    original_saved_objective_replay_difference=objective_replay,original_accepted_ledger_exact=archive_match,
                    likelihood_membership_exact=membership_exact,numerically_qualified=numeric,
                    original_calibration_supported=list(old.original_calibration_supported),active_families=list(new.active_likelihood_families),
                    new_prior_only_families=list(new.extra_families),new_prior_metadata=new.extra_mode_metadata,
                    coordinate_spec=new.coordinate_spec,candidate_conservative_gates=newsummary['gates'],
                    candidate_literal_fullmean=a.summarize(new,x,d['entries'],'literal_expanded_fullmean'),arrays=matrix)
                r.write_new(HERE/'fixed'/f'{case}_{arm}_checkpoint.json',record['arms'][arm])
            r.write_new(HERE/'fixed'/f'{case}_reference.json',reference)
            record['status']='complete'
    except Exception as exc:record.update(failure=repr(exc),traceback=traceback.format_exc())
    record['scientific_seconds']=time.monotonic()-began
    r.write_new(HERE/'fixed'/f'{case}.json',record)
    print(case,'fixed',record['status'],record['scientific_seconds'],flush=True)
    return record


def raw_endpoint(p,x,history,method,arm):
    c=p.calculate(x)
    return dict(method=method,arm=arm,endpoint_east_north_km=x,phase_reference=p.reference,
        history=history,final_phase_change_s=history[-1]['phase_change_s'],state=p.state(x),
        final_log_precision_change=float(c['final_log_precision_change']),negative_twice_elbo=float(c['negative_twice_elbo']))


def fit_arm(d,arm,method,directory):
    from investigate_dsx01_localization_failures import fit
    reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
    for epoch in range(5):
        p=a.build(d,arm,reference,method)
        result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        absolute=p.state(x)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,unclipped_absolute_phase_s=absolute,
            phase_change_s=float(np.max(abs(absolute-reference)))))
        r.write_new(directory/f'epoch{epoch}.json',raw_endpoint(p,x,history,method,arm))
        reference=np.clip(absolute,-15,15)
    raw=raw_endpoint(p,x,history,method,arm);r.write_new(directory/'raw_endpoint.json',raw)
    saved=a.summarize(p,x,d['entries']);saved.update(history=history,final_phase_change_s=raw['final_phase_change_s'])
    literal=a.summarize(p,x,d['entries'],'literal_expanded_fullmean')
    literal.update(history=history,final_phase_change_s=raw['final_phase_change_s'])
    coverage=a.coverage(p,x,d['entries'],saved);c=p.calculate(x)
    arrays=array_save(directory/'endpoint_arrays.npz',coefficient=c['coefficient'],latent_coefficient=c['latent_coefficient'],
        features=c['features'],noise_precision=c['noise_precision'],coefficient_prior_precision=c['coefficient_prior_precision'],
        residual=c['residual'],conditional_residual_hz=c['conditional_residual_hz'],
        conservative_conditional_residual_hz=a.conservative_result(p,x)['conditional_residual_hz'],
        predictive_raw_residual_hz=c.get('linear_raw_prediction_residual_hz',np.array([])),
        conservative_predictive_residual_hz=a.conservative_result(p,x).get('linear_raw_prediction_residual_hz',np.array([])),
        predictive_features=c.get('predictive_features',np.empty((0,len(c['coefficient'])))),
        point_sigma_hz=p.point_noise,noise_groups=p.noise_groups,keep=p.keep,phase_reference=p.reference)
    fixed_reference=np.asarray(d['arms'][arm]['phase_reference'])
    old_at_final=a.build(d,arm,fixed_reference,METHODS[0]);new_at_final=a.build(d,arm,fixed_reference,METHODS[1])
    component_panel=dict(reference_kind='same original saved parent phase reference for both models',phase_reference=fixed_reference,
        baseline_at_endpoint=dg.components(old_at_final,x),candidate_at_endpoint=dg.components(new_at_final,x),
        own_final_reference=dg.components(p,x))
    output=dict(summary=saved,literal_expanded_fullmean=literal,coverage=coverage,arrays=arrays,
        objective_components=component_panel,likelihood_membership=role_membership(d,p))
    r.write_new(directory/'result.json',output)
    return output


def preservation(original,candidate):
    per_arm={arm:set(original[arm]['accepted_observation_ids'])<=set(candidate[arm]['accepted_observation_ids'])
        for arm in r.ARMS if arm in original and arm in candidate}
    return bool(set(per_arm)==set(r.ARMS) and all(per_arm.values())),per_arm


def relabels(original,candidate):
    def labels(rows):
        return {oid:int(row['candidate_index']) for row in rows if row['compatible'] for oid in row['observation_ids']}
    before,after=labels(original['associations']),labels(candidate['associations'])
    postfit=set(original['postfit_only_observation_ids'])|set(candidate['postfit_only_observation_ids'])
    return [dict(observation_id=oid,old_family=before[oid],new_family=after[oid])
        for oid in sorted(postfit&before.keys()&after.keys()) if before[oid]!=after[oid]]


def fit_case(case,deadline):
    began=time.monotonic();fixed=r.read(HERE/'fixed'/f'{case}.json')
    record=dict(case=case,status='failed',methods={},coverage={},failures=[],
        operational_policy_source='original_reference',research_policy_source='original_reference',research_policy_adopted=False,
        candidate_all_baseline_accepted_IDs_preserved=False,GPS_or_position_errors_used=False)
    try:
        if fixed['status']!='complete' or not all(v['numerically_qualified'] for v in fixed['arms'].values()):
            raise RuntimeError('fixed-state pair technically blocked; no replacement')
        with alarm(min(120.-fixed['scientific_seconds'],deadline-began)):
            d=r.context(case);reference=r.read(HERE/'fixed'/f'{case}_reference.json')
            record.update(original_reference_arms=reference['original_reference_arms'],likelihood_membership=reference['likelihood_membership'])
            record['coverage']['original_reference']=reference['coverage']
            for method in METHODS:
                arms={};literal={};cov={};details={}
                record['methods'][method]=dict(arms=arms,literal_expanded_fullmean_arms=literal,details=details)
                record['coverage'][method]=cov
                for arm in r.ARMS:
                    try:
                        output=fit_arm(d,arm,method,HERE/'fits'/case/method/arm)
                        arms[arm]=output['summary'];literal[arm]=output['literal_expanded_fullmean'];cov[arm]=output['coverage']
                        details[arm]={k:v for k,v in output.items() if k not in ('summary','literal_expanded_fullmean','coverage')}
                        if output['likelihood_membership']!=reference['likelihood_membership']:
                            raise ValueError('original likelihood labels/aliases/IDs changed')
                        r.write_new(HERE/'fits'/case/method/f'{arm}_checkpoint.json',output)
                    except TimeoutError:raise
                    except Exception as exc:
                        record['failures'].append(dict(method=method,arm=arm,failure=repr(exc),traceback=traceback.format_exc()))
                record['methods'][method].update(a.qualification(arms))
                record['methods'][method]['literal_expanded_paired_valid']=a.qualification(literal)['conservative_paired_valid']
                record['methods'][method]['literal_postfit_extension_status']='not evaluated: expanded legacy indexing incompatible with appended layout'
            candidate=record['methods'][METHODS[1]]
            preserved,per_arm=preservation(reference['coverage'],record['coverage'][METHODS[1]])
            record['candidate_all_baseline_accepted_IDs_preserved']=preserved
            record['candidate_baseline_accepted_IDs_preserved_per_arm']=per_arm
            record['postfit_family_relabels']={arm:relabels(reference['coverage'][arm],record['coverage'][METHODS[1]][arm])
                for arm in r.ARMS if arm in record['coverage'][METHODS[1]]}
            adopted=bool(candidate['conservative_paired_valid'] and preserved and not record['failures'])
            record.update(research_policy_adopted=adopted,research_policy_source=METHODS[1] if adopted else 'original_reference',status='complete')
    except Exception as exc:record.update(failure=repr(exc),traceback=traceback.format_exc())
    record.update(scientific_fit_seconds=time.monotonic()-began,
        scientific_cumulative_case_seconds=fixed['scientific_seconds']+time.monotonic()-began)
    r.write_new(HERE/'fits'/case/'result.json',record)
    print(case,'fits',record['status'],'adopted',record['research_policy_adopted'],record['scientific_fit_seconds'],flush=True)
    return record


def run(stage):
    protocol=verify(stage);began=time.monotonic()
    charged=protocol['preparation_numerical_seconds']
    if stage=='fits':charged+=r.read(HERE/'fixed_summary.json')['summed_scientific_worker_seconds']
    # Cap charged worker-seconds conservatively; split remaining budget over the
    # two workers so even parallel execution cannot exceed600 total seconds.
    remaining=600.-charged
    deadline=began+remaining/2
    worker=fixed_case if stage=='fixed' else fit_case
    results=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,case,deadline):case for case in CASES}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:
                row=dict(case=futures[future],status='worker_failed',failure=repr(exc),scientific_seconds=0.)
                results.append(row)
    results.sort(key=lambda q:CASES.index(q['case']))
    total=sum(q.get('scientific_seconds',q.get('scientific_fit_seconds',0.)) for q in results)
    summary=dict(stage=stage,cases=results,wall_seconds=time.monotonic()-began,
        summed_scientific_worker_seconds=total,previously_charged_numerical_seconds=charged,
        cumulative_charged_seconds=charged+total,maximum_seconds=600.,
        all_selected_terminal=len(results)==len(CASES),all_complete=all(q['status']=='complete' for q in results),
        protocol_sha256=r.sha(PROTOCOL),GPS_or_position_errors_used=False)
    if stage=='fixed':summary['triage']=dg.triage(results)
    r.write_new(HERE/f'{stage}_summary.json',summary)
    files={str(p):r.sha(p) for sub in ('fixed','arrays') if (HERE/sub).exists() for p in sorted((HERE/sub).rglob('*')) if p.is_file()}
    if stage=='fits':files.update({str(p):r.sha(p) for p in sorted((HERE/'fits').rglob('*')) if p.is_file()})
    files[str(HERE/f'{stage}_summary.json')]=r.sha(HERE/f'{stage}_summary.json')
    r.write_new(HERE/f'{stage}_seal.json',dict(protocol_sha256=r.sha(PROTOCOL),files=files,
        all_selected_terminal=summary['all_selected_terminal'],all_complete=summary['all_complete']))
    print(stage,'terminal',summary['all_complete'],'seconds',summary['wall_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('fixed','fits'))
    run(parser.parse_args().stage)
