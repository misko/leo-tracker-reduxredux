import numpy as np
import pytest

from leo.analysis.localization_v3.discovery_likelihood import DiscoveryPosition
from leo.analysis.localization_v3.event_position import make_event_problem
from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.history_position import make_problem
from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.retained_position import PositionNormal
from tests.analysis.test_localization_v3_position import prepared


@pytest.mark.parametrize("kind", ["normal", "event", "history", "retained", "discovery"])
def test_every_likelihood_uses_explicit_scan_bound_and_preserves_result(kind):
    scan, node = prepared()
    assert scan.bound is hierarchical_bound
    calls = []

    def injected(*args, **kwargs):
        calls.append(True)
        return hierarchical_bound(*args, **kwargs)

    scan.bound = injected
    scan.previous_sources = {}
    scan.elements = {"99999": dict(provenance=dict(element_epoch_utc_ns=0))}
    args = (scan, node, np.ones(41, bool), "c0", np.zeros(1), np.ones(1), np.zeros(1))
    if kind == "normal":
        p = NormalPosition(scan, node, 150., False)
    elif kind == "history":
        p = make_problem(*args, 1., None)
    elif kind == "event":
        p = make_event_problem(*args, dict(multiplier=1., nu=None),
                               [dict(kind="receiver", receiver=1, time_s=150., sigma_hz=300.)])
    elif kind == "retained":
        p = PositionNormal(scan, node, 150., False, scale_labels=[0])
    else:
        p = DiscoveryPosition(scan, node["seed"], False, aliases=node["aliases"])
    assert p.scan.bound is injected
    p.scan.bound = hierarchical_bound
    expected = p.calculate(np.zeros(2))
    p.scan.bound = injected
    actual = p.calculate(np.zeros(2))
    assert calls == [True]
    for name in actual:
        np.testing.assert_equal(actual[name], expected[name])
