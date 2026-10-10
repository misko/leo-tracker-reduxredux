"""Preparation only: inherited149 source/input authority plus150 sources."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def prepare():
    previous = HERE.parent/'2026_10_10_position_error_iter149/protocol.json'
    plan = copy.deepcopy(json.loads(previous.read_text()))
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT/name) != expected:
                raise ValueError('preserved closure changed '+name)
    plan['input_sha256'][str(previous.relative_to(ROOT))] = sha(previous)
    for path in HERE.glob('*.py'):
        plan['source_sha256'][str(path.relative_to(ROOT))] = sha(path)
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))] = sha(HERE/'PLAN.md')
    plan['input_sha256'][str((HERE/'REVIEW.md').relative_to(ROOT))] = sha(HERE/'REVIEW.md')
    plan['policy']['handoff']['nonlinear_promotion'] = dict(original_state_only=True,
        rf_arm='fitted-c', fixed_position=True, slope_half_width_hz_s=60,
        maximum_seconds=5, maximum_iterations=200, polish_only_if_needed=True)
    plan['scope'] = 'Consumed150 successor; no149 numerical state reuse'
    plan['dynamic_diagnostic'] = dict(before_repair=True, check_legacy_fitted_gate=True,
        no_reference_access=True, original_arm_audit_evaluations=1,
        original_fitted_audit_evaluations=1, nonlinear_selected_audit_evaluations=1,
        promoted_final_audit_evaluations=1,
        nonlinear_optimizer=dict(maximum_seconds=5, maximum_iterations=200,
                                 evaluation_count_cap=None, deadline_scope='optimizer evaluation/callback'),
        polish_maximum_evaluations=100,
        excluded_from_audit_count=['verify_coarse reprice', 'bounded optimizer objective calls',
                                  '102 polish objective calls', '103 validated_postfit evaluation',
                                  'fresh calibration/downstream evaluations'],
        report_actual_wall_time=True)
    return plan

if __name__ == '__main__':
    raise SystemExit('Preparation only: no numerical freeze authorized')
