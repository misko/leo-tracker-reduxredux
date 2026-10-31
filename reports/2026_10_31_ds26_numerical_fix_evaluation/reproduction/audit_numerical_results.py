"""Read-only numerical-status audit of frozen same-TID recovery stage pairs.

No known-site coordinates, localization errors, or geographic ranking enter
this audit. Optimizer transitions describe the joint 30 s/centered treatment;
they do not isolate a derivative effect from the reference-coordinate change.
"""
import argparse
import hashlib
import json
from pathlib import Path


ROOT=Path(__file__).resolve().parent
ARMS=('c0','fitted_c')
ROLES=('control','new_family')


def read(path):return json.loads(Path(path).read_text())


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def optimizer_last(v):
    h=v['history'][-1];return h.get('fit',h)


def status_transition(old,new):
    before=optimizer_last(old);after=optimizer_last(new)
    success_before=before.get('success') is True;success_after=after.get('success') is True
    abnormal='ABNORMAL' in str(before.get('message','')).upper()
    return dict(original_success=success_before,treatment_success=success_after,
        original_message=str(before.get('message','')),treatment_message=str(after.get('message','')),
        original_ABNORMAL=abnormal,ABNORMAL_to_success=abnormal and success_after,
        original_success_to_failure=success_before and not success_after,
        failure_to_success=not success_before and success_after,
        persistent_failure=not success_before and not success_after)


def same_scientific_inputs(old,new):
    keys=('targets','family_prior','phase_step_s','maxiter','maxfun','phase_rounds','start',
        'box_width_km','uncalibrated_label','phase_resolution_audit')
    return [key for key in keys if old.get(key)!=new.get(key)]


def execution_evidence(case_root):
    """Worker receipts survive a killed child that cannot flush its metadata."""
    records={};sources=[]
    for path in sorted(case_root.glob('*-receipt.json')):
        try:record=read(path)
        except (OSError,json.JSONDecodeError):continue
        if isinstance(record,dict) and 'name' in record and 'status' in record:
            records[record['name']]=record;sources.append(path)
    decision=case_root/'decision.json'
    if decision.exists():
        try:
            for record in read(decision).get('stages',[]):records[record['name']]=record
            sources.append(decision)
        except (OSError,json.JSONDecodeError):pass
    expected={};cache=[]
    for path in sorted((case_root/'stage-cache').glob('*.json')):
        try:record=read(path)
        except (OSError,json.JSONDecodeError):continue
        cache.append(record)
        command=record.get('command',[])
        if '--receipt' in command:
            receipt=Path(command[command.index('--receipt')+1]);expected[str(receipt)]=dict(stage=receipt.stem,evidence=str(path))
    # A timeout can interrupt staged() before its stage-cache record exists.
    # The worker error retains the actual numerical_stage.py child command.
    for name,record in records.items():
        if record.get('command') and 'numerical_stage.py' in record.get('error',''):
            receipt=case_root/'numerical-receipts'/(name+'.json')
            expected[str(receipt)]=dict(stage=name,evidence='authoritative_worker_timeout_or_failure')
    missing=[]
    for path,evidence in expected.items():
        try:read(path)
        except (OSError,json.JSONDecodeError) as exc:
            missing.append(dict(path=path,**evidence,reason=type(exc).__name__))
    failed=[dict(record,timeout='TimeoutExpired' in record.get('error','') or record.get('status')=='timeout')
        for record in records.values() if record.get('status') in ('failed','timeout')]
    unstarted=[record['name'] for record in records.values() if record.get('status')=='budget_exhausted']
    return dict(failed=failed,unstarted_budget_exhausted=unstarted,missing_helper_receipts=missing,
        expected_helper_receipts=len(expected),source_paths=sources)


