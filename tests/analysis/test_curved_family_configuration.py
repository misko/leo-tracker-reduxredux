import copy
import numpy as np
import pytest
from include_curved_family_annotations import configuration


def test_joint_reassignment_preserves_other_labels_masks_and_input():
    node=dict(seed=dict(rows=[dict(component=c,candidate_index=j,candidate_norad=100+j) for c,j in [('a',1),('b',2),('c',3)]]),aliases=[0,1,0])
    before=copy.deepcopy(node);keep=np.array([True,False,False,False,True,False]);slices=[slice(0,2),slice(2,4),slice(4,6)]
    targets=[dict(row=i,component=c,candidate_index=4,norad=104,alias=-1) for i,c in [(0,'a'),(1,'b')]]
    changed,mask=configuration(node,keep,slices,targets)
    assert [r['candidate_index'] for r in changed['seed']['rows']]==[4,4,3]
    assert changed['aliases']==[-1,-1,0]
    np.testing.assert_array_equal(mask,[True,True,True,True,True,False])
    np.testing.assert_array_equal(keep,[True,False,False,False,True,False]);assert node==before
    with pytest.raises(ValueError,match='repeated'):configuration(node,keep,slices,targets*2)
    with pytest.raises(ValueError,match='mismatch'):configuration(node,keep,slices,[dict(targets[0],component='wrong')])
