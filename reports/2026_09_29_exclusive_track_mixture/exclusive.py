import importlib.util
import math
from pathlib import Path
import numpy as np
from partition import Partition

path=Path(__file__).resolve().parents[1]/'2026_09_29_frequency_contrast/contrast_position.py'
spec=importlib.util.spec_from_file_location('exclusive_contrast',path)
contrast=importlib.util.module_from_spec(spec);spec.loader.exec_module(contrast)


class Exclusive:
    def __init__(self,original,groups):
        self.original=original;self.documents=original.documents;self.models=original.models
        self.graphs=[Partition(g) for g in groups]

    def evaluate(self,x,gradient=True,held=False):
        x=np.asarray(x);derivative=np.zeros_like(x);total=0.;joint_total=0.;active=0.
        for di,(doc,engine,graph) in enumerate(zip(self.documents,self.models,self.graphs,strict=True)):
            local=np.array([*x[:2],x[di+2]])
            signal=[];background=[];full_signal=[];full_background=[];gradients=[]
            for ti,track in enumerate(doc['tracks']):
                pred,visible=engine.prediction(track,local)
                if not visible.any():
                    raise ValueError('No visible candidate')
                residual=track['y'][None,:]-pred;mask=track['mask']
                train,influence=contrast.contrast_density(residual[:,mask])
                train=np.where(visible,train,-np.inf);normal=np.logaddexp.reduce(train)
                signal.append(float(normal-math.log(int(visible.sum()))))
                background.append(self.original.background[di,ti][0])
                if gradient:
                    weights=np.exp(train-normal);g=[]
                    for axis,step in enumerate((1e-4,1e-4,1e-5)):
                        p,m=local.copy(),local.copy();p[axis]+=step;m[axis]-=step
                        if axis==2:p[axis]=min(5,p[axis]);m[axis]=max(-5,m[axis])
                        pp,vp=engine.prediction(track,p);pm,vm=engine.prediction(track,m)
                        assert np.array_equal(visible,vp) and np.array_equal(visible,vm)
                        dp=(pp[:,mask]-pm[:,mask])/(p[axis]-m[axis])
                        g.append(float(weights@np.sum(influence*dp,axis=1)))
                    gradients.append(g)
                if held:
                    full,_=contrast.contrast_density(residual)
                    full_signal.append(float(np.logaddexp.reduce(np.where(visible,full,-np.inf))-math.log(int(visible.sum()))))
                    full_background.append(self.original.background[di,ti][1])
            score,occupancy=graph.density(signal,background);total+=score;active+=float(occupancy.sum())
            if gradient:
                g=occupancy@np.array(gradients);derivative[:2]+=g[:2];derivative[di+2]=g[2]
            if held:
                joint_total+=graph.density(full_signal,full_background)[0]
        return dict(score=total,gradient=derivative,held_log_score=joint_total-total if held else None,expected_active_tracks=active)
