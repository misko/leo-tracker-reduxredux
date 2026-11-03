import itertools
import math

import numpy as np
import pytest

from ds23_symmetric_family_code import family_code,log_stirling_second,observed_labels,symmetric_gain,replace_whole_family


def test_small_catalogue_prior_is_normalized_over_every_assignment():
    for n,m in ((2,3),(3,4),(4,3)):
        mass=sum(math.exp(-.5*family_code(n,labels))
                 for labels in itertools.product(range(n),repeat=m))
        assert mass==pytest.approx(1.,abs=1e-12)


def test_catalogue_label_permutation_and_incumbent_have_equal_cost():
    first=[0,0,1,1,2,2]
    replacement=[19,19,9,9,7,7]
    assert family_code(30,first)==family_code(30,replacement)
    a,b=family_code(30,first),family_code(30,replacement)
    assert symmetric_gain(1000.,a,995.,b)==pytest.approx(5.)
    assert symmetric_gain(995.,b,1000.,a)==pytest.approx(-5.)


def test_partition_counts_and_active_population_only():
    assert math.exp(log_stirling_second(5,3))==pytest.approx(25.)
    assert log_stirling_second(0,0)==0.
    node={'seed':{'rows':[{'candidate_index':0},{'candidate_index':9}]}}
    assert observed_labels(node,[{'candidate_index':1}],np.array([True,True,False]),
                           [slice(0,2),slice(2,3)])==[0,1]


def test_invalid_codes_are_rejected():
    for labels in ([],[-1],[4],[.5]):
        with pytest.raises(ValueError):family_code(4,labels)
    with pytest.raises(ValueError):log_stirling_second(1,2)
    with pytest.raises(ValueError):symmetric_gain(1.,2.,np.nan,3.)


def test_whole_family_replacement_preserves_points_and_updates_both_receivers():
    node={'seed':{'rows':[{'candidate_index':1,'candidate_norad':101,'component':'A'},
                         {'candidate_index':1,'candidate_norad':101,'component':'B'},
                         {'candidate_index':2,'candidate_norad':102,'component':'C'}]},
          'aliases':[0,1,0]}
    entries=[{'candidate_index':1,'norad':101,'alias':0,'observation_ids':['one','two']},
             {'candidate_index':2,'norad':102,'alias':0,'observation_ids':['three']}]
    aliases={('curve',0):2,('curve',1):3,('linear',0):4}
    changed,linear=replace_whole_family(node,entries,1,9,109,aliases)
    assert [r['candidate_index'] for r in changed['seed']['rows']]==[9,9,2]
    assert changed['aliases']==[2,3,0]
    assert [r['observation_ids'] for r in linear]==[r['observation_ids'] for r in entries]
    assert linear[0]['candidate_index']==9 and linear[0]['alias']==4
    assert node['seed']['rows'][0]['candidate_index']==1
    with pytest.raises(ValueError):replace_whole_family(node,entries,1,9,109,{('curve',0):2})
