import csv

import run_ds23_dbg01_iteration_007 as study


def test_next_cases_preserve_all_benchmark_cases_and_skip_only_closed_debug_cases():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()));before=list(rows)
    assert study.batch_cases(rows)==['DS23-0227','DS23-0400']
    assert rows==before and any(r['case']=='DS23-0405' for r in rows)


def test_current_assignment_context_and_diagnostic_output_bindings():
    study.configure()
    assert study.engine.baseline.OUT==study.RAW
    assert study.engine.reentry.DEBUG==study.RAW
    assert study.engine.audit.OUT==study.RAW
    assert study.engine.dbg.PARENT==study.RAW
    assert study.engine.baseline.setup is study.engine.current_setup
