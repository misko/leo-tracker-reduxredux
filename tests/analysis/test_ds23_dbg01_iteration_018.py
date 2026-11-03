import csv
import run_ds23_dbg01_iteration_018 as study


def test_queue_closes017_and_keeps_all_scientific_stages():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    assert study.batch_cases(rows)==['DS23-0239','DS23-0261']
    assert study.STAGES==study.previous.STAGES and len(study.STAGES)==13


def test_existing_guards_and_all_driver_outputs_are_bound_to018():
    study.configure()
    assert study.engine.baseline.OUT==study.engine.dbg.PARENT==study.RAW
    assert study.engine.reentry.OUT==study.RAW/'single_curve_reentry'
    assert study.engine.support.NOMINATIONS==study.engine.finalize.OLD==study.engine.reentry.OUT
    assert study.engine.reentry.nominate is study.whole_track_guard.guarded_nomination
    assert study.engine.dbg.engine.bank is study.bank_guard.bank_with_optional_archive
