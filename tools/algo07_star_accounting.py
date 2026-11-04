"""Narrow, fail-closed operational classifications for complete paired replays.

This module classifies differences; it never recursively drops field names.
Unknown schemas, numerical values, incomplete stages and timeouts remain unequal.
"""
import math
import re
from pathlib import Path

PUBLIC_TIMES = {
    'algo02-causal-family-v1': {'elapsed_seconds'},
    'algo03-causal-predictive-v1': {'baseline_seconds', 'recovery_seconds', 'total_seconds'},
    'algo04-causal-numerical-v1': {'incumbent_seconds', 'numerical_seconds', 'total_seconds'},
    'algo05-causal-gap-conditional-v1': {'incumbent_seconds', 'recovery_seconds', 'total_seconds'},
    'algo06-causal-residual-family-v1': {'incumbent_seconds', 'recovery_seconds', 'total_seconds'},
    'algo07-causal-guarded-reassociation-v1': {
        'incumbent_seconds', 'recovery_seconds', 'total_seconds'},
}
RECOVERY_POLICY = 'algo03-bounded-recovery-v1'
LAUNCH_POLICIES = {RECOVERY_POLICY, 'algo04-conditional-numerical-replay-v1',
                   'gap_conditional', '72h_30s', 'causal-reassociation-unique-receiver-groups-v1'}


def finite_time(value, maximum=7200):
    return type(value) in (float, int) and math.isfinite(value) and 0 <= value < maximum


def parts(pointer):
    return [p.replace('~1', '/').replace('~0', '~') for p in pointer.split('/')[1:]]


def at(value, keys):
    for key in keys:
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def recovery_result(value):
    required = {'job_id', 'baseline', 'stages', 'decision', 'maximum_seconds', 'seconds'}
    return (value.get('policy') == RECOVERY_POLICY and
            required <= value.keys()
            and value.get('no_GPS_selection') is True and value.get('causal_only') is True
            and value.get('matched_c_arms') is True
            and finite_time(value['seconds'], value['maximum_seconds']))


def root_scientific_timing(name, value):
    path = Path(name)
    if not isinstance(value, dict):
        return False
    if (path.name in ('result.json', 'algo02_result.json') and
            {'case', 'algorithm', 'status', 'GPS_used', 'future_TLE_used'} <= value.keys()):
        return value['GPS_used'] is False and value['future_TLE_used'] is False
    if path.name == 'fit_radio_noise.json':
        return {'case', 'choices', 'selected_hypothesis', 'input_read_paths'} <= value.keys()
    if path.parts[-3:] == ('family_cavity', 'position', 'SCAN.json'):
        return {'policy_arms', 'nomination_sha256', 'trials', 'selected'} <= value.keys()
    if path.parts[-2:] == ('family_cavity', 'SCAN_nominations.json'):
        return {'families', 'incumbent_arms', 'reference_position_used'} <= value.keys()
    if path.parts[-2:] == ('annotation', 'result.json'):
        return {'job', 'component', 'folds', 'annotation', 'identity_score_name'} <= value.keys()
    if (path.name in ('control.json', 'new_family.json') or
            (path.stem.startswith('target_') and path.stem[7:].isdigit())):
        return ({'job', 'arms', 'paired_valid', 'target_entries'} <= value.keys()
                and set(value['arms']) == {'c0', 'fitted_c'})
    if path.parent.name == 'numerical-receipts':
        return {'script', 'arguments', 'helper_sha256', 'script_sha256',
                'bootstrap_sha256', 'optimizer_calls', 'reference_limit_s'} <= value.keys()
    exact_shapes = (
        {'case', 'checks', 'targets', 'positions', 'scan_receipt', 'bank_domain_s', 'seconds'},
        {'case', 'targets', 'catalogue_count', 'eligible48', 'propagation_failures', 'seconds'},
        {'case', 'decisions', 'trials', 'control', 'seconds', 'conditional_recovery',
         'production_changed'},
    )
    if any(set(value) == shape for shape in exact_shapes):
        return True
    return (path.name == 'worker_result.json'
            and value.get('policy') == 'causal-reassociation-unique-receiver-groups-v1'
            and {'guards', 'records', 'baseline', 'execution_status'} <= value.keys())


