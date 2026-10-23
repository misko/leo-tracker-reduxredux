"""The next debug batch preserves the benchmark and bounded selection policy."""

import csv
import run_ds23_dbg01_iteration_014 as study


def test_next_two_worst_unclosed_cases():
    rows=list(csv.DictReader(study.engine.baseline.BENCHMARK.open()))
    assert study.batch_cases(rows)==['DS23-0202','DS23-0262']
    assert 'DS23-0234' in study.CLOSED and 'DS23-0064' in study.CLOSED


def test_existing_engine_and_guards_are_retained():
    assert study.engine is study.previous.engine
    assert study.STAGES==study.previous.STAGES
    assert str(study.RAW).endswith('2026_10_23_ds23_dbg01_iteration_014_raw')
