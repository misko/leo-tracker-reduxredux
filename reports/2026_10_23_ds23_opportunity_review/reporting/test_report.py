import csv
import json
import numpy as np
from report import ROOT, STAGES, summarize, decompose


def test_complete_matched_stage_population_and_accounting():
    rows = list(csv.DictReader(STAGES.open()))
    assert {r['case'] for r in rows if r['arm'] == 'c0'} == {r['case'] for r in rows if r['arm'] == 'fitted_c'}
    result = summarize(rows)
    for arm in ('c0', 'fitted_c'):
        rr = [r for r in result if r['arm'] == arm]
        assert all(r['scans'] == 410 for r in rr)
        assert rr[0]['associated_points'] + rr[1]['incremental_points'] == rr[1]['associated_points']
        assert rr[1]['associated_points'] + rr[2]['incremental_points'] == rr[2]['associated_points']


def test_decomposition_replays_full_score_and_alternative_endpoint_difference():
    rows = json.loads((ROOT / 'mean_shape.json').read_text())['rows']
    for r in decompose(rows):
        assert np.isclose(r['full_score_delta'], r['curved_delta'] + r['contrasts_delta'] + r['conditional_levels_delta'])
        assert np.isclose(r['contrast_only_endpoint_delta'], r['full_score_delta'] - r['conditional_levels_delta'])
