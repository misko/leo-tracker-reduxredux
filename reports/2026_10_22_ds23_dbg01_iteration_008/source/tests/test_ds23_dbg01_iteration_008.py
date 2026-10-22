import csv

import run_ds23_dbg01_iteration_008 as study


def test_next_cases_keep_the_archived_benchmark_and_close_only_completed_debug_cases():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()));original=list(rows)
    assert study.batch_cases(rows)==['DS23-0157','DS23-0207']
    assert rows==original and {'DS23-0227','DS23-0400'}<=set(study.CLOSED)


def test_current_assignment_context_still_uses_the_existing_engine():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.dbg.PARENT==study.RAW
    assert study.engine.baseline.setup is study.engine.current_setup
