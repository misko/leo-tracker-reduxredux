import csv

import run_ds23_dbg01_iteration_006 as study


def test_next_batch_skips_closed_cases_without_changing_evaluation_population():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    before=list(rows)
    assert study.batch_cases(rows)==['DS23-0069','DS23-0291']
    assert rows==before
    assert any(r['case']=='DS23-0405' for r in rows)


def test_all_reused_engines_bind_to_the_new_current_assignment_context():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.reentry.DEBUG==study.RAW
    assert study.engine.audit.OUT==study.RAW
    assert study.engine.dbg.PARENT==study.RAW
    assert study.engine.baseline.setup is study.engine.current_setup
