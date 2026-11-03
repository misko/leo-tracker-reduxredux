import csv

import run_ds23_dbg01_iteration_010 as study
from run_algo01_ds23_sample import write


def test_next_two_cases_and_whole_input_guard_preserve_existing_engine():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    assert study.batch_cases(rows)==['DS23-0080','DS23-0257']
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.audit.REENTRY==study.RAW/'single_curve_reentry'
    assert study.engine.reentry.nominate is study.previous.guarded_nomination


def test_zero_shell_exit_does_not_override_failed_scientific_receipt(tmp_path):
    path=tmp_path/'single_curve_reentry/nominations_execution.json';path.parent.mkdir()
    write(path,dict(all_terminal=True,all_passed=False,rows=[dict(status='failed')]))
    assert not study.stage_passed('nominations',tmp_path,[])
    write(path,dict(all_terminal=True,all_passed=True,rows=[dict(status='complete')]))
    assert study.stage_passed('nominations',tmp_path,[])


def test_restart_receipt_requires_all_requested_cases(tmp_path):
    p=tmp_path/'RF_restart_selection.json'
    write(p,dict(selection_frozen_before_new_geographic_error_comparison=True,rows=[dict(case='a')]))
    assert not study.stage_passed('restart_selection',tmp_path,['a','b'])
    assert study.stage_passed('restart_selection',tmp_path,['a'])
