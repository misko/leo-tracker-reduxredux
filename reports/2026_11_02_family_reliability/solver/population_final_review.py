"""No-refit publication checks of final population receipt bindings.

Reads sealed files only. Never imports inference code or evaluation geography.
Missing receipts are reported as incomplete, not silently treated as audited.
"""
import csv,hashlib,json,math,subprocess
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POP=ROOT.parent/'population'
ARMS=('c0','fitted_c')
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(condition,message,issues):
    if not condition:issues.append(message)

def check_record(record,worker,row,receipt,*,protocol_hash,input_hash,worker_hash,threshold,audit_hash=None,driver_hash=None):
    issues=[];case=record['case']
    require(worker.get('protocol_sha256')==protocol_hash,'worker protocol binding',issues)
    require(receipt.get('protocol_sha256')==protocol_hash,'audit protocol binding',issues)
    require(worker.get('source_input_sha256')==record['input_sha256']==input_hash,'worker/native input binding',issues)
    require(receipt.get('input_sha256')==input_hash,'audit/native input binding',issues)
    require(receipt.get('worker_receipt_sha256')==worker_hash,'audit references stale worker receipt',issues)
    if audit_hash is not None:require(receipt.get('audit_source_sha256')==audit_hash,'audit source binding',issues)
    if driver_hash is not None:require(receipt.get('driver_source_sha256')==driver_hash,'driver source binding',issues)
    require(row.get('final_audit')==receipt,'embedded and standalone audit differ',issues)
    require(worker.get('baseline')==row.get('baseline')==record['baseline'],'exact saved comparator binding',issues)
    require(row.get('case')==worker.get('case')==receipt.get('case')==case,'case binding',issues)
    require(row.get('identities')==record['identities'],'recording identity tuple binding',issues)
    accepted=row.get('accepted') is True
    require(receipt.get('final_accepted')==accepted,'audit/final decision binding',issues)
    if record['selected']:
        require(not accepted and worker.get('status')=='preserved_existing_ALGO07','existing ALGO07 repair was replaced',issues)
        require(receipt.get('status')=='passed_preserved_existing_ALGO07','existing repair audit status',issues)
    baseline=receipt.get('baseline_native_inventory',{})
    for label in ('candidate','control'):
        for arm,item in row.get(label,{}).items():
            if receipt.get('status')!='passed':continue
            old=baseline.get(arm,{})
            require(item.get('all_native_IDs_preserved') is True and item.get('all_fitted_owners_preserved') is True,f'{label}/{arm} full native/owner preservation',issues)
            for k in ('all_native_union_sha256','all_native_count','native_counts','fitted_owners_sha256'):
                require(k in item and item[k]==old.get(k),f'{label}/{arm} baseline {k} equality',issues)
    if accepted:
        require(receipt.get('status')=='passed','accepted result lacks passed audit',issues)
        for arm in ARMS:
            cand=row.get('candidate',{}).get(arm,{});control=row.get('control',{}).get(arm,{})
            require(control.get('optimizer_success') is True and control.get('phase_closed') is True,f'{arm} matched control not converged',issues)
            for k in ('optimizer_success','phase_closed','all_gates_pass','native_ids_preserved','all_native_IDs_preserved','all_fitted_owners_preserved'):
                require(cand.get(k) is True,f'{arm} candidate {k}',issues)
            require(cand.get('incumbent_lost')==0 and cand.get('unrelated_reassigned')==0,f'{arm} incumbent loss or unrelated reassignment',issues)
            require(all(math.isfinite(v) and v<.01 for v in cand.get('mixture_phase_boundary_masses',[])),f'{arm} mixture phase boundary',issues)
            require(all(v.get('all_pass') is True for v in cand.get('exact_orbit_checks',[])),f'{arm} exact gates',issues)
            costs=[cand.get('objective'),control.get('objective'),record['baseline'][arm]['objective']]
            finite=all(isinstance(v,(int,float)) and math.isfinite(v) for v in costs)
            require(finite,f'{arm} nonfinite/missing objective',issues)
            if finite:
                gains={'vs_matched_control':costs[1]-costs[0],'vs_saved_baseline':costs[2]-costs[0]}
                require(all(v>threshold for v in gains.values()),f'{arm} amended score guard',issues)
                for k,v in gains.items():require(abs(row['objective_gains'][arm][k]-v)<1e-7,f'{arm}/{k} score replay',issues)
            expected=dict(error_m=cand.get('error_m'),objective=cand.get('objective'),associated=record['baseline'][arm]['associated'],source='SD4_half_candidate')
            require(row.get('selected_output',{}).get(arm)==expected,f'{arm} selected candidate binding',issues)
    else:
        for arm in ARMS:
            expected=dict(record['baseline'][arm],source='exact_saved_ALGO07')
            require(row.get('selected_output',{}).get(arm)==expected,f'{arm} fallback not exact saved ALGO07',issues)
    return issues

