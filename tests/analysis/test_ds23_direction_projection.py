import numpy as np
import pytest

from ds23_direction_projection import project_direction


def test_existing_mode_has_zero_independent_information_with_different_units():
    t=np.linspace(-1,1,60)
    existing=np.column_stack((np.ones(60)*1e12,t*1e-12))
    result=project_direction(3+4*t,existing,np.linspace(1,2,60))
    assert result['independent_noise_norm']<1e-12
    assert result['existing_rank']==2


def test_additional_curvature_survives_affine_projection_and_whitening():
    t=np.linspace(-1,1,61)
    existing=np.column_stack((np.ones(len(t)),t))
    y=t*t+2*t
    result=project_direction(y,existing,np.ones(len(t))*2)
    expected=t*t-np.mean(t*t)
    np.testing.assert_allclose(result['independent_hz'],expected,atol=1e-14)
    assert result['independent_noise_norm']==pytest.approx(np.linalg.norm(expected)/2)
    np.testing.assert_allclose(existing.T@result['independent_hz'],0,atol=1e-13)


def test_duplicate_and_zero_columns_do_not_change_residual_or_rank():
    t=np.linspace(-1,1,31)
    a=np.column_stack((t,np.ones(len(t))))
    b=np.column_stack((a,t*1e6,np.zeros(len(t))))
    left=project_direction(t*t,a,np.ones(len(t)))
    right=project_direction(t*t,b,np.ones(len(t)))
    assert left['existing_rank']==right['existing_rank']==2
    np.testing.assert_allclose(left['independent_hz'],right['independent_hz'],atol=1e-14)


def test_bad_noise_and_mismatched_dimensions_are_rejected():
    with pytest.raises(ValueError):
        project_direction([1,2],np.eye(2),[1,0])
    with pytest.raises(ValueError):
        project_direction([1,2],np.eye(3),[1,1])
