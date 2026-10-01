import numpy as np
from mixture_label_delta import correction, move_gain


def test_incremental_moves_equal_complete_reconstruction():
    a=('a',100);b=('a',200);c=('b',100)
    stat=lambda q:dict(d=7,q=q,logdet=5.)
    groups={a:{0:stat(2),1:stat(20)},b:{2:stat(4)},c:{3:stat(8)}}
    for old,new,index in ((a,b,0),(b,None,2),(None,a,4),(b,c,2)):
        modified={k:dict(v) for k,v in groups.items()}
        if old is not None:del modified[old][index]
        if new is not None:modified.setdefault(new,{})[index]=stat(11)
        expected=3.2+sum(correction(list(v.values())) for v in modified.values())-sum(correction(list(v.values())) for v in groups.values())
        np.testing.assert_allclose(move_gain(groups,old,new,index,stat(11),3.2),expected,atol=1e-12)


def test_empty_and_singleton_groups_have_no_correction():
    assert correction([])==correction([dict(d=7,q=2.,logdet=3.)])==0.
