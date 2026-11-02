"""Cohort reporting from fixed selected endpoints; never selects by GPS."""
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from algo06_science.common import read,write

ROOT=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def statistics(values):
    a=np.asarray(values,float)
    return dict(count=len(a),mean_m=float(a.mean()),median_m=float(np.median(a)),p90_m=float(np.percentile(a,90)),maximum_m=float(a.max()))

def csvwrite(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)

def main():
    policy=read(ROOT/'protocol.json');records=policy['cases'];cases=[]
    by_case={r['case']:r for r in records};attempts=[]
    for name,window in [('run.log','first_main_window'),('extra.log','supplementary_window'),('resume.log','second_bounded_resume')]:
        path=ROOT/name
        if not path.exists():continue
        for line in path.read_text().splitlines():
            fields=line.split()
            offset=0 if window=='first_main_window' else 2
            if len(fields)<=offset+2 or fields[offset] not in by_case:continue
            case=fields[offset];status=fields[offset+1]
            try:elapsed=float(fields[-1])
            except ValueError:continue
            attempts.append(dict(window=window,case=case,dataset=by_case[case]['dataset'],status=status,
                seconds_since_window_start=elapsed,source_log=name,
                event_scope='queue completion; may reuse a previously completed worker receipt'))
    logged_resume={r['case'] for r in attempts if r['window']=='second_bounded_resume'}
    for archive in sorted(ROOT.glob('cases/*/before-resume-*.json')):
        prior=read(archive);case=archive.parent.name
        assert prior['case']==case,'Archived prior receipt attached to wrong recording'
        attempts.append(dict(window='archived_before_bounded_resume',case=case,dataset=by_case[case]['dataset'],
            status=prior['status'],seconds_since_window_start=None,source_log=str(archive.relative_to(ROOT)),
            receipt_sha256=sha(archive),event_scope='exact earlier receipt retained before bounded retry'))
        current_path=archive.parent/'result.json'
        if case not in logged_resume and current_path.exists():
            current=read(current_path)
            if current.get('status')!='running':
                attempts.append(dict(window='bounded_resume_receipt_completion',case=case,dataset=by_case[case]['dataset'],
                    status=current['status'],seconds_since_window_start=None,source_log=str(current_path.relative_to(ROOT)),
                    receipt_sha256=sha(current_path),event_scope='completion bound to retained prior/current receipts; scheduler log unavailable'))
                logged_resume.add(case)
    correction_path=ROOT/'orchestration_correction.json'
    if correction_path.exists():
        for correction in read(correction_path)['records']:
            for retry in correction['terminated_serial_retries']:
                case=correction['case']
                attempts.append(dict(window='aborted_redundant_serial_retry',case=case,dataset=by_case[case]['dataset'],
                    status='orchestration_abort',worker_elapsed_seconds=retry['elapsed_seconds'],source_log='orchestration_correction.json',
                    receipt_sha256=correction['restored_timeout_sha256'],event_scope='redundant serial retry aborted; sealed second600s timeout restored; no output selected'))
    csvwrite(ROOT/'attempt_ledger.csv',attempts)
    for record in records:
        path=ROOT/'cases'/record['case']/'audited_result.json'
        assert path.exists(),'Missing final audited decision '+record['case']
        row=read(path)
        assert row['status'] not in ('running','incomplete_running','not_attempted','total_cap','unaudited_fallback'),'Unfinished decision '+record['case']
        assert row.get('final_audit',{}).get('worker_status') not in ('running','total_cap'),'Unattempted placeholder '+record['case']
        worker_receipt=ROOT/'cases'/record['case']/'result.json'
        assert read(worker_receipt)['status']!='running','Running worker receipt '+record['case']
        assert row['final_audit']['worker_receipt_sha256']==sha(worker_receipt),'Stale audited receipt '+record['case']
        lock_path=worker_receipt.parent/'worker.lock'
        if lock_path.exists():
            with lock_path.open('r') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                fcntl.flock(lock,fcntl.LOCK_UN)
        row.setdefault('baseline',record['baseline'])
        row.setdefault('selected_output',{a:dict(record['baseline'][a],source='exact_saved_ALGO07') for a in ('c0','fitted_c')})
        row.setdefault('development_case',record['case'] in policy['development_cases'])
        cases.append(row)
    assert len(cases)==205 and len({r['case'] for r in cases})==205
    positions=[];ledger=[]
    for row in cases:
        ledger.append(dict(case=row['case'],dataset=row['dataset'],development=row['development_case'],
            status=row['status'],accepted=row['accepted'],fit_attempted=row.get('fit_attempted',False),
            selected_family=row.get('selected_family'),baseline_repair=row.get('baseline_selected'),
            seconds=row.get('seconds'),reason=row.get('reason'),
            RF_eligible_families=len(row.get('eligible',[])),final_audit_status=row.get('final_audit',{}).get('status'),
            final_audit_decision_changed=row.get('final_audit',{}).get('decision_changed'),
            matched_control_optimizer_phase_valid=row.get('final_audit',{}).get('matched_control_optimizer_phase_valid'),
            matched_control_all_gates_qualified=row.get('final_audit',{}).get('matched_control_all_gates_qualified')))
        for arm in ('c0','fitted_c'):
            before=row['baseline'][arm];after=row['selected_output'][arm]
            assert all(np.isfinite(float(v)) for v in (before['error_m'],after['error_m'],before['objective'],after['objective'])),'Nonfinite reporting metric '+row['case']
            assert after['associated']==before['associated'],'Coverage changed'
            if not row['accepted']:
                assert before['error_m']==after['error_m'] and before['objective']==after['objective'],'Fallback not exact'
            candidate=row.get('candidate',{}).get(arm,{})
            gain=row.get('objective_gains',{}).get(arm,{})
            positions.append(dict(case=row['case'],dataset=row['dataset'],arm=arm,development=row['development_case'],
                accepted=row['accepted'],status=row['status'],baseline_error_m=before['error_m'],selected_error_m=after['error_m'],
                selected_minus_baseline_m=after['error_m']-before['error_m'],
                baseline_objective=before['objective'],selected_objective=after['objective'],
                candidate_objective=candidate.get('objective'),candidate_error_m=candidate.get('error_m'),
                candidate_rms_hz=candidate.get('rms_hz'),control_rms_hz=row.get('control',{}).get(arm,{}).get('rms_hz'),
                candidate_phase_change_s=candidate.get('phase_change_s'),
                candidate_gain_vs_control=gain.get('vs_matched_control'),candidate_gain_vs_saved=gain.get('vs_saved_baseline'),
                candidate_phase_closed=candidate.get('phase_closed'),candidate_optimizer_success=candidate.get('optimizer_success'),
                candidate_gates_pass=candidate.get('all_gates_pass'),candidate_qualified=candidate.get('qualified'),
                baseline_associated=before['associated'],selected_associated=after['associated'],selected_source=after['source']))
    csvwrite(ROOT/'case_ledger.csv',ledger);csvwrite(ROOT/'positions.csv',positions)
    summary=[]
    datasets=['ALL','DS24','DS26','DS27','DS28','FRSH']
    for subset in ['all205','held203','development2']:
        for dataset in datasets:
            for arm in ['c0','fitted_c']:
                rr=[r for r in positions if r['arm']==arm and (dataset=='ALL' or r['dataset']==dataset)
                    and (subset=='all205' or r['development']==(subset=='development2'))]
                if not rr:continue
                delta=np.array([r['selected_minus_baseline_m'] for r in rr])
                summary.append(dict(subset=subset,dataset=dataset,arm=arm,count=len(rr),accepted=sum(r['accepted'] for r in rr),
                    improved=int(np.sum(delta< -1e-6)),regressed=int(np.sum(delta>1e-6)),unchanged=int(np.sum(abs(delta)<=1e-6)),
                    improved_over50m=int(np.sum(delta< -50)),regressed_over50m=int(np.sum(delta>50)),
                    maximum_improvement_m=float(max(0.,-delta.min())),maximum_regression_m=float(max(0.,delta.max())),
                    baseline=statistics([r['baseline_error_m'] for r in rr]),selected=statistics([r['selected_error_m'] for r in rr]),
                    baseline_associated=sum(r['baseline_associated'] for r in rr),selected_associated=sum(r['selected_associated'] for r in rr)))
    flat=[dict({k:v for k,v in r.items() if k not in ('baseline','selected')},**{'baseline_'+k:v for k,v in r['baseline'].items()},**{'selected_'+k:v for k,v in r['selected'].items()}) for r in summary]
    csvwrite(ROOT/'cohort_statistics.csv',flat)
    statuses={s:sum(r['status']==s for r in cases) for s in sorted({r['status'] for r in cases})}
    geography_checks=[]
    for row in cases:
        for arm in ('c0','fitted_c'):
            check=row.get('baseline_geography_postdecision_audit',{}).get(arm,{})
            difference=check.get('error_difference_m',row.get('baseline_replay',{}).get(arm,{}).get('error_difference_m'))
            if difference is not None:geography_checks.append(dict(case=row['case'],arm=arm,error_difference_m=difference))
    result=dict(protocol_sha256=sha(ROOT/'protocol.json'),available=205,per_cohort=policy['per_cohort'],status_counts=statuses,
        accepted=sum(r['accepted'] for r in cases),fits_attempted=sum(r.get('fit_attempted',False) for r in cases),
        complete_decision_ledger=len(cases),
        completed_candidate_fit_pairs=sum(len(r.get('candidate',{}))==2 for r in cases),
        completed_matched_control_fit_pairs=sum(len(r.get('control',{}))==2 for r in cases),
        final_audit_passed_cases=sum(r.get('final_audit',{}).get('status') in ('passed','passed_preserved_existing_ALGO07') for r in cases),
        exact_timeout_fallback_bindings=sum(r.get('final_audit',{}).get('status')=='passed_timeout_fallback_binding' for r in cases),
        unsupported_physical_mode_cases=sum(r['status']=='inapplicable_no_physical_modes' for r in cases),
        unsupported_baseline_evidence_union_cases=[dict(case=r['case'],discrepancy=r.get('final_audit',{}).get('baseline_evidence_discrepancy')) for r in cases if r['status']=='unsupported_baseline_evidence_union'],
        final_capped_failed_unverified_cases=[dict(case=r['case'],status=r['status'],worker_status=r.get('final_audit',{}).get('worker_status'),reason=r.get('reason')) for r in cases if r['status'] not in ('accepted','guard_rejected','no_RF_trigger','preserved_existing_ALGO07','inapplicable_no_physical_modes')],
        independence=policy['independence'],coverage_frozen=True,
        baseline_geography_reporting_audit=dict(checked_case_arms=len(geography_checks),
            maximum_absolute_difference_m=max((abs(r['error_difference_m']) for r in geography_checks),default=None),
            above_002m=[r for r in geography_checks if abs(r['error_difference_m'])>.02],
            scope='reporting audit only; never changes RF acceptance; original preselection agreement assertion superseded by final RF-only decision replay'),
        score_scope='RF gains determine acceptance; GPS is postfit outcome reporting only',
        caveat='This bounded stress test is not promotion validation. Conditional predictive development evidence has fold qualification limits.',
        execution_windows={name:read(ROOT/name) for name in ('completion.json','extra_completion.json','resume_completion.json') if (ROOT/name).exists()},
        initial_and_resume_cap_events=[r for r in attempts if r['status'] in ('total_cap','case_cap','subprocess_failed','resume_cap_or_failure')],
        orchestration_correction=read(ROOT/'orchestration_correction.json') if (ROOT/'orchestration_correction.json').exists() else None,
        aborted_redundant_retry_worker_seconds=sum(r.get('worker_elapsed_seconds',0) for r in attempts if r['status']=='orchestration_abort'),
        statistics=summary)
    write(ROOT/'summary.json',result)
    fig,axes=plt.subplots(1,2,figsize=(11,5),constrained_layout=True)
    for ax,arm in zip(axes,['c0','fitted_c']):
        for dataset in datasets[1:]:
            rr=[r for r in positions if r['arm']==arm and r['dataset']==dataset]
            ax.scatter(np.array([r['baseline_error_m'] for r in rr])/1000,np.array([r['selected_error_m'] for r in rr])/1000,s=18,alpha=.7,label=dataset)
        maximum=max(max(r['baseline_error_m'],r['selected_error_m']) for r in positions if r['arm']==arm)/1000
        ax.plot([0,maximum],[0,maximum],'k--',lw=1);ax.set_title(arm);ax.set_xlabel('Saved ALGO07 error (km)');ax.set_ylabel('Guarded SD4 + half selected error (km)');ax.grid(alpha=.25);ax.legend(fontsize=8)
    fig.suptitle('All205 fixed recording identities; RF-only guard with exact baseline fallback')
    fig.savefig(ROOT/'cohort-comparison.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,5),constrained_layout=True)
    for ax,arm in zip(axes,['c0','fitted_c']):
        for development,marker,label in [(False,'o','held203'),(True,'*','development2')]:
            rr=[r for r in positions if r['arm']==arm and r['development']==development and r['candidate_gain_vs_saved'] is not None]
            for accepted,color in [(False,'C3'),(True,'C0')]:
                ss=[r for r in rr if r['accepted']==accepted]
                if ss:ax.scatter([r['candidate_gain_vs_saved'] for r in ss],[(r['candidate_error_m']-r['baseline_error_m'])/1000 for r in ss],marker=marker,s=35 if not development else 110,color=color,alpha=.6,label=label+(' accepted' if accepted else ' rejected'))
        ax.axhline(0,color='black',lw=.8);ax.axvline(policy['objective_gain_threshold'],color='black',ls='--',lw=.8)
        ax.set_title(arm);ax.set_xlabel('Candidate RF objective gain vs saved ALGO07');ax.set_ylabel('Candidate minus saved ALGO07 error (km)');ax.grid(alpha=.25);ax.legend(fontsize=8)
    fig.suptitle('RF fit gain and GPS outcome shown separately; rejected candidates never replace comparator')
    fig.savefig(ROOT/'RF-vs-geography.png',dpi=170);plt.close(fig)
    artifacts=['README.md','protocol.json','execution_amendment.json','audit_guard_amendment.json','final_audit_summary.json','summary.json','cohort_statistics.csv','case_ledger.csv','attempt_ledger.csv','positions.csv','cohort-comparison.png','RF-vs-geography.png','tests.txt']
    artifacts += ['run.py','run_frozen_v1.py','accelerate.py','resume.py','audit.py','initial_audit.py','deadline_guard.py','seal.py','summarize.py','test_population.py',
        'completion.json','extra_completion.json','resume_completion.json','resume_attempts.json','resume_window.json','deadline_guard.json','orchestration_correction.json','terminal_receipt_reconciliation.json']
    allowed=[ROOT/name for name in artifacts if (ROOT/name).exists()]
    excluded=[p for p in ROOT.rglob('*') if p.is_file() and p not in allowed and p.name!='publication_manifest.json' and '__pycache__' not in p.parts]
    def manifest_item(p):return dict(path=str(p.relative_to(ROOT.parent)),sha256=sha(p),bytes=p.stat().st_size)
    write(ROOT/'publication_manifest.json',dict(revision=policy['revision'],protocol_sha256=sha(ROOT/'protocol.json'),
        scope='Bounded205-recording offline stress test; no production or ownership change',
        files={name:dict(sha256=sha(ROOT/name),bytes=(ROOT/name).stat().st_size) for name in artifacts if (ROOT/name).exists()},
        allowlist=[manifest_item(p) for p in allowed],excluded_dense_files=[manifest_item(p) for p in sorted(excluded)],
        detailed_worker_artifacts='cases/CASE/result.json and control/candidate arm JSONs; local research outputs',
        all_case_identity_manifest='protocol.json cases (205 unique native recording identity tuples)',status_counts=statuses))
    print(json.dumps(dict(status_counts=statuses,accepted=result['accepted'],fits_attempted=result['fits_attempted'])),flush=True)

if __name__=='__main__':main()
