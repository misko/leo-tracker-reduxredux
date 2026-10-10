"""Successor metadata preparation; no numerical calls or implicit writes."""
import copy
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def prepare():
    previous=HERE.parent/'2026_10_10_position_error_iter148/protocol.json'
    plan=copy.deepcopy(json.loads(previous.read_text()))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if sha(ROOT/name)!=expected:raise ValueError('preserved148 closure changed '+name)
    plan['input_sha256'][str(previous.relative_to(ROOT))]=sha(previous)
    for path in HERE.glob('*.py'):plan['source_sha256'][str(path.relative_to(ROOT))]=sha(path)
    for name in ('PLAN.md', 'REVIEW.md'):
        plan['input_sha256'][str((HERE/name).relative_to(ROOT))]=sha(HERE/name)
    plan['policy']['handoff']=dict(arm_aware=True,independent_discovery_and_fitted_audits=True,maximum_rounds=2,maximum_evaluations=100,qualification=.001,fixed_position=True,slope_half_width_hz_s=60)
    plan['scope']='Consumed149 successor;148 zero handoff failure preserved, not a scientific negative'
    plan['dynamic_diagnostic']=dict(before_repair=True,check_legacy_fitted_gate=True,no_reference_access=True,original_arm_audit_evaluations=1,original_fitted_audit_evaluations=1,promoted_audit_evaluations=1,excluded_from_audit_count=['verify_coarse reprice','102 qualification evaluations maximum100','103 validated_postfit evaluation','fresh calibration/downstream evaluations'])
    return plan

if __name__=='__main__':raise SystemExit('Preparation only: protocol freeze awaits explicit review')
