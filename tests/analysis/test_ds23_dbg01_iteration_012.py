import csv

import run_ds23_dbg01_iteration_012 as study


def test_next_unclosed_cases_preserve_the_published_benchmark():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()));before=list(rows)
    assert study.batch_cases(rows)==['DS23-0215','DS23-0281']
    assert rows==before and {'DS23-0163','DS23-0209'}<=set(study.CLOSED)


def test_current_output_retains_whole_track_and_missing_archive_guards():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.audit.REENTRY==study.RAW/'single_curve_reentry'
    assert study.engine.reentry.nominate is study.previous.previous.previous.guarded_nomination
    assert study.engine.dbg.engine.bank is study.previous.bank_repair.bank_with_optional_archive
