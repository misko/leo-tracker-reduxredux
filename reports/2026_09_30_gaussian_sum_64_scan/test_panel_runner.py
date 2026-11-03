import numpy as np

from leo.analysis.gaussian_sum_location import FilterState, GaussianComponent
from physics import StateLayout
from prior import build_uniform_prior, make_config
from run import initial_state_summary, support_failures


def test_each_new_scan_resets_all_nuisances_and_prior_support_is_covered():
    layout = StateLayout((100, 200))
    first, second = build_uniform_prior(layout), build_uniform_prior(layout)
    summary = initial_state_summary(second)
    assert summary == {
        "component_count": 32, "weight_sum": 1.0, "histories_empty": True,
        "consumed_observations": 0, "state_dimension": 8,
        "max_abs_tau_s": 0.0, "max_abs_rx_drift_hz_s": 0.0,
        "max_abs_satellite_epoch_s": 0.0,
    }
    assert support_failures(second, make_config()) == []
    assert not np.shares_memory(first.components[0].mean, second.components[0].mean)


def test_intended_prior_center_boundary_is_distinct_from_orbit_geometry_support():
    mean = np.zeros(8)
    mean[0] = 251.0
    component = GaussianComponent(1.0, mean, np.eye(8) * .0001)
    failures = support_failures(FilterState((component,)), make_config())
    assert failures == ["uniform_region_center_boundary"]
