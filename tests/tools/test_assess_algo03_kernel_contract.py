from pathlib import Path

import pytest
from assess_algo03_kernel_contract import assess

PROTOCOL = (Path(__file__).resolve().parents[2]
            /'reports/2026_11_03_algo07_runtime_iteration002/protocol.json').read_bytes()


def strict(path, a=1., b=1.+1e-15):
    return dict(passed=False, differences=[dict(path=path, baseline=a, candidate=b)],
                both_calibration_arms_required=True, tolerance=0, exact_leaves=20,
                verified_runtime_files=[2046, 2050])


def test_original_bounds_apply_only_to_kernel_diagnostics():
    r = assess(strict('trial/orbital_map_mean/0/1'), PROTOCOL)
    assert r['passed'] and not r['strict_comparison_passed']
    assert len(r['roundoff_differences']) == 1
    assert not assess(strict('trial/position/latitude_deg'), PROTOCOL)['passed']
    assert not assess(strict('trial/negative_twice_elbo'), PROTOCOL)['passed']
    assert not assess(strict('trial/orbital_map_mean/position/latitude'), PROTOCOL)['passed']
    assert not assess(strict('trial/phase_marginals/0/1', 0., 1e-7), PROTOCOL)['passed']
    assert not assess(strict('trial/orbital_map_mean/0/1', 0., float('nan')), PROTOCOL)['passed']


def test_protocol_and_complete_comparison_are_required():
    with pytest.raises(ValueError, match='Original predeclared'):
        assess(strict('trial/phase_marginals/0/1'), PROTOCOL+b' ')
    value = strict('trial/phase_marginals/0/1')
    value['both_calibration_arms_required'] = False
    with pytest.raises(ValueError, match='Complete pinned'):
        assess(value, PROTOCOL)
