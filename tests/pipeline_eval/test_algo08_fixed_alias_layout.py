import numpy as np
import pytest

from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared
from tools.pipeline_eval.variants.algo08_fixed_alias_layout import measured_fixed_alias_layout


@pytest.mark.parametrize("fitted", [False, True])
def test_explicit_alias_layout_leaves_full_and_held_data_likelihood_exact(fitted):
    scan, node = prepared()
    node["aliases"] = [node["aliases"][0] + 1]
    node["seed"]["state"]["phases"][:] = -1.25
    keep = np.arange(len(scan.tracks[0]["times"])) % 3 != 0
    location = np.array([2.7, -1.9])
    options = dict(reference=np.array([0.15]), keep=keep)
    stock = NormalPosition(scan, node, 150., fitted, **options)
    with measured_fixed_alias_layout(enabled=True) as counts:
        direct = NormalPosition(scan, node, 150., fitted, **options)
    assert counts["direct_layouts"] == counts["explicit_aliases"] == counts["calls"] == 1
    assert counts["layout_fallbacks"] == 0
    assert direct.alias == stock.alias == node["aliases"]
    assert (direct.rows, direct.labels, direct.members, direct.slices) == (
        stock.rows, stock.labels, stock.members, stock.slices)
    expected = stock.calculate(location)
    actual = direct.calculate(location)
    assert actual.keys() == expected.keys()
    for key in expected:
        np.testing.assert_array_equal(actual[key], expected[key], err_msg=key)
    np.testing.assert_array_equal(direct.residual(location), stock.residual(location))


def test_nomination_and_seed_outside_supported_time_use_original_constructor():
    scan, node = prepared()
    stock = JointMarginal(scan, node["seed"], True, variant="radio_noise")
    with measured_fixed_alias_layout(enabled=True) as counts:
        nomination = JointMarginal(scan, node["seed"], True, variant="radio_noise")
        assert nomination.alias == stock.alias
        scan.tracks[0]["times"][0] = -9.
        node["seed"]["state"]["phases"][:] = -15.
        with pytest.raises(ValueError, match="never extrapolates"):
            JointMarginal(scan, node["seed"], True, variant="radio_noise", aliases=node["aliases"])
    assert counts["calls"] == 2
    assert counts["explicit_aliases"] == counts["layout_fallbacks"] == 1
    assert counts["direct_layouts"] == 0
