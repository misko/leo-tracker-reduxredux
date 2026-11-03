"""Independent labels: opposite cardinal half-sky is not behind boresight."""
import numpy as np

def labels(unit_enu,receiver,epsilon=1e-12):
    unit=np.asarray(unit_enu,float)
    if unit.shape[-1]!=3 or receiver not in (0,1):raise ValueError('ENU direction and RX0/RX1 required')
    if not np.allclose(np.linalg.norm(unit,axis=-1),1,atol=1e-7):raise ValueError('unit directions required')
    az=np.radians(270. if receiver==0 else 90.);el=np.radians(70.)
    bore=np.array([np.cos(el)*np.sin(az),np.cos(el)*np.cos(az),np.sin(el)])
    dot=unit@bore
    return dict(opposite_east_west=unit[...,0]>epsilon if receiver==0 else unit[...,0]<-epsilon,behind_nominal_boresight=dot<-epsilon,nominal_boresight_angle_deg=np.degrees(np.arccos(np.clip(dot,-1,1))),below_horizon=unit[...,2]<-epsilon)
