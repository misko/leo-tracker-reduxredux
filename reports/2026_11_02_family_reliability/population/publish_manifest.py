"""Compact205 decision receipts and publication hashes; no numerical changes."""
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def item(p):return dict(path=str(p.relative_to(ROOT.parent)),sha256=sha(p),bytes=p.stat().st_size)

ARM_FIELDS=('arm','x','reference','objective','rms_hz','error_m','SD_scale','phase_closed','phase_change_s',
    'optimizer_success','all_gates_pass','failed_gates','exact_orbit_checks','mixture_gates_pass',
    'mixture_phase_boundary_masses','native_ids_preserved','all_native_IDs_preserved','all_fitted_owners_preserved',
    'all_native_union_sha256','all_native_count','native_counts','fitted_owners_sha256','incumbent_lost',
    'unrelated_reassigned','incumbent_reassigned','incidental_unowned_extensions','qualified','seconds')

def full_candidate(a):
    return bool(a['optimizer_success'] and a['phase_closed'] and a['phase_change_s']<=.01
        and a['all_gates_pass'] and not a['failed_gates'] and a['mixture_gates_pass']
        and all(g['all_pass'] and g['minimum_slack']>=0 for g in a['exact_orbit_checks'])
        and all(m<.01 for m in a['mixture_phase_boundary_masses'])
        and a['native_ids_preserved'] and a['all_native_IDs_preserved'] and a['all_fitted_owners_preserved']
        and not a['incumbent_lost'] and not a['unrelated_reassigned'])

def main():
    policy=read(ROOT/'protocol.json');threshold=policy['objective_gain_threshold'];rows=[]
    for record in policy['cases']:
        path=ROOT/'cases'/record['case']/'audited_result.json';row=read(path)
        assert row['case']==record['case'] and row['baseline']==record['baseline']
        compact={k:row.get(k) for k in ('case','dataset','identities','status','reason','accepted','baseline','baseline_selected',
            'selected_output','selected_family','objective_gains','matched_control_optimizer_phase_valid','matched_control_status',
            'fit_attempted','development_case','source_input_sha256','protocol_sha256')}
        compact['audited_receipt_sha256']=sha(path);compact['final_audit']=row['final_audit']
        for role in ('candidate','control'):
            compact[role]={arm:{k:a[k] for k in ARM_FIELDS if k in a} for arm,a in row.get(role,{}).items()}
        paired=all(a in compact['candidate'] and a in compact['control'] for a in ('c0','fitted_c'))
        accepted=paired and all(full_candidate(compact['candidate'][a])
            and compact['control'][a]['optimizer_success'] and compact['control'][a]['phase_closed']
            and compact['control'][a]['phase_change_s']<=.01
            and compact['control'][a]['objective']-compact['candidate'][a]['objective']>threshold
            and compact['baseline'][a]['objective']-compact['candidate'][a]['objective']>threshold for a in ('c0','fitted_c'))
        assert bool(accepted)==compact['accepted'],'Compact guard does not reproduce sealed decision '+record['case']
        for arm in ('c0','fitted_c'):
            before=compact['baseline'][arm];after=compact['selected_output'][arm]
            assert all(math.isfinite(float(v)) for v in (before['error_m'],before['objective'],after['error_m'],after['objective']))
            if not accepted:assert after==dict(before,source='exact_saved_ALGO07')
            else:
                candidate=compact['candidate'][arm];base_inventory=compact['final_audit']['baseline_native_inventory'][arm]
                assert candidate['all_native_union_sha256']==base_inventory['all_native_union_sha256']
                assert candidate['fitted_owners_sha256']==base_inventory['fitted_owners_sha256']
                assert candidate['all_native_count']==base_inventory['all_native_count']
                assert after['objective']==candidate['objective'] and after['error_m']==candidate['error_m']
                assert after['associated']==before['associated']
        rows.append(compact)
    assert len(rows)==205
    write(ROOT/'audited_decisions.json',dict(protocol_sha256=sha(ROOT/'protocol.json'),
        threshold=threshold,cases=205,guard_recomputed_cases=205,accepted=sum(r['accepted'] for r in rows),rows=rows,
        scope='Compact sealed decision primitives, normalized objectives, full-native hashes, exact fallback bindings; no dense native arrays'))
    names=['README.md','protocol.json','execution_amendment.json','audit_guard_amendment.json','final_audit_summary.json',
        'audited_decisions.json','summary.json','cohort_statistics.csv','case_ledger.csv','attempt_ledger.csv','positions.csv',
        'cohort-comparison.png','RF-vs-geography.png','tests.txt','run.py','run_frozen_v1.py','accelerate.py','resume.py',
        'audit.py','initial_audit.py','deadline_guard.py','seal.py','summarize.py','publish_manifest.py','test_population.py',
        'completion.json','extra_completion.json','resume_completion.json','resume_attempts.json','resume_window.json',
        'deadline_guard.json','orchestration_correction.json','terminal_receipt_reconciliation.json']
    allow=[ROOT/name for name in names]
    for correction in read(ROOT/'orchestration_correction.json')['records']:
        original=Path(correction['restored_timeout_receipt']).resolve();assert sha(original)==correction['restored_timeout_sha256'];allow.append(original)
    for reconciliation in read(ROOT/'terminal_receipt_reconciliation.json')['records']:
        original=Path(reconciliation['archived_partial']).resolve();assert sha(original)==reconciliation['archived_partial_sha256'];allow.append(original)
    assert len(allow)==len(set(allow)) and all(p.is_file() for p in allow)
    excluded=[p for p in ROOT.rglob('*') if p.is_file() and p not in allow and p.name!='publication_manifest.json' and '__pycache__' not in p.parts]
    write(ROOT/'publication_manifest.json',dict(revision=policy['revision'],protocol_sha256=sha(ROOT/'protocol.json'),
        scope='Bounded205 recording research stress test;35accepted research candidates, no production promotion',
        allowlist=[item(p) for p in allow],excluded_dense_files=[item(p) for p in sorted(excluded)],
        compact_decisions='population/audited_decisions.json',guard_recomputed_cases=205,accepted=35,
        cap_restore_source_chain='original sealed second-timeout and terminal partial receipts are allowlisted with exact hashes',
        dense_evidence_local_only=True))
    print('Publication ready:',len(allow),'allowlisted files;',len(excluded),'excluded dense files;205guards independently reconstructed')

if __name__=='__main__':main()
