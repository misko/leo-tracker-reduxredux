import numpy as np
import pytest
from elevation_geometry import elevation_jacobian


def test_batched_geometry_derivative_includes_changing_receiver_normal():
    rng=np.random.default_rng(194)
    line=rng.normal(size=(4,5,3))+[3,0,0];normal=np.broadcast_to([0,0,2.],line.shape).copy()
    dl=rng.normal(size=(4,5,3,3));dn=rng.normal(size=dl.shape)*.05
    values,g=elevation_jacobian(line,normal,dl,dn)
    for d in range(3):
        h=1e-6
        plus=elevation_jacobian(line+h*dl[...,d],normal+h*dn[...,d],dl,dn)[0]
        minus=elevation_jacobian(line-h*dl[...,d],normal-h*dn[...,d],dl,dn)[0]
        np.testing.assert_allclose((plus-minus)/(2*h),g[...,d],rtol=1e-6,atol=1e-6)


def test_vector_scale_does_not_change_elevation_or_its_derivative():
    line=np.array([2.,3.,1.]);normal=np.array([0.,0.,2.]);dl=np.eye(3);dn=np.eye(3)*.1
    a=elevation_jacobian(line,normal,dl,dn)
    b=elevation_jacobian(line*3,normal*7,dl*3,dn*7)
    np.testing.assert_allclose(a[0],b[0]);np.testing.assert_allclose(a[1],b[1])


def test_singular_geometry_is_explicit():
    with pytest.raises(ValueError,match='singular'):elevation_jacobian([0,0,1],[0,0,1],np.eye(3),np.zeros((3,3)))
    with pytest.raises(ValueError,match='nonzero'):elevation_jacobian([0,0,0],[0,0,1],np.eye(3),np.zeros((3,3)))
