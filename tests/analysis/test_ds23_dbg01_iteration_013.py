import csv

import run_ds23_dbg01_iteration_013 as study


def test_next_cases_close012_without_excluding_scans_from_the_benchmark():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()));before=list(rows)
    assert study.batch_cases(rows)==['DS23-0234','DS23-0064']
    assert rows==before and {'DS23-0215','DS23-0281'}<=set(study.CLOSED)


def test_numerical_receipt_and_input_guards_remain_bound_to_the_new_output():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.audit.REENTRY==study.RAW/'single_curve_reentry'
    assert study.engine.reentry.nominate is study.whole_track_guard.guarded_nomination
    assert study.engine.dbg.engine.bank is study.bank_guard.bank_with_optional_archive
