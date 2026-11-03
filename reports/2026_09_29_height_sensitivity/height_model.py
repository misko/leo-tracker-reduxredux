import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import ds7_baseline_adapter as baseline


class HeightStationary(baseline.Stationary):
    def __init__(self,document,config):
        super().__init__(document,config)
        self.height_km=float(config['receiver_height_m'])/1000
        if not np.isfinite(self.height_km):
            raise ValueError('Require finite height')

    def prediction(self,track,x):
        rec,up=baseline.site(*self.coordinates(x))
        rec=rec+self.height_km*up
        tau=x[2]
        hi=min(max(int(np.searchsorted(self.taus,tau,side='right')),1),len(self.taus)-1)
        lo=hi-1
        weight=(tau-self.taus[lo])/(self.taus[hi]-self.taus[lo])
        pos=track['candidate_position_km'][:,lo]*(1-weight)+track['candidate_position_km'][:,hi]*weight
        vel=track['candidate_velocity_km_s'][:,lo]*(1-weight)+track['candidate_velocity_km_s'][:,hi]*weight
        unit=pos-rec
        unit/=np.linalg.norm(unit,axis=-1)[...,None]
        prediction=-baseline.REFERENCE_RF_HZ/baseline.LIGHT_KM_S*np.sum(unit*vel,axis=-1)
        return prediction,np.any((unit@up)[:,track['mask']]>=0,axis=1)
