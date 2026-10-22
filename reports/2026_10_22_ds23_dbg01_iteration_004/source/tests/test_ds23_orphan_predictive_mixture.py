import numpy as np
import pytest

from ds23_orphan_predictive_mixture import integrated_clutter,wrapped_pdf,orphan_rows,PERIOD


def test_wrapped_density_has_unit_mass_and_is_periodic_at_alias_boundary():
    grid=np.linspace(-PERIOD/2,PERIOD/2,20001)
    pdf=wrapped_pdf(grid,300.)
    assert np.trapezoid(pdf,grid)==pytest.approx(1.,abs=1e-10)
    np.testing.assert_allclose(wrapped_pdf(np.array([-20.,0.,20.])+4*PERIOD,300.),wrapped_pdf(np.array([-20.,0.,20.]),300.),atol=1e-13)


def test_uniform_signal_matches_clutter_and_zero_signal_integrates_fraction_prior():
    a=integrated_clutter(np.ones((16,20)),details=True)
    assert a['relative_negative_twice_log_likelihood']==pytest.approx(0.,abs=1e-12)
    assert a['posterior_signal_fraction']==pytest.approx(.5)
    np.testing.assert_allclose(a['point_signal_probabilities'],.5)
    b=integrated_clutter(np.zeros((16,20)))
    assert b['relative_negative_twice_log_likelihood']==pytest.approx(2*np.log(21),abs=1e-10)


def test_shared_nuisance_integration_preserves_cross_point_dependence():
    shared=np.array([[10.,10.],[0.,0.]])
    independent=np.array([[10.,0.],[0.,10.]])
    assert integrated_clutter(shared)['relative_negative_twice_log_likelihood'] < integrated_clutter(independent)['relative_negative_twice_log_likelihood']


def test_orphan_partition_excludes_all_graph_IDs_even_unassociated_graph_tracks():
    from types import SimpleNamespace
    observations=[dict(observation_id=i,receiver=1,channel=1,actual_rf_hz=1.,time_s=k) for k,i in enumerate(['a','b','c'])]
    data=dict(scan=SimpleNamespace(tracks=[dict(observation_ids=['a','b'])]),observations=observations)
    assert [r['observation_id'] for r in orphan_rows(data)]==['c']
