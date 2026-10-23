import csv
import run_ds23_dbg01_iteration_017 as study


def test_next_two_and_all_original_stages_are_preserved():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    assert study.engine.next_cases(rows,closed=study.CLOSED)==['DS23-0075','DS23-0087']
    assert study.STAGES==study.previous.STAGES and len(study.STAGES)==13


def test_every_output_binding_and_existing_guard_targets017():
    study.configure()
    assert study.engine.RAW==study.engine.baseline.OUT==study.engine.dbg.PARENT==study.RAW
    assert study.engine.reentry.OUT==study.RAW/'single_curve_reentry'
    assert study.engine.support.NOMINATIONS==study.engine.finalize.OLD==study.engine.reentry.OUT
    assert study.engine.reentry.nominate is study.whole_track_guard.guarded_nomination
    assert study.engine.dbg.engine.bank is study.bank_guard.bank_with_optional_archive
