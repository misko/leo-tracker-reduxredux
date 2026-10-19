"""Band covariance changes cross-band dependence without changing marginal noise."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_band_covariance import split_basis,split_seed,augment
from types import SimpleNamespace


@pytest.mark.parametrize('rho',[0.,.5,1.])
def test_marginal_variance_preserved_and_cross_band_covariance_scaled(rho):
    b=np.array([[1.,2.],[3.,4.]])
    low,high=split_basis(b,0,rho),split_basis(b,1,rho)
    assert low@low.T==pytest.approx(b@b.T)
    assert high@high.T==pytest.approx(b@b.T)
    assert low@high.T==pytest.approx(rho*(b@b.T))


@pytest.mark.parametrize('rho',[0.,.5,1.])
def test_expanded_seed_reproduces_original_correction_on_both_bands(rho):
    b=np.array([[1.,2.],[3.,4.]]);s=np.array([[.1,.2],[.3,.4]])
    expanded=split_seed(s,rho)
    for rx in (0,1):
        for band in (0,1):assert split_basis(b,band,rho)@expanded[rx]==pytest.approx(b@s[rx])


def test_original_seed_and_basis_are_not_mutated():
    b=np.ones((3,2));scan=SimpleNamespace(rx_basis=[b],tracks=[dict(channel=1)])
    node=dict(seed=dict(state=dict(smooth=[[1,2],[3,4]])),aliases=[1])
    new,new_node=augment(scan,node,.5)
    assert new.rx_basis[0].shape==(3,6) and scan.rx_basis[0].shape==(3,2)
    assert node['seed']['state']['smooth']==[[1,2],[3,4]]
    assert new_node['aliases']==[1]


def test_invalid_correlation_is_rejected():
    with pytest.raises(ValueError):split_basis(np.ones((2,1)),0,1.1)
