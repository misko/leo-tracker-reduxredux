from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_synthetic_nuisance_components import select_coefficients,bounded_phase_draw


def test_component_draws_add_to_same_all_draw_without_phase_or_constant_scale_leak():
    widths=(8,6,3,9,4);z=np.random.default_rng(219).normal(size=sum(widths))
    total=sum(select_coefficients(z,widths,g) for g in ('radio','smooth','orbit','fragment'))
    np.testing.assert_array_equal(total,select_coefficients(z,widths,'all'))
    np.testing.assert_array_equal(total[14:17],0.)
    np.testing.assert_allclose(total[-4:],.3*z[-4:])
    np.testing.assert_array_equal(select_coefficients(z,widths,'phase'),0.)


@pytest.mark.parametrize('nu',[None,4.])
def test_phase_conditioning_uses_continuous_bounded_distribution(nu):
    means=np.array([0.,15.,-15.]);sigmas=np.array([1.,4.,4.])
    values=bounded_phase_draw(means,sigmas,nu,np.array([.5,.5,.5]))
    assert abs(values[0])<1e-10
    assert 0<values[1]<15 and -15<values[2]<0
    np.testing.assert_allclose(values[1],-values[2],atol=1e-12)


def test_invalid_draws_do_not_get_clipped_into_valid_simulations():
    with pytest.raises(ValueError):bounded_phase_draw([0.],[0.],None,[.5])
    with pytest.raises(ValueError):bounded_phase_draw([0.],[1.],None,[0.])
    with pytest.raises(ValueError):select_coefficients(np.ones(5),(1,1,1,1,1),'unknown')
