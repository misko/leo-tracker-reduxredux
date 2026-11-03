import json
from pathlib import Path

import numpy as np

from subset_position_search import design, select_subset, SubsetEngine

HERE = Path(__file__).parent


def test_selection_is_nested_and_full_identical():
    for scan in 'AB':
        cases = json.loads((HERE / f'subset-position-search/{scan}-subsets.json').read_text())['cases']
        full = []
        for method in ('rms', 'support', 'glrt'):
            selected = sorted((r for r in cases if r['method'] == method), key=lambda r: r['fraction'])
            for small, large in zip(selected, selected[1:]):
                assert set(small['original_rows']) <= set(large['original_rows'])
                assert set(small['numbers']) <= set(large['numbers'])
            full.append(selected[-1])
        for r in full[1:]:
            assert r['rows'] == full[0]['rows']
            assert r['numbers'] == full[0]['numbers']


def test_glrt_tie_break_and_direction():
    numbers = np.array([1, 2]); ids = np.array([4, 3, 2, 1])
    owners = np.array([1, 1, 2, 2]); scores = np.array([.1, .8, .8, .2])
    bank, keep = select_subset(numbers, ids, owners, scores, {1: 10, 2: 20}, .25, 'glrt')
    assert np.array_equal(bank, numbers)
    assert ids[keep].tolist() == [2]


def test_matched_rf_arms_and_fixed_roof():
    subset = json.loads((HERE / 'subset-position-search/A-subsets.json').read_text())['cases'][0]
    a = SubsetEngine('A', 'fitted-c', subset); b = SubsetEngine('A', 'zero-c', subset)
    for k in ['original_rows', 'numbers', 'measured', 'fixed_receiver_hz', 'rf']:
        np.testing.assert_array_equal(getattr(a.data, k), getattr(b.data, k))
    np.testing.assert_array_equal(a.obj.features, b.obj.features)
    assert b.obj.bounds[-1] == (0., 0.)
    assert a.obj.base.sigma_hz == b.obj.base.sigma_hz == 200
    assert a.lat == b.lat == 37.849056280893684
    assert a.lon == b.lon == -122.48575489722863
    assert a.obj.base.minimum_shift_s >= -20
    assert a.obj.base.maximum_shift_s <= 20


def test_design_within_requested_disk():
    assert len(design()) == 21
    assert max(np.linalg.norm(p) for p in design()) <= 2 + 1e-12


def test_completed_searches():
    folder = HERE / 'subset-position-search'
    result_files = sorted(folder.glob('*-c.json'))
    assert len(result_files) == 40
    for path in result_files:
        r = json.loads(path.read_text())
        assert r['roof']['success'] and r['best']['success'], path
        assert r['successful_starts'] >= 1, path
        assert 'cross_restart_audit' in r, path
        assert r['distance_m'] <= 2000.00001, path
        assert r['delta_score'] <= 1e-7, path
        # A lower checked neighbor is retained as best found and explicitly
        # flagged as not having a local-minimum certificate.
        assert r['minimum_neighbor_delta'] >= -.001 or r['cross_restart_audit']['lower_point_after_neighbors'], path
        np.testing.assert_allclose(r['gradient_per_100m'], r['gradient_fd_10m'], atol=.005, rtol=.01)
        if r['arm'] == 'zero-c':
            assert r['roof']['c_hz_per_ghz'] == r['best']['c_hz_per_ghz'] == 0
        mate = json.loads((folder / f"{r['scan']}-{r['case_id']}-{'zero-c' if r['arm']=='fitted-c' else 'fitted-c'}.json").read_text())
        assert r['subset'] == mate['subset']
