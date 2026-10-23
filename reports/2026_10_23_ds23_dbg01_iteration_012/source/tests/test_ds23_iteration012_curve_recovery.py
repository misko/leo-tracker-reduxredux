import numpy as np

import probe_ds23_iteration012_curve_recovery as study


def test_source_intersection_preserves_native_times_values_alias_and_order():
    track=dict(key='source',observation_ids=['a','b','c'])
    fragment=dict(key='path',candidate_index=4,norad=99,times=[1.,2.,3.,4.],values=[100.,200.,300.,400.],observation_ids=['extra','a','b','c'])
    result=study.source_intersections([track],[fragment])[0]
    assert result['observation_ids']==['a','b','c']
    np.testing.assert_array_equal(result['times'],[2.,3.,4.]);np.testing.assert_array_equal(result['values'],[200.,300.,400.])
    assert result['candidate_index']==4 and result['norad']==99
    assert fragment['observation_ids']==['extra','a','b','c']


def test_disjoint_native_paths_do_not_create_a_source_core():
    assert study.source_intersections([dict(key='s',observation_ids=['a'])],[dict(key='p',times=[1.],values=[2.],observation_ids=['b'])])==[]


def test_core_retains_prior_endpoint_and_curvature_guards():
    module=study.configure('core')
    assert module.offers is study.source_offers and module.raw_curvature is study.supported_curvature
    assert module.parent.OUT==study.binding.runner.RAW/'graph_seeded_paths'
    assert module.OUT==study.OUT
