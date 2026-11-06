import pytest
from probe_algo07v3_control_view import ControlViewPairs

from leo.analysis.localization_v3.scan import ScanLikelihood


def fixture():
    scan = object.__new__(ScanLikelihood)
    scan.tracks, scan.white, scan.rx_basis = ['a'], [1], [2]
    scan.geometry = {'expensive discovery data': [1, 2]}
    scan.sky = {'retained': [3]}
    d = dict(scan=scan, node={}, keep=[True], powers=[1.], means=[0.], model={}, entries=[])
    return d, {'policy': {}}


def test_view_is_enforced_restored_and_results_are_private():
    d, inventory = fixture()
    original, calls = d['scan'], []
    pairs = ControlViewPairs(True)

    def compute():
        calls.append(1)
        assert d['scan'] is not original
        assert not hasattr(d['scan'], 'geometry')
        return {'c0': [1.], 'fitted_c': [2.]}

    args = (True, 'fit_shared', d, inventory, 1, False)
    first = pairs(compute, *args)
    first['c0'][0] = 99.
    assert pairs(compute, *args)['c0'] == [1.]
    assert len(calls) == 1 and d['scan'] is original
    assert original.geometry == {'expensive discovery data': [1, 2]}
    d['scan'].sky['retained'][0] = 4
    pairs(compute, *args)
    assert len(calls) == 2


def test_missing_dependency_fails_and_restores_context():
    d, inventory = fixture()
    original = d['scan']
    pairs = ControlViewPairs(True)
    with pytest.raises(AttributeError):
        pairs(lambda: d['scan'].geometry, True, 'fit_shared', d, inventory, 1, False)
    assert d['scan'] is original and not pairs.rows


@pytest.mark.parametrize('case', ['target', 'stateful', 'factory', 'conditional', 'override'])
def test_unsafe_and_target_routes_keep_original_scan(case):
    d, inventory = fixture()
    original = d['scan']
    if case == 'stateful':
        d['numerical_policy'] = object()
    if case == 'factory':
        d['problem_factory'] = object()
    if case == 'override':
        original.hardware = lambda *args: 0
    pairs = ControlViewPairs(True)
    result = pairs(lambda: d['scan'] is original, case != 'target', 'fit_shared',
                   d, inventory, 1, case == 'conditional')
    assert result and not pairs.rows
