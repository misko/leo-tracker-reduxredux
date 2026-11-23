import numpy as np
import pytest

from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v3.retained_position import PositionNormal
from tests.analysis.test_localization_v3_position import prepared
from tools.pipeline_eval.variants.algo08_incremental_layout import incremental_layout


@pytest.mark.parametrize("model", [NormalPosition, PositionNormal])
@pytest.mark.parametrize("fitted", [False, True])
def test_reuse_preserves_fresh_mask_reference_and_likelihood(model, fitted):
    scan, node = prepared()
    mask = np.arange(len(scan.tracks[0]["times"])) % 3 != 0
    phase = np.array([.21])
    point = np.array([1.25, -2.5])
    stock = model(scan, node, 150., fitted, reference=phase, keep=mask)
    with incremental_layout() as counts:
        first = model(scan, node, 150., fitted, reference=np.array([.15]))
        first.constants.fill(0.)
        first.phase_sigma.fill(19.)
        first.sky["position_km"].fill(1.)
        actual = model(scan, node, 150., fitted, reference=phase, keep=mask)
        assert counts["fixed_constructions"] == counts["reused_fixed_constructions"] == 1
        assert counts["mask_calls"] == 2
    assert actual.reference is phase
    assert actual.keep is mask
    calculated = actual.calculate(point)
    for name, expected in stock.calculate(point).items():
        assert np.asarray(calculated[name]).tobytes() == np.asarray(expected).tobytes()


def test_alias_calibration_or_replaced_scan_input_use_fresh_preparation():
    scan, node = prepared()
    phase = np.array([.1])
    with incremental_layout() as counts:
        a = NormalPosition(scan, node, 150., False, reference=phase)
        node["aliases"][0] += 1
        b = NormalPosition(scan, node, 150., False, reference=phase)
        c = NormalPosition(scan, node, 150., True, reference=phase)
        scan.search_region = SearchRegion((1., 0.), width_km=20.)
        d = NormalPosition(scan, node, 150., True, reference=phase)
        assert counts["fixed_constructions"] == 4
        assert counts["reused_fixed_constructions"] == 0
    assert a.alias != b.alias
    assert b.hardware.shape[1] + 1 == c.hardware.shape[1]
    assert d.upper[0] == 10.


def test_invalid_mask_still_reaches_frozen_validation_on_reuse():
    scan, node = prepared()
    phase = np.array([.15])
    with incremental_layout() as counts:
        problem = NormalPosition(scan, node, 150., False, reference=phase)
        with pytest.raises(ValueError, match="nonempty observation mask"):
            NormalPosition(scan, node, 150., False, reference=phase,
                           keep=np.zeros_like(problem.keep))
        assert counts["fixed_constructions"] == counts["reused_fixed_constructions"] == 1
