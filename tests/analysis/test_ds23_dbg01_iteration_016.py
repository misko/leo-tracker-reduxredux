import csv
import run_ds23_dbg01_iteration_016 as study


def test_next_batch_uses_unchanged_benchmark_and_closed015_cases():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    assert study.batch_cases(rows)==['DS23-0386','DS23-0409']
    assert 'DS23-0273' in study.CLOSED and 'DS23-0049' in study.CLOSED


def test_existing_engine_and_all_thirteen_scientific_stages_are_retained():
    assert study.engine is study.previous.engine
    assert study.STAGES==study.previous.STAGES and len(study.STAGES)==13
