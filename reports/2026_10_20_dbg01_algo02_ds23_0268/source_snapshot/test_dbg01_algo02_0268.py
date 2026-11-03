from types import SimpleNamespace

import numpy as np
import pytest

from debug_algo02_ds23_0268 import decomposition
from report_dbg01_algo02_ds23_0268 import memberships


def test_decomposition_uses_latent_prior_and_includes_predictive_normalization():
    a=np.arange(1,15,dtype=float)/10
    data=dict(coefficient=a+5,latent_coefficient=a,coefficient_prior_precision=np.ones(14),
              quadratic=30.,logvolume=3.,noise_gamma_cost=2.,prior_gamma_cost=1.,normalization_constant=40.,
              negative_twice_elbo=76.)
    combined=dict(data,negative_twice_elbo=81.)
    p=SimpleNamespace(hardware=np.zeros((2,8)),smooth=np.zeros((2,2)),labels=[0],members=[0],
                      calculate=lambda x:combined,curved_calculate=lambda x:data)
    result=decomposition(p,np.zeros(2))
    assert result['reconstruction_error']==pytest.approx(0.)
    assert result['terms']['predictive_linear']==5.
    assert result['terms']['weighted_data']==pytest.approx(30-float(a@a))


def test_partial_track_association_does_not_hide_rejected_prefix():
    track=dict(key='track',observation_ids=['prefix','suffix1','suffix2'])
    rows=[dict(component='track',compatible=True,norad=1,observation_ids=['suffix1','suffix2'])]
    audit=dict(arms={arm:dict(associations=dict(tracks=rows)) for arm in ('c0','fitted_c')})
    result=memberships(audit,[track])
    assert result['c0']['observation_ids']==['suffix1','suffix2']
    assert 'prefix' not in result['c0']['observation_ids']
    rows.append(dict(component='track',compatible=True,norad=2,observation_ids=['suffix1']))
    with pytest.raises(ValueError,match='duplicate association ownership'):
        memberships(audit,[track])
