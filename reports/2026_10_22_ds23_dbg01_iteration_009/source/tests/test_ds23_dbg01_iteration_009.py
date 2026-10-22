import csv

import run_ds23_dbg01_iteration_009 as study


def test_next_two_scans_advance_without_changing_the_published_population():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()));before=list(rows)
    assert study.batch_cases(rows)==['DS23-0028','DS23-0311']
    assert rows==before and {'DS23-0157','DS23-0207'}<=set(study.CLOSED)


def test_existing_assignment_context_and_current_raw_bindings():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.audit.OUT==study.RAW
    assert study.engine.baseline.setup is study.engine.current_setup
