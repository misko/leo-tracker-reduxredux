import numpy as np

from probe_algo03_fai_residuals import accumulate


def test_boundary_statistic_uses_actual_pair_gaps_and_utc_phase():
    times=np.arange(0,150,.5)
    residual=np.floor((times+3-12)/15)*400
    count,total,_,use,_=accumulate(times,residual,np.full(len(times),100.),3.,phases=[12.,5.])
    assert count[0].sum()==use.sum()
    assert total[0,1].sum()>0
    assert total[0,0].sum()==0
    assert total[1,1].sum()==0
    assert total[1,0].sum()>0


def test_long_gap_does_not_manufacture_a_boundary_jump():
    times=np.array([0.,.5,1.,16.,16.5])
    count,total,_,use,_=accumulate(times,[0,0,0,10000,10000],np.full(5,100.),0.)
    assert use.sum()==3
    assert count[0].sum()==3
    assert total.sum()==0
