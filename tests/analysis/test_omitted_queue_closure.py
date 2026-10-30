import csv
import json
from argparse import Namespace
import pytest
from report_omitted_queue_closure import run


def fixture_args(tmp_path):
    report = tmp_path/'batch'; report.mkdir()
    registry = tmp_path/'registry'; registry.mkdir()
    row = dict(track_id='a', points=2, qualified=True, capture_mode='adaptive',
        c0_before_km=1., c0_after_km=.5, fitted_c_before_km=1., fitted_c_after_km=.5)
    for name, rows in [('final_positions.csv',[row]), ('annotations.csv',[
            dict(track_id='a',status='conditionally_supported_identity')])]:
        with (report/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (registry/'pending_candidates.json').write_text(json.dumps([dict(track_id='a')]))
    (report/'series_qualified_trials.json').write_text(json.dumps([
        dict(track_id='a', reviewed_candidate=False, norad=1, observation_ids=['x','y'])]))
    return Namespace(reports=[report],registry=registry,output=tmp_path/'out')


def test_closure_honors_later_withholding_over_original_pass(tmp_path):
    args=fixture_args(tmp_path);run(args)
    d=json.loads((args.output/'summary.json').read_text())
    assert d['reviewed_points']==0
    assert d['states']==[dict(state='common_residual_withheld',tracks=1,points=2)]
    assert d['individual_candidate_error_direction']['fitted_c']==dict(improved=0,worsened=0)


def test_closure_refuses_incomplete_registry_coverage(tmp_path):
    args=fixture_args(tmp_path)
    (args.registry/'pending_candidates.json').write_text(json.dumps([dict(track_id='a'),dict(track_id='b')]))
    with pytest.raises(ValueError,match='exactly cover'):
        run(args)