def audit(root,final=False):
    protocol=read(root/'dataset-protocol.json');freeze=read(root/'source-freeze.json')
    cases=protocol['fast_cases'];terminals={}
    for case in cases:
        try:terminals[case]=read(root/'cases'/case/'receipt.json')
        except (OSError,json.JSONDecodeError):continue
    completed=list(terminals)
    if final and len(completed)!=len(cases):raise ValueError('final numerical audit requires every frozen fast-case terminal receipt')
    expected_helper=freeze['files_sha256'][str(root/'numerical_helper.py')]
    expected_bootstrap=freeze['files_sha256'][str(root/'numerical_stage.py')]
    case_failures=[];unavailable=[]
    for case in completed:
        terminal=terminals[case]
        if terminal.get('state')=='unavailable':
            unavailable.append(dict(case=case,reason=terminal.get('reason')));continue
        outcome=root/'cases'/case/'outcome.json'
        failure=read(outcome).get('replay_failure') if outcome.exists() else None
        if terminal.get('state')!='complete' or failure:
            case_failures.append(dict(case=case,terminal_state=terminal.get('state'),replay_failure=failure))
    rows=[];trials=[];receipt_rows=[];hash_mismatches=[];cap_violations=[];stage_failures=[];sources={}
    worker_failures=[];missing_helper=[];unstarted=[];expected_helper_count=0
    for path,expected in ((root/'numerical_helper.py',expected_helper),(root/'numerical_stage.py',expected_bootstrap)):
        actual=sha(path)
        if actual!=expected:hash_mismatches.append(dict(path=str(path),expected=expected,actual=actual,kind='current_source'))
    for case in cases:
        case_root=root/'cases'/case
        execution=execution_evidence(case_root)
        worker_failures += [dict(case=case,**r) for r in execution['failed']]
        missing_helper += [dict(case=case,**r) for r in execution['missing_helper_receipts']]
        unstarted += [dict(case=case,stage=name) for name in execution['unstarted_budget_exhausted']]
        expected_helper_count+=execution['expected_helper_receipts']
        for path in execution['source_paths']:sources[str(path)]=sha(path)
        for path in sorted((case_root/'numerical-receipts').glob('*.json')):
            try:r=read(path)
            except (OSError,json.JSONDecodeError):continue
            sources[str(path)]=sha(path)
            calls=r['optimizer_calls'];updates=r['reference_updates']
            for key,expected in (('helper_sha256',expected_helper),('bootstrap_sha256',expected_bootstrap)):
                if r.get(key)!=expected:hash_mismatches.append(dict(path=str(path),key=key,expected=expected,actual=r.get(key)))
            for index,c in enumerate(calls):
                if not(0<c['total_physical_objective_evaluations']<=c['cap']<=240):
                    cap_violations.append(dict(path=str(path),optimizer_call=index,record=c))
            receipt_rows.append(dict(case=case,path=str(path),optimizer_calls=len(calls),
                successful_rounds=sum(bool(c['success']) for c in calls),
                unsuccessful_rounds=sum(not c['success'] for c in calls),
                counted_cap_stops=sum('cap reached' in c['message'] for c in calls),
                maximum_evaluations=max((c['total_physical_objective_evaluations'] for c in calls),default=0),
                reference_updates=len(updates),extra_optimizer_rounds=r.get('extra_optimizer_rounds'),
                exception=r.get('stage_exception')))
        for stage_path in sorted((case_root/'stage-cache').glob('*.json')):
            try:stage=read(stage_path)
            except (OSError,json.JSONDecodeError):continue
            if stage['script']!='include_new_predictive_family.py' or stage['reused']:continue
            command=stage.get('command',[])
            if '--receipt' not in command:continue
            receipt_path=Path(command[command.index('--receipt')+1]);newroot=Path(stage['output']);oldroot=Path(stage['source'])
            if not receipt_path.exists():continue
            receipt=read(receipt_path)
            if stage['returncode']!=0 or receipt.get('stage_exception'):
                stage_failures.append(dict(case=case,stage=str(stage_path),returncode=stage['returncode'],exception=receipt.get('stage_exception')));continue
            centered=bool(receipt['optimizer_calls'])
            completed_pair=all((newroot/(role+'.json')).exists() for role in ROLES)
            if not completed_pair:continue
            newpr=read(newroot/'protocol.json');old_exists=all((oldroot/(role+'.json')).exists() for role in ROLES) and (oldroot/'protocol.json').exists()
            intended_centered=bool(receipt['centered_lbfgsb'] and str(newpr.get('optimizer','')).lower().replace('-','').startswith('lbfgsb'))
            mismatch=same_scientific_inputs(read(oldroot/'protocol.json'),newpr) if old_exists else []
            trial=dict(case=case,track_id=newroot.parent.name,trial=str(newroot),source_trial=str(oldroot),
                centered_position_fit=centered,original_same_TID_trial_exists=old_exists,
                intended_centered_position_fit=intended_centered,
                input_mismatch_fields=mismatch,matched_comparison=old_exists and not mismatch and centered,
                optimizer_calls=len(receipt['optimizer_calls']),
                optimizer_rounds_expected=sum(len(v['history']) for role in ROLES for v in read(newroot/(role+'.json'))['arms'].values()),
                counts_rounds_match=False)
            trial['counts_rounds_match']=trial['optimizer_calls']==trial['optimizer_rounds_expected'] if intended_centered else True
            trials.append(trial);sources[str(stage_path)]=sha(stage_path)
            for role in ROLES:
                document=read(newroot/(role+'.json'));old_document=read(oldroot/(role+'.json')) if old_exists else None
                for arm in ARMS:
                    v=document['arms'][arm];last=optimizer_last(v)
                    row=dict(case=case,track_id=newroot.parent.name,role=role,arm=arm,trial=str(newroot),
                        source_trial=str(oldroot),matched_comparison=trial['matched_comparison'],
                        treatment_success=last.get('success') is True,treatment_message=str(last.get('message','')),
                        treatment_paired_valid=document['paired_valid'],final_phase_change_s=v['final_phase_change_s'])
                    if old_document is not None:row.update(status_transition(old_document['arms'][arm],v))
                    rows.append(row)
                    sources[str(newroot/(role+'.json'))]=sha(newroot/(role+'.json'))
                    if old_exists:sources[str(oldroot/(role+'.json'))]=sha(oldroot/(role+'.json'))
    matched=[r for r in rows if r['matched_comparison']]
    result=dict(final=final,scope='all frozen DS26 fast scans; no geographic truth',expected_cases=len(cases),
        completed_cases=len(completed),remaining_cases=[c for c in cases if c not in completed],
        completed_new_family_trials=len(trials),centered_trials=sum(t['centered_position_fit'] for t in trials),
        matched_same_TID_trials=sum(t['matched_comparison'] for t in trials),
        trials_without_original_same_TID=sum(not t['original_same_TID_trial_exists'] for t in trials),
        trials_with_input_mismatch=sum(bool(t['input_mismatch_fields']) for t in trials),
        matched_final_fits=len(matched),original_ABNORMAL_final_fits=sum(r.get('original_ABNORMAL',False) for r in matched),
        original_ABNORMAL_to_centered_success=sum(r.get('ABNORMAL_to_success',False) for r in matched),
        original_success_to_treatment_failure=sum(r.get('original_success_to_failure',False) for r in matched),
        failure_to_success=sum(r.get('failure_to_success',False) for r in matched),
        persistent_failure=sum(r.get('persistent_failure',False) for r in matched),
        centered_optimizer_rounds=sum(r['optimizer_calls'] for r in receipt_rows),
        counted_cap_stops=sum(r['counted_cap_stops'] for r in receipt_rows),
        maximum_counted_objective_evaluations=max((r['maximum_evaluations'] for r in receipt_rows),default=0),
        cap_violations=cap_violations,helper_hash_mismatches=hash_mismatches,
        stage_failures=worker_failures,
        worker_stage_failed_count=len(worker_failures),worker_stage_timeout_count=sum(r['timeout'] for r in worker_failures),
        completed_new_family_stage_failures=stage_failures,
        recorded_bootstrap_exceptions=[r for r in receipt_rows if r['exception']],
        missing_helper_receipts=missing_helper,expected_started_helper_receipts=expected_helper_count,
        unstarted_budget_exhausted_stages=unstarted,
        case_terminal_failures=case_failures,source_unavailable_cases=unavailable,
        round_count_mismatches=[t for t in trials if not t['counts_rounds_match']],
        expected_helper_sha256=expected_helper,expected_bootstrap_sha256=expected_bootstrap,
        inference_receipts=receipt_rows,trials=trials,fit_transitions=rows,
        caveat='Status transitions are under joint reference30/centered treatment; not an isolated gradient ablation. Newly eligible trials have no original optimizer comparator.',
        no_GPS_or_known_site_evaluation=True,source_hashes=sources,
        audit_script_sha256=sha(Path(__file__)))
    prefix='numerical-audit' if final else 'numerical-audit-preliminary'
    (root/(prefix+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    text=['# Numerical optimizer audit'+('' if final else ' — preliminary'),'',
        f"{'Final' if final else 'Incomplete snapshot'}: {len(completed)} / {len(cases)} frozen DS26 fast cases have terminal receipts. No known-site coordinate or geographic error enters this audit.",'',
        f"Completed new-family trials: **{len(trials)}**; **{result['matched_same_TID_trials']}** centered trials have the same original TID, target identities/aliases, physical family prior, phase grid, starting point and round/evaluation budgets. **{result['trials_without_original_same_TID']}** have no completed original same-TID trial and cannot demonstrate an optimizer-status improvement.",'',
        '| Numerical status / integrity | Count |','|---|---:|',
        f"| Matched final role × c-arm fits | {len(matched)} |",
        f"| Original final ABNORMAL | {result['original_ABNORMAL_final_fits']} |",
        f"| Original ABNORMAL → centered success | {result['original_ABNORMAL_to_centered_success']} |",
        f"| Original success → treatment failure | {result['original_success_to_treatment_failure']} |",
        f"| All original failures → treatment success | {result['failure_to_success']} |",
        f"| Persistent optimizer failures | {result['persistent_failure']} |",
        f"| Centered optimizer rounds in completed helper receipts | {result['centered_optimizer_rounds']} |",
        f"| Counted evaluation-cap stops | {result['counted_cap_stops']} |",
        f"| Maximum physical evaluations in a round | {result['maximum_counted_objective_evaluations']} / 240 |",
        f"| Cap violations | {len(cap_violations)} |",
        f"| Recorded helper/bootstrap hash mismatches | {len(hash_mismatches)} |",
        f"| Worker-authoritative failed stages | {len(worker_failures)} |",
        f"| Worker-authoritative timeouts (subset of failed) | {result['worker_stage_timeout_count']} |",
        f"| Exceptions recorded by completed bootstrap receipts | {len(result['recorded_bootstrap_exceptions'])} |",
        f"| Started changed stages missing valid helper receipt | {len(missing_helper)} |",
        f"| Unstarted stages omitted by remaining-budget check | {len(unstarted)} |",
        f"| Case-level replay failures | {len(case_failures)} |",
        f"| Original source unavailable; no replay/comparison | {len(unavailable)} |",
        f"| Original/treatment scientific-input mismatches | {result['trials_with_input_mismatch']} |",
        f"| Unexpected optimizer-round counts | {len(result['round_count_mismatches'])} |",'',
        'A fit is one role (`control` or `new_family`) × one c arm, using its final phase round. Numeric-round totals also include centered joint-position stages, but only where a completed helper receipt exists. A killed child may never flush that receipt: zero recorded bootstrap exceptions or hash mismatches does not mean zero worker timeouts, nor does it certify missing receipts. Worker `decision.stages` and per-stage receipts are authoritative for execution failures. Status success does not override RF, phase, incumbent, owner or quadrature gates. All comparisons use the joint 30 s/centered numerical treatment; this audit does not isolate the gradient effect from the reference change.','',
        'Detailed per-fit transitions, unmatched trials, evaluation counts, exceptions and source hashes are in the adjacent JSON. Initial-start coordinates are not used to rank fits.','']
    (root/(prefix+'.md')).write_text('\n'.join(text))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--final',action='store_true');a=p.parse_args()
    result=audit(a.root.resolve(),a.final)
    print(json.dumps({k:result[k] for k in ('final','completed_cases','completed_new_family_trials','matched_same_TID_trials','original_ABNORMAL_to_centered_success','original_success_to_treatment_failure','counted_cap_stops')}))
