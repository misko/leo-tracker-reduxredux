"""Reporting cannot precede terminal inference; geometry arithmetic sanity."""
import json

import pytest

import position_evaluate as report


def test_distance_geometry_without_any_real_reference():
    assert report.distance_km([0.,0.],[0.,0.])==0.
    assert report.distance_km([0.,0.],[1.,0.])==pytest.approx(111.1950802335)


def test_unsealed_inference_blocks_reporting_before_GPS_access(tmp_path,monkeypatch):
    monkeypatch.setattr(report,'HERE',tmp_path)
    (tmp_path/'position_terminal_seal.json').write_text(json.dumps(dict(all_terminal=False,evaluation_now_permitted=False)))
    (tmp_path/'position_protocol_v2.json').write_text('{}')
    with pytest.raises(AssertionError):report.evaluate()
    assert not (tmp_path/'position_inference_audit.json').exists()
    assert not (tmp_path/'position_evaluation.json').exists()