def classify(name, row, left, right, process_roles):
    if row['kind'] not in ('float', 'value') or not row.get('path'):
        return None
    keys = parts(row['path'])
    a, b = at(left, keys[:-1]), at(right, keys[:-1])
    key = keys[-1]
    x, y = at(left, keys), at(right, keys)
    if not isinstance(a, dict) or not isinstance(b, dict):
        # The launch command's remaining wall budget must agree with its own
        # explicit maximum_seconds. All other command arguments remain exact.
        if len(keys) == 2 and keys[0] == 'command' and Path(name).name == 'launch.json':
            i = int(key)
            if (i > 0 and left.get('policy') == right.get('policy') in LAUNCH_POLICIES
                    and a[i-1] == b[i-1] == '--maximum-seconds'
                    and all(str(v['maximum_seconds']) == c[i] and
                            0 < v['maximum_seconds'] <= 1200
                            for v, c in ((left, a), (right, b)))):
                return 'remaining_launch_budget'
        return None
    if a.keys() != b.keys():
        return None
    if (key in ('root_process_id', 'supervisor_process_id')
            and (keys[-2:-1] == ['read_audit'] or
                 (len(keys) == 1 and Path(name).name == 'read-audit.json'))
            and all(v.get('verified') is True and v.get('all_launched_processes_accounted') is True
                and v.get('denied_paths') == [] and v.get('receipts') == v.get('expected')
                for v in (a, b)) and x in process_roles[0] and y in process_roles[1]
            and process_roles[0][x] == process_roles[1][y]):
        return 'verified_process_identity'
    stage = {'stage', 'returncode', 'process_id', 'seconds'}
    if set(a) == stage and a['returncode'] == b['returncode'] == 0:
        if (key == 'process_id' and x in process_roles[0] and y in process_roles[1]
                and process_roles[0][x] == process_roles[1][y]):
            return 'verified_stage_process'
        if key == 'seconds' and finite_time(x, 1200) and finite_time(y, 1200):
            return 'completed_stage_duration'
    receipt = {'name', 'status', 'command', 'budget_seconds', 'returncode', 'seconds'}
    if (set(a) == receipt and key in ('seconds', 'budget_seconds')
            and all(v['status'] == 'complete' and v['returncode'] == 0
                                and 0 < v['budget_seconds'] <= 1200
                                and finite_time(v['seconds'], v['budget_seconds'])
                                for v in (a, b))):
        return 'completed_subprocess_accounting'
    if (set(a) == {'command', 'returncode', 'seconds', 'timeout_s'}
            and a['returncode'] == b['returncode'] == 0 and key == 'seconds'
            and all(0 < v['timeout_s'] <= 1200 and finite_time(v['seconds'], v['timeout_s'])
                    for v in (a, b))):
        return 'completed_gap_stage_duration'
    if (key == 'updated_utc_ns' and {'job_id', 'model_version', 'state', 'result', 'terminal',
                                   'input_sha256', 'failure'} <= a.keys()
            and a['state'] == b['state'] == 'complete' and a['failure'] is b['failure'] is None
            and type(x) is type(y) is int and min(x, y) > 0):
        return 'completed_job_timestamp'
    if (a.get('kind') == b.get('kind') == 'fast-scan.graph-position' and
            a.get('state') == b.get('state') == 'complete' and
            a.get('model_version') == b.get('model_version')
            and key in PUBLIC_TIMES.get(a.get('model_version'), set())
            and finite_time(x) and finite_time(y)):
        return 'validated_public_terminal_accounting'
    if recovery_result(a) and recovery_result(b):
        if key in ('seconds', 'total_seconds') and finite_time(x, 1200) and finite_time(y, 1200):
            return 'completed_recovery_duration'
        if key == 'maximum_seconds' and 0 < x <= 1200 and 0 < y <= 1200:
            return 'completed_recovery_remaining_budget'
    if (Path(name).name == 'launch.json' and len(keys) == 1 and
            a.get('policy') == b.get('policy') in LAUNCH_POLICIES):
        if key == 'maximum_seconds' and 0 < x <= 1200 and 0 < y <= 1200:
            return 'remaining_launch_budget'
        if key == 'whole_recovery_deadline_monotonic' and finite_time(x, math.inf) and \
                finite_time(y, math.inf):
            return 'absolute_monotonic_deadline'
    if (Path(name).name == 'protocol.json' and len(keys) == 1 and key == 'maximum_seconds'
            and a.get('policy') == b.get('policy') in LAUNCH_POLICIES
            and a.get('no_GPS_inference') is b.get('no_GPS_inference') is True
            and 0 < x <= 1200 and 0 < y <= 1200):
        return 'protocol_remaining_wall_budget'
    cache = {'script', 'output', 'source', 'reused', 'reason', 'returncode', 'wall_seconds'}
    if (Path(name).parent.name == 'stage-cache' and len(keys) == 1
            and set(a) in (cache | {'command'}, cache | {'charged_original_seconds'})
            and a['returncode'] == b['returncode'] == 0
            and key in ('wall_seconds', 'charged_original_seconds')
            and finite_time(x, 1200) and finite_time(y, 1200)):
        return 'validated_cache_accounting'
    if (key == 'seconds' and len(keys) == 1 and root_scientific_timing(name, a)
            and root_scientific_timing(name, b) and finite_time(x, 1200) and finite_time(y, 1200)):
        return 'known_result_top_level_duration'
    cavity = {'x', 'latlon', 'error_m', 'objective', 'rms_hz', 'history', 'reference',
              'active_points', 'seconds', 'phase_closed', 'optimizer_success', 'boundary',
              'diagnostic_only', 'omitted_norad', 'phase_scale'}
    if (Path(name).name == 'screen.json' and len(keys) == 3 and keys[0] == 'cavity'
            and keys[1] in ('c0', 'fitted_c') and key == 'seconds' and set(a) == cavity
            and all(v['diagnostic_only'] is True and v['phase_closed'] is True
                    and v['optimizer_success'] is True for v in (a, b))
            and finite_time(x, 1200) and finite_time(y, 1200)):
        return 'completed_cavity_fit_duration'
    return None


def log_accounting(name, text):
    """Retain endpoint/status text; normalize only two reviewed timing messages."""
    basename = Path(name).name
    patterns = []
    if basename == 'algo02.log':
        patterns = [r'(SCAN complete seconds )([0-9]+(?:\.[0-9]+)?)']
    elif re.fullmatch(r'target-[0-9]+-(inclusion|retry)\.log', basename):
        patterns = [r'(SCAN (?:control|new_family) (?:c0|fitted_c) endpoint '
                    r'\[[^\]\n]+\] seconds )([0-9]+(?:\.[0-9]+)?)']
    output, changed = [], 0
    for line in text.splitlines(keepends=True):
        body = line.removesuffix('\n')
        for pattern in patterns:
            match = re.fullmatch(pattern, body)
            if match and finite_time(float(match[2]), 1200):
                line = match[1]+'<WALL_SECONDS>'+('\n' if line.endswith('\n') else '')
                changed += 1
                break
        output.append(line)
    return ''.join(output), changed
