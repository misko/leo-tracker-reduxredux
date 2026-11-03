import csv

import run_ds23_dbg01_iteration_011 as study


def test_next_batch_moves_to_unclosed_cases_with_the_same_benchmark_population():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()));before=list(rows)
    assert study.batch_cases(rows)==['DS23-0163','DS23-0209']
    assert rows==before and {'DS23-0080','DS23-0257'}<=set(study.CLOSED)


def test_whole_track_and_rescued_bank_guards_bind_only_the_current_output():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.audit.REENTRY==study.RAW/'single_curve_reentry'
    assert study.engine.reentry.nominate is study.previous.previous.guarded_nomination
    assert study.engine.dbg.engine.bank is study.bank_repair.bank_with_optional_archive
