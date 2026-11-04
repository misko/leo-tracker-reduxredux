import copy

from algo07_star_accounting import classify, log_accounting
from diff_algo07_star_evidence import differences


def reasons(name, a, b, roles=None):
    return [classify(name, row, a, b, roles or ({}, {})) for row in differences(a, b)]


def test_unknown_and_nested_seconds_are_not_dropped():
    assert reasons('mystery.json', {'seconds': 1.0}, {'seconds': 2.0}) == [None]
    assert reasons('control.json', {'nuisance': {'seconds': 1.0}},
                   {'nuisance': {'seconds': 2.0}}) == [None]


def test_completed_receipt_duration_has_explicit_bound():
    a = dict(name='fit', status='complete', command=['/python'], budget_seconds=600,
             returncode=0, seconds=1.0)
    b = dict(a, seconds=2.0)
    assert reasons('receipt.json', a, b) == ['completed_subprocess_accounting']
    assert reasons('receipt.json', a, dict(b, seconds=601.0)) == [None]
    assert None in reasons('receipt.json', a, dict(b, returncode=1))


def test_decisions_and_endpoints_are_never_accounting():
    a = dict(job='scan', arms=dict(c0={'endpoint': 1.0}, fitted_c={'endpoint': 1.0}),
             paired_valid=True, target_entries=[], seconds=1.0)
    b = copy.deepcopy(a)
    b['arms']['c0']['endpoint'] = 2.0
    b['paired_valid'] = False
    b['seconds'] = 2.0
    assert reasons('control.json', a, b) == [None, None, 'known_result_top_level_duration']


def test_process_ids_require_the_same_verified_role():
    a = dict(stage='fit', returncode=0, process_id=100, seconds=1.0)
    b = dict(a, process_id=200)
    assert reasons('terminal.json', a, b) == [None]
    assert reasons('terminal.json', a, b, ({100: 'stage/root'}, {200: 'stage/root'})) == \
        ['verified_stage_process']
    assert reasons('terminal.json', a, b, ({100: 'stage/root'}, {200: 'other/root'})) == [None]


def test_command_budget_must_match_explicit_launch_bound():
    a = dict(policy='gap_conditional', command=['/python', '--maximum-seconds', '1100'],
             maximum_seconds=1100)
    b = dict(a, command=['/python', '--maximum-seconds', '1110'], maximum_seconds=1110)
    assert reasons('launch.json', a, b) == ['remaining_launch_budget', 'remaining_launch_budget']
    b['command'][1] = '--phase-rounds'
    assert None in reasons('launch.json', a, b)


def test_root_scientific_duration_does_not_allow_nonfinite_or_unknown_shape():
    a = dict(case='SCAN', checks=[], targets=[], positions=[], scan_receipt={},
             bank_domain_s=[], seconds=1.0)
    assert reasons('SCAN.json', a, dict(a, seconds=2.0)) == ['known_result_top_level_duration']
    assert reasons('SCAN.json', a, dict(a, seconds=float('nan'))) == [None]
    assert reasons('SCAN.json', a, dict(a, seconds=True)) == [None]


def test_changed_solver_budget_is_never_a_wall_budget():
    a = dict(policy='gap_conditional', no_GPS_inference=True, maxiter=100,
             phase_rounds=3, maximum_seconds=1100)
    b = dict(a, maxiter=110, phase_rounds=4)
    assert reasons('protocol.json', a, b) == [None, None]


def test_log_timing_preserves_scientific_endpoint_and_status():
    a = 'SCAN control c0 endpoint [ 1.0 2.0 ] seconds 3.2\n'
    b = a.replace('3.2', '4.1')
    assert log_accounting('target-1-inclusion.log', a) == \
        log_accounting('target-1-inclusion.log', b)
    c = b.replace('1.0 2.0', '1.1 2.0')
    assert log_accounting('target-1-inclusion.log', a) != \
        log_accounting('target-1-inclusion.log', c)
    assert log_accounting('unknown.log', a) == (a, 0)
    bad = a.replace('3.2', 'nan')
    assert log_accounting('target-1-inclusion.log', bad) == (bad, 0)


def test_standalone_audit_requires_a_verified_process_role():
    a = dict(verified=True, all_launched_processes_accounted=True, denied_paths=[],
             receipts=2, expected=2, root_process_id=100)
    b = dict(a, root_process_id=200)
    roles = ({100: 'fit/root'}, {200: 'fit/root'})
    assert reasons('read-audit.json', a, b, roles) == ['verified_process_identity']
    assert reasons('unknown.json', a, b, roles) == [None]


def test_cavity_duration_keeps_objective_and_requires_completed_fit():
    fit = dict(x=[], latlon=[], error_m=None, objective=2.0, rms_hz=3.0, history=[],
               reference=None, active_points=20, seconds=1.0, phase_closed=True,
               optimizer_success=True, boundary=False, diagnostic_only=True,
               omitted_norad=12345, phase_scale=1.0)
    a = dict(cavity=dict(c0=fit, fitted_c=copy.deepcopy(fit)))
    b = copy.deepcopy(a)
    b['cavity']['c0']['seconds'] = 2.0
    assert reasons('screen.json', a, b) == ['completed_cavity_fit_duration']
    b['cavity']['c0']['objective'] = 1.0
    assert None in reasons('screen.json', a, b)
    b['cavity']['c0']['optimizer_success'] = False
    assert all(v is None for v in reasons('screen.json', a, b))
