"""Fix independent ellipsoidal antenna height while fitting east/north/time."""
import importlib.util
from pathlib import Path
import numpy as np

SOURCE=Path(__file__).resolve().parent.parent/'free_height/model.py'
spec=importlib.util.spec_from_file_location('ds11_fixed_height_geometry',SOURCE)
physical=importlib.util.module_from_spec(spec);spec.loader.exec_module(physical)


class Model:
    def __init__(self,document,config,height_m):
        if not np.isscalar(height_m) or not np.isfinite(height_m):
            raise ValueError('finite ellipsoidal height in metres required')
        self.height_km=float(height_m)/1000
        self.base=physical.Model(document,config)

    def state(self,x):
        x=np.asarray(x,float)
        if x.shape!=(3,) or not np.isfinite(x).all():
            raise ValueError('only finite east, north and timing coordinates may vary')
        return np.r_[x,self.height_km]

    def evaluate(self,x,gradient=True):
        result=self.base.evaluate(self.state(x),gradient)
        return dict(score=result['score'],held=result['held'],gradient=result['gradient'][:3])

    def coordinates(self,x):
        return self.base.model.coordinates(self.state(x))

    def prediction(self,track,x):
        return self.base.model.prediction(track,self.state(x))
