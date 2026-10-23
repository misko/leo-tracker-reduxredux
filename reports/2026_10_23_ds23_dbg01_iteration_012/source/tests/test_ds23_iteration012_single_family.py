import copy
import numpy as np

from probe_ds23_iteration012_single_family import offer


def rows():
    best=dict(candidate_index=2,aliases=[0],qualified=True,all_fixed_radio_checks_pass=True,wrapped_null_gain=30.,score=10.)
    return {a:[copy.deepcopy(best),dict(score=30.)] for a in ['c0','fitted_c']}


def test_single_source_requires_both_fixed_radio_checks_and_null_and_identity_margins():
    pair=rows();assert offer(pair,20.)
    pair['fitted_c'][0]['all_fixed_radio_checks_pass']=False;assert not offer(pair,20.)
    pair=rows();pair['fitted_c'][0]['wrapped_null_gain']=19.;assert not offer(pair,20.)
    pair=rows();pair['c0'][1]['score']=15.;assert not offer(pair,20.)


def test_identity_or_alias_disagreement_cannot_create_a_shared_family_offer():
    pair=rows();pair['fitted_c'][0]['candidate_index']=3;assert not offer(pair,20.)
    pair=rows();pair['fitted_c'][0]['aliases']=[1];assert not offer(pair,20.)
