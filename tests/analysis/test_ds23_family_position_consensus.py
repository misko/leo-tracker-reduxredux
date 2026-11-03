import numpy as np
import pytest

from ds23_family_position_consensus import geometric_median,position_candidates


def test_geometric_median_handles_coincident_points_without_freezing_at_nonoptimum():
    triangle=np.array([[0.,0.],[1.,0.],[.5,np.sqrt(3)/2]])
    np.testing.assert_allclose(geometric_median(triangle),triangle.mean(axis=0),atol=1e-8)
    # Coordinate median is exactly one input here but is not the geometric median.
    right=np.array([[0.,0.],[1.,0.],[0.,1.]])
    answer=geometric_median(right)
    np.testing.assert_allclose(answer,[(3-np.sqrt(3))/6]*2,atol=1e-8)


def test_geometric_median_resists_one_bad_family_and_is_rotation_equivariant():
    positions=np.array([[0.,0.],[0.,0.],[0.,0.],[20.,10.]])
    np.testing.assert_array_equal(geometric_median(positions),[0.,0.])
    cloud=np.array([[1.,2.],[2.,4.],[3.,1.],[-1.,1.]])
    rotation=np.array([[.6,-.8],[.8,.6]])
    np.testing.assert_allclose(geometric_median(cloud@rotation.T),geometric_median(cloud)@rotation.T,atol=1e-8)


def test_jackknife_recovers_known_variance_bias_correction():
    samples=np.array([1.,2.,4.,8.,16.])
    full=np.array([samples.var(),0.])
    deleted=np.array([[np.delete(samples,k).var(),0.] for k in range(len(samples))])
    answer=position_candidates(full,deleted)
    assert answer['jackknife'][0]==pytest.approx(samples.var(ddof=1))
    np.testing.assert_allclose(answer['jackknife_covariance_diagnostic'],answer['jackknife_covariance_diagnostic'].T)


def test_family_consensus_preserves_shared_translation_and_requires_all_finite_fits():
    full=np.array([2.,3.]);deleted=np.array([[2.,3.],[2.,4.],[1.,3.],[3.,2.]])
    first=position_candidates(full,deleted);offset=np.array([50.,-30.])
    moved=position_candidates(full+offset,deleted+offset)
    for kind in ('mean','geometric_median','jackknife'):
        np.testing.assert_allclose(moved[kind],first[kind]+offset,atol=1e-8)
    deleted[0,0]=np.nan
    with pytest.raises(ValueError):position_candidates(full,deleted)
