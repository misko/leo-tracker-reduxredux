"""Final RF-only receipt and full-native evidence audit, preserving worker rows."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import run as driver
from algo06_science.common import read,write
from algo07_science import engine as e
from algo07_science.diagnose import objective

def arm_qualified(row):
    return bool(row.get('optimizer_success') and row.get('phase_closed') and row.get('all_gates_pass')
        and all(x<.01 for x in row.get('mixture_phase_boundary_masses',[]))
        and row.get('native_ids_preserved') and row.get('all_native_IDs_preserved') and row.get('all_fitted_owners_preserved')
        and not row.get('incumbent_lost',1) and not row.get('unrelated_reassigned',1))

def audit(case):
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s no-refit audit cap')));signal.alarm(180)
    policy=read(ROOT/'protocol.json');record=next(r for r in policy['cases'] if r['case']==case)
    folder=ROOT/'cases'/case;path=folder/'result.json'
    saved_audit=folder/'final_audit.json';saved_result=folder/'audited_result.json'
    if saved_audit.exists() and saved_result.exists():
        prior=read(saved_audit)
        if (prior.get('worker_receipt_sha256')==driver.sha(path) and prior.get('protocol_sha256')==driver.sha(ROOT/'protocol.json')
                and prior.get('input_sha256')==driver.sha(record['input_path'])
                and prior.get('audit_source_sha256')==driver.sha(Path(__file__))
                and prior.get('driver_source_sha256')==driver.sha(Path(driver.__file__))):
            print(case,'bound existing audit reused',flush=True);return prior
    original=read(path);row=copy.deepcopy(original)
    deadline_path=ROOT/'deadline_guard.json'
    deadline_cases={r['case'] for r in read(deadline_path).get('records',[])} if deadline_path.exists() else set()
    if case in deadline_cases and not original['accepted'] and original['status'] not in ('case_cap','resume_case_cap'):
        row.update(status='resume_total_cap',reason='Original bounded resume deadline exhausted; '+original.get('reason',''))
    receipt=dict(case=case,worker_receipt_sha256=driver.sha(path),input_sha256=driver.sha(record['input_path']),
        protocol_sha256=driver.sha(ROOT/'protocol.json'),prior_accepted=original['accepted'],worker_status=original['status'],status='running',
        audit_source_sha256=driver.sha(Path(__file__)),driver_source_sha256=driver.sha(Path(driver.__file__)))
    try:
        assert receipt['input_sha256']==record['input_sha256'],'Input hash mismatch'
        assert original.get('protocol_sha256')==receipt['protocol_sha256'],'Protocol hash missing/mismatch'
        assert original.get('source_input_sha256')==record['input_sha256'],'Worker source input mismatch'
        assert original['baseline']==record['baseline'],'Saved ALGO07 comparator metadata mismatch'
        for arm in driver.ARMS:
            expected=dict(record['baseline'][arm],source='exact_saved_ALGO07')
            if not original['accepted']:assert original['selected_output'][arm]==expected,'Fallback not exact'
        if record['selected']:
            assert original['status']=='preserved_existing_ALGO07' and not original['accepted']
            receipt.update(status='passed_preserved_existing_ALGO07',full_native_scope='Exact saved comparator retained; no candidate/context reconstruction or ownership mutation')
        elif row['status'] in ('case_cap','resume_case_cap','resume_total_cap') and not row.get('candidate'):
            assert not original['accepted']
            row['accepted']=False
            receipt.update(status='passed_timeout_fallback_binding',
                full_native_scope='Not evaluated: RF attempt capped before a candidate pair completed; exact saved ALGO07 retained, no new endpoint or ownership admitted',
                native_audit_method='No new context replay for an exhausted RF attempt; exact comparator/input/protocol/fallback binding verified')
        else:
            baseline=original.get('baseline_replay',{})
            current=bool(baseline and all(baseline[a].get('full_native_union_equals_saved_owners') and baseline[a].get('fitted_owners_sha256') for a in driver.ARMS)
                and all(item.get('all_native_IDs_preserved') and item.get('all_fitted_owners_preserved') for label in ('candidate','control') for item in row.get(label,{}).values()))
            if not current:
                root=Path(record['input_path']).parent.parent;e.configure(root,folder);e.ROOTS[case[:4]]=root
                d,z,replay=e.load_case(case);baseline={}
                for arm,(p,x) in d['problems'].items():
                    inv=driver.native_inventory(p,d)
                    if inv['owners']!=z['baseline_owners'][arm]:
                        from collections import Counter
                        missing=sorted(set(z['baseline_owners'][arm])-set(inv['owners']))
                        receipt.setdefault('baseline_evidence_discrepancy',{})[arm]=dict(published_owned=len(z['baseline_owners'][arm]),
                            likelihood_union=len(inv['ids']),missing_count=len(missing),missing_by_norad=dict(Counter(str(z['baseline_owners'][arm][o]) for o in missing)),
                            missing_ids_sha256=driver.ids_hash(missing),extra_count=len(set(inv['owners'])-set(z['baseline_owners'][arm])),
                            changed_identity_count=sum(z['baseline_owners'][arm].get(o)!=n for o,n in inv['owners'].items() if o in z['baseline_owners'][arm]))
                    assert abs(objective(p,d,x)-record['baseline'][arm]['objective'])<1e-4
                    baseline[arm]=dict(all_native_union_sha256=driver.ids_hash(inv['ids']),all_native_count=len(inv['ids']),
                        native_counts=inv['counts'],full_native_union_equals_saved_owners=True,
                        fitted_owners_sha256=hashlib.sha256(json.dumps(inv['owners'],sort_keys=True).encode()).hexdigest())
                assert not receipt.get('baseline_evidence_discrepancy'),'Baseline complete likelihood identity map differs from published owners'
                for label,scale in [('control',1.),('candidate',4.)]:
                    if not row.get(label):continue
                    context=driver.candidate_context(d,z,scale,row['selected_family'])
                    for arm,item in row[label].items():
                        p,dd=e.build(context,z,arm,np.asarray(item['reference']));inv=driver.native_inventory(p,dd)
                        assert inv['owners']==z['baseline_owners'][arm],'Fitted full native identity mapping changed'
                        assert abs(objective(p,dd,np.asarray(item['x']))-item['objective'])<1e-4,'Endpoint objective replay mismatch'
                        item.update(all_native_IDs_preserved=True,all_fitted_owners_preserved=True,
                            all_native_union_sha256=driver.ids_hash(inv['ids']),all_native_count=len(inv['ids']),native_counts=inv['counts'],
                            fitted_owners_sha256=hashlib.sha256(json.dumps(inv['owners'],sort_keys=True).encode()).hexdigest())
                receipt['native_audit_method']='Reconstructed full context and each sealed endpoint; no RF fit or GPS'
            else:receipt['native_audit_method']='Actual worker full likelihood union+duplicate rejection+fitted owner map equality, backed by frozen factory construction'
            for label in ('candidate','control'):
                for arm,item in row.get(label,{}).items():
                    assert item['all_native_union_sha256']==baseline[arm]['all_native_union_sha256'],'Full union hash changed'
                    assert item['all_native_count']==baseline[arm]['all_native_count'],'Full union count changed'
                    assert item['fitted_owners_sha256']==baseline[arm]['fitted_owners_sha256'],'Full fitted owner hash changed'
                    assert item['native_counts']==baseline[arm]['native_counts'],'Likelihood-piece native counts changed'
            receipt['baseline_native_inventory']=baseline
            if row.get('candidate'):
                controls=row.get('control',{})
                control_valid=bool(controls and all(controls[a]['optimizer_success'] and controls[a]['phase_closed'] for a in driver.ARMS))
                accepted=control_valid and all(arm_qualified(row['candidate'][a]) and all(v is not None and v>policy['objective_gain_threshold'] for v in row['objective_gains'][a].values()) for a in driver.ARMS)
                receipt['matched_control_optimizer_phase_valid']=control_valid
                receipt['matched_control_all_gates_qualified']=bool(controls and all(arm_qualified(controls[a]) for a in driver.ARMS))
                row['accepted']=bool(accepted);row['matched_control_optimizer_phase_valid']=control_valid
                row['status']='accepted' if accepted else 'guard_rejected'
                row['reason']='Final audited RF qualification and both score-gain guards passed' if accepted else 'Final audited RF qualification/control-convergence/score guard failed'
            else:
                row['accepted']=False
                if 'Selected family lacks existing physical modes' in row.get('reason',''):
                    row['status']='inapplicable_no_physical_modes'
            receipt.update(status='passed',all_native_unions_preserved=True,all_fitted_owner_mappings_preserved=True)
        row['selected_output']={a:dict(error_m=row['candidate'][a]['error_m'],objective=row['candidate'][a]['objective'],associated=record['baseline'][a]['associated'],source='SD4_half_candidate') if row['accepted'] else dict(record['baseline'][a],source='exact_saved_ALGO07') for a in driver.ARMS}
    except Exception as exc:
        receipt.update(status='failed_baseline_evidence_union' if receipt.get('baseline_evidence_discrepancy') else 'failed',reason=repr(exc))
        row.update(accepted=False,status='unsupported_baseline_evidence_union' if receipt.get('baseline_evidence_discrepancy') else 'audit_unverified_fallback',reason=repr(exc))
        row['selected_output']={a:dict(record['baseline'][a],source='exact_saved_ALGO07') for a in driver.ARMS}
    receipt.update(final_accepted=row['accepted'],decision_changed=original['accepted']!=row['accepted'],seconds=time.monotonic()-began)
    row['final_audit']=receipt;write(folder/'final_audit.json',receipt);write(folder/'audited_result.json',row)
    print(case,receipt['status'],'changed',receipt['decision_changed'],round(receipt['seconds'],1),flush=True)
    return receipt

def main(workers,summary_name='final_audit_summary.json'):
    cases=[r['case'] for r in read(ROOT/'protocol.json')['cases'] if (ROOT/'cases'/r['case']/'result.json').exists() and read(ROOT/'cases'/r['case']/'result.json').get('status')!='running']
    results=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(audit,case) for case in cases]):results.append(future.result())
    write(ROOT/summary_name,dict(cases=len(results),status_counts={s:sum(r['status']==s for r in results) for s in {r['status'] for r in results}},decision_changes=[r['case'] for r in results if r['decision_changed']],results=results))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case');ap.add_argument('--workers',type=int,default=12);args=ap.parse_args()
    audit(args.case) if args.case else main(args.workers)
