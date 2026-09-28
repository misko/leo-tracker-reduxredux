import numpy as np
import pytest
from small_timing_core import profile,choose_shared,aggregate


def test_eval_isolation_and_shared_selection():
    pred=np.array([[0,1,2,3],[0,2,4,6],[0,3,6,9]],float)
    y=pred[1]+50; mask=np.array([True,True,False,False])
    a=profile(y,pred,mask);y[~mask]+=1000;b=profile(y,pred,mask)
    assert np.array_equal(a['train_sse'],b['train_sse'])
    assert choose_shared([dict(satellite_id='a',**a)],[-1,0,1])=={'a':1}
    rows=[{'satellite_id':'a','train_sse':np.array([0,3,9])},
          {'satellite_id':'a','train_sse':np.array([12,3,0])}]
    assert choose_shared(rows,[-1,0,1])=={'a':1}


def test_aggregation_and_tie():
    out=aggregate([{'observations':1,'mse':4},{'observations':3,'mse':16}],'mse')
    assert out['equal_track_rms_hz']==pytest.approx(np.sqrt(10))
    assert out['size_weighted_rms_hz']==pytest.approx(np.sqrt(13))
    assert choose_shared([{'satellite_id':'a','train_sse':np.zeros(3)}],[-1,0,1])=={'a':1}
