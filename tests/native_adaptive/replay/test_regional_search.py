import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


def module():
    path = Path(__file__).resolve().parents[3] / 'tools/qualify_native_regional_search.py'
    spec = importlib.util.spec_from_file_location('regional_qualification', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_trace_compares_coordinates_before_scores():
    reference = {'diagnostics': {'search_trace': {'reno': [
        {'event': 'evaluate', 'east_km': 1, 'north_km': 2, 'weighted_mse_hz2': 9},
        {'event': 'evaluate', 'east_km': 3, 'north_km': 4, 'weighted_mse_hz2': 16}]}}}
    result = module().compare_trace({'evaluations': [[3, 4, 4.5], [1, 2, 3]]}, reference, 'reno')
    assert not result['same_ordered_sites']
    assert result['common_site_count'] == 2
    assert result['max_common_site_score_delta_hz'] == .5


@pytest.mark.parametrize('count', [400, 399])
def test_search_uses_prior_center_and_requires_full_budget(tmp_path, monkeypatch, count):
    tool = module()
    binary = tmp_path / 'binary'; binary.write_bytes(b'test binary')
    checkpoint = tmp_path / 'published-reference.loc1'; checkpoint.write_bytes(b'fixture')
    prior = {'name': 'sacramento', 'region': {'center_latitude_deg': 38.5,
             'center_longitude_deg': -121.5, 'radius_km': 250},
             'selected': {'east_km': -81.25, 'north_km': -68.75,
                          'capped_weighted_rmse_hz': 284},
             'accounting': {'deferred_cell_count': 75}}
    (tmp_path / 'server-reference.json').write_text(json.dumps({'priors': [prior]}))
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', ['tool', '--binary', str(binary), '--authority',
        str(tmp_path), '--input', str(checkpoint), '--prior', 'sacramento',
        '--published-memberships', str(output)])

    def run(argv, **kwargs):
        assert argv[3:6] == ['38.5', '-121.5', '250']
        assert kwargs['timeout'] == 300
        return subprocess.CompletedProcess(argv, 0, json.dumps({
            'selected': {'east_km': -81.25, 'north_km': -68.75, 'score_hz': 284.01},
            'evaluated_points': count, 'evaluations': [[0, 0, 0]] * count,
            'complete': False, 'stop_reason': 'point-budget-reached',
            'deferred_cells': 75}), '')

    monkeypatch.setattr(tool.subprocess, 'run', run)
    if count == 400:
        tool.main()
    else:
        with pytest.raises(ValueError, match='400 points'):
            tool.main()
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['status'] == ('complete' if count == 400 else 'failed')
    assert not receipt['search_complete']
