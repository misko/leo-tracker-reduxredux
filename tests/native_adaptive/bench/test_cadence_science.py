"""Joined scientific gates must reject a loss despite successful timing."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from evaluate_arm_cadence import evaluate_scan
from evaluate_recorded_pacing import load_reference


def setup(tmp_path):
    actual=tmp_path/'actual';actual.mkdir();chain=actual/'results';chain.mkdir()
    reference=tmp_path/'reference';reference.mkdir()
    candidate=[0,0,0,722,-100,-100,.4,.1,.3,1]
    rows=[dict(sequence=0,accepted=True,status=0,candidates=[candidate],positive=1,
               io_ms=1,producer_late_ms=1,queue_ms=0,service_ms=100,due_to_finish_ms=101),
          dict(kind='summary',arrivals=1,completed=1,failed=0,rejected=0,
               queue_high_water=1,max_rss_kib=100,wall_ms=101)]
    (actual/'detector.stdout').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    for name,value in [('observations.tsv','candidate_id\tvalue\na\t1\n'),
                       ('graph.tsv','META\tscan\nidentity\tvalue\na\t1\n')]:
        (reference/name).write_text(value);(actual/name).write_text(value)
    search={'schema':'test','evaluated_points':400,'budget_points':400,'deferred_cells':1,
            'complete':False,'stop_reason':'budget','evaluations':[[i,0,1.] for i in range(400)],
            'selected':{'east_km':0,'north_km':0,'score_hz':1.}}
    values={'seeds.stdout':'seed\n','tracks.stdout':'track\n','search.stdout':json.dumps(search),
            'associations.json':'{"satellite":123}\n'}
    for name,value in values.items():(chain/name).write_text(value);(reference/name).write_text(value)
    receipt={'scope':'whole_process','exit_code':0,'wall_s':1,'cpu_s':1,'max_rss_kib':100}
    for path in [actual/'detector.stderr',actual/'downstream.stderr',*[chain/(n+'.stderr') for n in ['seeds','tracks','search']]]:
        path.write_text(json.dumps(receipt)+'\n')
    return (actual,[[candidate]],reference,*[reference/n for n in
             ['seeds.stdout','tracks.stdout','search.stdout','search.stdout','associations.json']],1e-9)


def test_complete_joined_controls(tmp_path):
    assert evaluate_scan(*setup(tmp_path))['passed']


@pytest.mark.parametrize('changed',['observations.tsv','results/tracks.stdout','results/associations.json'])
def test_successful_timing_does_not_hide_changed_science(tmp_path,changed):
    args=setup(tmp_path);path=args[0]/changed
    path.write_text(path.read_text().replace('1','2') if changed=='observations.tsv' else 'changed\n')
    assert not evaluate_scan(*args)['passed']


def test_failed_stage_receipt_is_not_qualification(tmp_path):
    args=setup(tmp_path);(args[0]/'downstream.stderr').write_text('{"scope":"whole_process","exit_code":3}\n')
    with pytest.raises(ValueError,match='timing receipt'):evaluate_scan(*args)


def test_missing_detector_reference_is_explicit_failure(tmp_path):
    with pytest.raises(ValueError,match='empty reference'):load_reference(tmp_path)
