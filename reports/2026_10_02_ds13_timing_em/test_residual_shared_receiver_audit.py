import numpy as np
from residual_shared_receiver_audit import transferred_component


def test_shared_drift_transfers_without_satellite_intercept():
    times=np.linspace(0,300,120);channels=np.tile([1,2],60);tracks=np.tile([10,20,30],40)
    drift=2*(times-150)+.004*(times-150)**2
    channel=(channels==2)*17
    values=drift+channel+np.where(tracks==10,100,np.where(tracks==20,-300,50))
    predicted=transferred_component(times,channels,tracks,values,times,channels,2)
    np.testing.assert_allclose(predicted,drift+channel,atol=1e-8)
