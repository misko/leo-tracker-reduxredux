import json

import pytest
from report_algo07_star_cohort import report, side_state
from verify_algo07_star import CONFIG, digest


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(tmp_path):
    plan = tmp_path / 'plan.json'
    iteration = tmp_path / 'iteration'
    dump(plan, dict(kind='algo07-star-cohort-execution-plan', fast_members=3,
                   available_members=2, unavailable_members=1,
                   execution_order=['DS26-0001', 'DS26-0002'], members=[
                       dict(dataset_label=f'DS26-{n:04}', availability=(
                           'available' if n < 3 else 'no_native_run'), run_id=f'run-{n}')
                       for n in range(1, 4)]))
    case = iteration / 'DS26-0001'
    config = dict(kind='algo07-star-verification-case', schema_version=1, run_id='run-1',
                  pins={'manifest': 'pin'}, candidate_terminal_read_reuse=True,
                  candidate_source_pins={'source.py': 'source-hash'})
    executions = {}
    for side in ('reference', 'candidate'):
        path = case / f'verify-run-{side}-0001/execution.json'
        dump(path, dict(state='scientific_complete'))
        dump(path.parent / 'outcome.json', dict(exit_code=0))
        executions[side] = dict(path=str(path), sha256=digest(path))
    dump(case / CONFIG, config)
    passed = dict(state='PASS', requested_scope='science', scientific_parity=True,
                  case_full_parity=False, publication_parity='not_checked',
                  configuration_sha256=digest(case / CONFIG), executions=executions,
                  scientific_difference_count=0, link_error_count=0)
    dump(case / 'verify-check-0001/summary.json', passed)
    return plan, iteration, case, config, passed


def test_denominator_and_narrow_pass_scope_remain_visible(tmp_path):
    plan, iteration, _, _, _ = fixture(tmp_path)
    result = report(plan, iteration)
    assert result['cohort_members'] == 3
    assert result['counts']['available'] == 2
    assert result['counts']['unavailable'] == 1
    assert result['counts']['not_initialized'] == 1
    assert result['counts']['recorded_science_pass'] == 1
    assert result['counts']['recorded_full_pass'] == 0
    assert len(result['members']) == 3
    assert not result['ds26_equivalence_verified']
    assert not result['scientific_exports_rehashed']
    assert not result['live_processes_checked']


def test_unfinished_attempt_is_not_reported_as_old_complete_execution(tmp_path):
    _, _, case, config, _ = fixture(tmp_path)
    (case / 'verify-run-candidate-0002').mkdir()
    assert side_state(case, config, 'candidate') == 'unfinished_attempt_receipt'
    dump(case / 'verify-run-candidate-0002/outcome.json', dict(exit_code=1))
    assert side_state(case, config, 'candidate') == 'failed_attempt'


def test_failed_history_is_preserved_after_a_recorded_pass(tmp_path):
    plan, iteration, case, _, passed = fixture(tmp_path)
    dump(case / 'verify-check-0001/summary.json', dict(state='FAIL', error='Different work'))
    dump(case / 'verify-check-0002/summary.json', passed)
    (case / 'verify-check-0003').mkdir()
    result = report(plan, iteration)
    assert result['counts']['recorded_science_pass'] == 1
    assert result['counts']['cases_with_recorded_failed_checks'] == 1
    assert result['counts']['unfinished_check_receipts'] == 1
    assert len(result['members'][0]['checks']) == 3


@pytest.mark.parametrize('corruption', ['config', 'execution', 'wrong_run', 'full_claim'])
def test_changed_bindings_and_contradictory_claims_are_rejected(tmp_path, corruption):
    plan, iteration, case, config, passed = fixture(tmp_path)
    if corruption == 'config':
        dump(case / CONFIG, dict(config, extra='changed after check'))
    elif corruption == 'execution':
        dump(case / 'verify-run-candidate-0001/execution.json', dict(state='checkpointed'))
    elif corruption == 'wrong_run':
        dump(case / CONFIG, dict(config, run_id='different-native-input'))
    else:
        dump(case / 'verify-check-0001/summary.json', dict(passed, case_full_parity=True))
    with pytest.raises(ValueError):
        report(plan, iteration)


def test_mixed_iteration_pins_and_extra_cases_cannot_disappear(tmp_path):
    plan, iteration, _, config, _ = fixture(tmp_path)
    other = iteration / 'DS26-0002'
    dump(other / CONFIG, dict(config, run_id='run-2', pins={'manifest': 'different'}))
    with pytest.raises(ValueError, match='Mixed'):
        report(plan, iteration)
    dump(other / CONFIG, dict(config, run_id='run-2'))
    dump(iteration / 'DS26-9999' / CONFIG, config)
    with pytest.raises(ValueError, match='outside'):
        report(plan, iteration)


def test_missing_or_duplicate_membership_is_rejected(tmp_path):
    plan, iteration, _, _, _ = fixture(tmp_path)
    value = json.loads(plan.read_text())
    value['members'][1] = value['members'][0]
    dump(plan, value)
    with pytest.raises(ValueError, match='denominator'):
        report(plan, iteration)
