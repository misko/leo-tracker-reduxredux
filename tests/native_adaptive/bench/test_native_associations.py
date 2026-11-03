import copy
import pytest
from compare_native_associations import compare


def test_choice_and_numeric_comparisons_remain_separate():
    a={'points':[{'score_hz':3.,'matched_tracks':1,'tracks':[{
        'candidate_id':123,'tau_s':-1.,'held_hz':3.,'fit_hz':2.,'offset_hz':1.}]}]}
    b=copy.deepcopy(a);b['points'][0]['tracks'][0]['held_hz']+=1e-10
    result=compare(a,b,1e-9)
    assert not result['exact_json'] and result['within_position_tolerance']
    b['points'][0]['tracks'][0]['candidate_id']=124
    assert not compare(a,b,1e-9)['within_position_tolerance']
    with pytest.raises(ValueError):compare(a,{'points':[]},1e-9)
