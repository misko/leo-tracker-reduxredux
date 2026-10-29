from types import SimpleNamespace
import numpy as np
import pytest
from provisional_family_recovery import confirmation,without_family


def test_two_distinct_paired_witnesses_and_positive_aggregate_required():
    good=lambda n:dict(norad=n,valid=True,gains=dict(c0=2.,fitted_c=1.))
    assert not confirmation([good(1)])['accepted']
    assert confirmation([good(1),good(2)])['accepted']
    assert not confirmation([good(1),good(2),dict(norad=3,valid=True,gains=dict(c0=-5.,fitted_c=-3.))])['accepted']
    assert not confirmation([good(1),dict(norad=2,valid=False,gains=dict(c0=10.,fitted_c=10.))])['accepted']
    assert not confirmation([good(1),dict(norad=2,valid=True,gains=dict(c0=10.,fitted_c=-.1))])['accepted']
    with pytest.raises(ValueError):confirmation([good(1),good(1)])
    with pytest.raises(ValueError):confirmation([good(1),dict(norad=2,valid=True,gains=dict(c0=np.nan,fitted_c=1.))])


def test_withheld_family_removed_everywhere_and_only_its_prior_reset():
    p=SimpleNamespace(rows=[dict(candidate_norad=n,candidate_index=j) for n,j in [(100,0),(200,1),(100,0)]],
                      slices=[slice(0,2),slice(2,4),slice(4,6)],labels=[0,1])
    d=dict(keep=np.ones(6,bool),means=np.array([9.,8.]),problems={'c0':(p,None)},
           entries=[dict(norad=100,receiver=2),dict(norad=200,receiver=1)])
    fold=without_family(d,100,np.array([1.,2.]))
    np.testing.assert_equal(fold['keep'],[False,False,True,True,False,False])
    np.testing.assert_equal(fold['means'],[1.,8.])
    assert fold['entries']==[dict(norad=200,receiver=1)]
    assert d['keep'].all() and d['means'][0]==9.
