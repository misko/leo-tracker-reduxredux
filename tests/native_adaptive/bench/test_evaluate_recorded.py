import importlib.util
from pathlib import Path

import pytest


def evaluator():
    path=Path(__file__).resolve().parents[3]/'tools/evaluate_recorded_pacing.py'
    spec=importlib.util.spec_from_file_location('evaluate_paced',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.evaluate


def records():
    return [dict(sequence=0,accepted=True,status=0,candidates=[],positive=0,
                 io_ms=1,producer_late_ms=1000,queue_ms=0,service_ms=100,due_to_finish_ms=1100),
            dict(kind='summary',arrivals=1,completed=1,failed=0,rejected=0,
                 queue_high_water=1,max_rss_kib=100,wall_ms=1100)]


def test_no_drop_does_not_hide_producer_lateness():
    result=evaluator()(records(),[[]])
    assert result['scientific_match_for_all_arrivals']
    assert result['producer_late_ms']['max']==1000


def test_missing_arrival_fails():
    with pytest.raises(ValueError,match='arrival'):
        evaluator()(records(),[[],[]])


def test_detector_failure_is_accounted_separately():
    rows=records();rows[0]['status']=-1;rows[-1].update(completed=0,failed=1)
    result=evaluator()(rows,[[]])
    assert result['failed']==1
    assert not result['scientific_match_for_all_arrivals']


def test_changed_candidate_is_not_a_scientific_match():
    result=evaluator()(records(),[[[1]]])
    assert result['candidate_mismatch_visits']==[0]


def test_quarters_expose_growing_backlog():
    rows=records();first=rows[0]
    arrivals=[dict(first,sequence=i,producer_late_ms=i*100,queue_ms=i*10) for i in range(8)]
    summary=dict(rows[-1],arrivals=8,completed=8)
    result=evaluator()(arrivals+[summary],[[]]*8)
    assert len(result['quarters'])==4
    assert [q['first_sequence'] for q in result['quarters']]==[0,2,4,6]
    assert result['quarters'][-1]['queue_ms']['mean']>result['quarters'][0]['queue_ms']['mean']
