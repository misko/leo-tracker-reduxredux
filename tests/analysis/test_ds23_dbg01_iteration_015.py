import csv
import run_ds23_dbg01_iteration_015 as study


def test_next_two_cases_use_the_unchanged_reference_and_closed014_queue():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    assert study.batch_cases(rows)==['DS23-0273','DS23-0049']
    assert 'DS23-0202' in study.CLOSED and 'DS23-0262' in study.CLOSED


def test_existing_engine_and_all_scientific_stages_are_retained():
    assert study.engine is study.previous.engine
    assert study.STAGES==study.previous.STAGES and len(study.STAGES)==13