def main():
    policy=read(POP/'protocol.json');ph=sha(POP/'protocol.json');source_issues=[]
    amendment=read(POP/'execution_amendment.json');guard=read(POP/'audit_guard_amendment.json')
    require(guard['original_protocol_sha256']==ph,'guard amendment protocol binding',source_issues)
    require(amendment['original_policy_sha256']==ph,'execution amendment protocol binding',source_issues)
    require(amendment['amended_run_sha256']==sha(POP/'run.py'),'amended runner source binding',source_issues)
    require(amendment['original_run_sha256']==sha(POP/'run_frozen_v1.py'),'preserved original runner source binding',source_issues)
    for path,h in policy['source_sha256'].items():
        expected=amendment['amended_run_sha256'] if path==str((POP/'run.py').resolve()) else h
        require(sha(path)==expected,'frozen source binding: '+path,source_issues)
    results=[];missing=[]
    for record in policy['cases']:
        folder=POP/'cases'/record['case'];paths=[folder/n for n in ('result.json','audited_result.json','final_audit.json')]
        if not all(p.exists() for p in paths):
            missing.append(record['case']);continue
        worker,row,receipt=map(read,paths)
        issues=check_record(record,worker,row,receipt,protocol_hash=ph,input_hash=sha(record['input_path']),worker_hash=sha(paths[0]),threshold=policy['objective_gain_threshold'],audit_hash=sha(POP/'audit.py'),driver_hash=sha(POP/'run.py'))
        results.append(dict(case=record['case'],accepted=row.get('accepted'),worker_status=worker.get('status'),
            final_status=row.get('status'),audit_status=receipt.get('status'),existing_repair=record['selected'],
            fit_attempted=row.get('fit_attempted',False),issues=issues,
            worker_receipt_sha256=sha(paths[0]),audited_result_sha256=sha(paths[1]),final_audit_sha256=sha(paths[2]),
            source_input_sha256=record['input_sha256']))
    correction=read(POP/'orchestration_correction.json');correction_issues=[];restored=[]
    for rec in correction['records']:
        archived=ROOT.parents[2]/rec['restored_timeout_receipt'];prior=read(archived)
        require(sha(archived)==rec['restored_timeout_sha256'],'restored receipt hash: '+rec['case'],correction_issues)
        require(prior['case']==rec['case'] and archived.parent.name==rec['case'],'restored receipt case: '+rec['case'],correction_issues)
        require(not prior['accepted'] and 'cap' in prior['status'],'restored receipt is not terminal capped fallback: '+rec['case'],correction_issues)
        current=read(POP/'cases'/rec['case']/'result.json')
        annotation=current.pop('orchestration_correction',None)
        require(current==prior and annotation in (None,rec),'final worker changes restored cap beyond provenance annotation: '+rec['case'],correction_issues)
        restored.append(rec['case'])
    terminal=read(POP/'terminal_receipt_reconciliation.json')
    for rec in terminal['records']:
        partial=ROOT.parents[2]/rec['archived_partial']
        require(sha(partial)==rec['archived_partial_sha256'],'partial checkpoint archive binding: '+rec['case'],correction_issues)
        require(read(partial)['case']==rec['case'],'partial checkpoint case binding: '+rec['case'],correction_issues)
        require(sha(POP/'cases'/rec['case']/'result.json')==rec['terminal_receipt_sha256'],'terminal reconciliation binding: '+rec['case'],correction_issues)
    summary=read(POP/'final_audit_summary.json');summary_rows={r['case']:r for r in summary['results']}
    require(summary['cases']==len(policy['cases']) and set(summary_rows)=={r['case'] for r in policy['cases']},'final summary205 case binding',source_issues)
    for rec in results:
        require(summary_rows.get(rec['case'])==read(POP/'cases'/rec['case']/'final_audit.json'),'summary audit receipt binding: '+rec['case'],source_issues)
    report=read(POP/'summary.json')
    require(report['protocol_sha256']==ph and report['complete_decision_ledger']==len(policy['cases']),'published summary policy/denominator binding',source_issues)
    require(report['accepted']==sum(r['accepted'] is True for r in results),'published accepted count binding',source_issues)
    require(report['status_counts']==dict(Counter(r['final_status'] for r in results)),'published status counts binding',source_issues)
    positions=list(csv.DictReader((POP/'positions.csv').open()))
    require(len(positions)==2*len(policy['cases']) and len({(r['case'],r['arm']) for r in positions})==len(positions),'positions410 unique case-arm binding',source_issues)
    for pos in positions:
        final=read(POP/'cases'/pos['case']/'audited_result.json');selected=final['selected_output'][pos['arm']]
        require(float(pos['selected_objective'])==selected['objective'] and float(pos['selected_error_m'])==selected['error_m'] and int(pos['selected_associated'])==selected['associated'] and pos['selected_source']==selected['source'],'position table sealed endpoint binding: '+pos['case']+'/'+pos['arm'],source_issues)
    processes=subprocess.run(['ps','-eo','pid,args'],check=True,capture_output=True,text=True).stdout.splitlines()
    running=[line.strip() for line in processes if 'family_reliability/population/run.py --case ' in line]
    failed=[r for r in results if r['issues']]
    status='incomplete' if missing or running else 'failed' if failed or source_issues or correction_issues else 'passed'
    result=dict(status=status,scope='independent read-only final receipt/evidence/acceptance replay; no fit or geography calculation',
        protocol_sha256=ph,expected=len(policy['cases']),reviewed=len(results),missing=missing,
        source_issues=source_issues,failed_records=[r['case'] for r in failed],
        orchestration_correction_sha256=sha(POP/'orchestration_correction.json'),orchestration_issues=correction_issues,
        terminal_reconciliation_sha256=sha(POP/'terminal_receipt_reconciliation.json'),
        final_audit_summary_sha256=sha(POP/'final_audit_summary.json'),population_summary_sha256=sha(POP/'summary.json'),
        positions_csv_sha256=sha(POP/'positions.csv'),review_source_sha256=sha(Path(__file__)),
        restored_capped_receipts=restored,running_numerical_workers=running,
        worker_status_counts=dict(Counter(r['worker_status'] for r in results)),
        final_status_counts=dict(Counter(r['final_status'] for r in results)),
        audit_status_counts=dict(Counter(r['audit_status'] for r in results)),
        accepted=sum(r['accepted'] is True for r in results),
        preserved_repairs=[r['case'] for r in results if r['existing_repair']],
        source_hashes={str(p.relative_to(ROOT.parent)):sha(p) for p in (POP/'run.py',POP/'audit.py',POP/'summarize.py',POP/'execution_amendment.json',POP/'audit_guard_amendment.json',ROOT.parent/'combined.py',ROOT.parent/'qualify_combined.py')},
        records=results)
    (ROOT/'population_final_review.json').write_text(json.dumps(result,indent=2)+'\n')
    brief={k:result[k] for k in ('status','expected','reviewed','source_issues','failed_records','accepted','preserved_repairs')}
    brief['missing_count']=len(missing);print(json.dumps(brief))
    return result

if __name__=='__main__':main()
