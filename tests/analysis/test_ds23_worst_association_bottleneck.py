import pytest
import numpy as np

from probe_ds23_worst_association_bottleneck import select_worst
from plot_ds23_worst_association_bottleneck import raw_track_values


def test_debug_ranking_uses_complete_declared_benchmark_and_keeps_bad_cases():
    rows = [dict(case=f'DS23-{k:04}', policy='equal_assignment_priors', arm=arm,
                 policy_error_km=str(error)) for k, error in [(3, 10.), (2, 2.), (1, 10.)]
            for arm in ['c0', 'fitted_c']]
    assert [r['case'] for r in select_worst(rows)] == ['DS23-0001', 'DS23-0003']
    with pytest.raises(ValueError, match='one benchmark'):
        select_worst(rows+[rows[-1]])


def test_figure_joins_physical_IDs_instead_of_plotting_canonical_alias_values():
    period = 1/4.4e-6
    track = dict(observation_ids=['b', 'a'], times=[1., 2.], values=[2., 3.])
    raw = dict(a=dict(time_s=2., measured_cfo_hz=3.+4*period),
               b=dict(time_s=1., measured_cfo_hz=2.+4*period))
    times, values = raw_track_values(track, [0, 1], raw)
    np.testing.assert_array_equal(times, [1., 2.])
    np.testing.assert_allclose(values, np.asarray(track['values'])+4*period)
    assert values.min() > 900000
    with pytest.raises(ValueError, match='physical observation time'):
        raw_track_values(track, [0], dict(raw, b=dict(time_s=3., measured_cfo_hz=1.)))
