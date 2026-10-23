"""RF-only410-case inventory of completed candidates hidden by a search deadline."""

from collections import Counter
from pathlib import Path
import numpy as np

import probe_ds23_paired_replacement_evidence as reference
from audit_ds23_archived_qualification import qualification
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_22_ds23_reentry_family_cavity/full_DS23'
OUT=ROOT/'reports/2026_10_23_ds23_completed_deadline_inventory'


def matching_RF_context(old,current):
    for arm in ['c0','fitted_c']:
        a,b=old[arm],current[arm]
        if abs(a['negative_twice_elbo']-b['negative_twice_elbo'])>1e-8 or a['active_points']!=b['active_points'] or a.get('predictive_points',0)!=b.get('predictive_points',0):return False
        if any(not np.array_equal(a['state'][key],b['state'][key]) for key in ['beta','smooth','phases']):return False
    return True


def group_key(trial):
    g=trial['group'];return g['original_index'],tuple(g['rows']),g['added_points']


def completed_choice(record,original_mask):
    if record['status']!='budget_exhausted':return None,[]
    qualified=[]
    for i,t in enumerate(record['trials']):
        if not t['paired_valid'] or not all(qualification(r)['qualified'] for r in t['arms'].values()):continue
        mask=np.asarray(t['mask'],bool);old=np.asarray(original_mask,bool)
        if mask.shape!=old.shape or np.any(old&~mask):continue
        qualified.append(i)
    if not qualified:return None,qualified
    first=group_key(record['trials'][qualified[0]])
    selected=min((i for i in qualified if group_key(record['trials'][i])==first),key=lambda i:record['trials'][i]['arms']['c0']['negative_twice_elbo'])
    return selected,qualified


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve completed-deadline RF inventory')
    authority=read(reference.AUTHORITY);bindings=authority['case_result_sha256'];assert len(bindings)==410
    write(OUT/'protocol.json',dict(cases=sorted(r['case'] for r in bindings),source_sha256=sha(Path(__file__)),
        old_full_source_protocol_sha256=sha(SOURCE/'protocol.json'),canonical_authority_sha256=sha(reference.AUTHORITY),
        inventory_only_no_new_fit_or_GPS_or_geographic_scoring=True,
        primary='completed strict-qualified candidate of first passing group, min c0 RF bound within same group',
        only_expired_searches_and_exact_original_current_RF_context_match=True,
        original_calibration_mask_must_be_preserved=True,
        same_saved_c0_fitted_c_candidate_and_original_priors_and_search_budget=True,
        parent_IDs_model_and_native_densities_require_fresh_audit_before_adoption=True,
        no_new_ALGO_or_full_DS23_accuracy_claim=True))
    rows=[]
    for b in bindings:
        case=b['case'];path=reference.SOURCE/(case+'.json')
        if sha(path)!=b['position_sha256']:raise ValueError('canonical source changed')
        canonical=read(path);decision=reference.decisions(canonical);current=canonical['trials'][decision['best_paired_trial_index']]['arms'] if decision['accepted']['published_c0_positive'] else canonical['baseline_arms']
        source=SOURCE/'reentry'/(case+'.json');old=read(source);match=bool('incumbent_arms' in old and matching_RF_context(old['incumbent_arms'],current))
        selected,qualified=completed_choice(old,canonical['original_mask'])
        t=old['trials'][selected] if selected is not None else None
        rows.append(dict(case=case,status=old['status'],source_sha256=sha(source),canonical_source_sha256=sha(path),
            same_current_RF_context=match,completed_trials=len(old.get('trials',[])),qualified_trial_indices=qualified,
            tentative_selected_index=selected if match else None,eligible_pending_fresh_audit=bool(match and selected is not None),
            first_group_completed_candidate_index=selected,added_curved_points=t['group']['added_points'] if t else 0,
            no_final_association_or_adoption=True))
    write(OUT/'RF_inventory.json',dict(rows=rows,status_counts=dict(Counter(r['status'] for r in rows)),
        eligible_cases=[r['case'] for r in rows if r['eligible_pending_fresh_audit']],all410included=True,
        no_GPS_or_position_error_used=True,RF_choices_frozen_before_any_new_geographic_evaluation=True))
    print('All410 statuses',dict(Counter(r['status'] for r in rows)),flush=True)
    print('Eligible pending fresh audit',[r['case'] for r in rows if r['eligible_pending_fresh_audit']],flush=True)


if __name__=='__main__':main()
