from types import SimpleNamespace
import numpy as np
from probe_ds23_rx2_catalogue import affected_family


def test_family_nomination_uses_only_active_RX2_measurement_changes():
    tracks=[dict(receiver=2,observation_ids=['a','b']),dict(receiver=2,observation_ids=['c','d']),
            dict(receiver=1,observation_ids=['e','f'])]
    p=SimpleNamespace(scan=SimpleNamespace(tracks=tracks),members=[0,1,2],
        rows=[dict(candidate_index=j) for j in [10,20,30]],
        slices=[slice(0,2),slice(2,4),slice(4,6)],point_noise=np.array([1,1,2,2,1,1]))
    family,scores=affected_family(p,np.array([True,False,True,True,True,True]),
        dict(a=2,b=1000,c=3,d=3,e=10000,f=10000))
    assert family==20 and scores=={10:4.,20:4.5}
