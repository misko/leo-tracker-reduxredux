"""Full retained-candidate independent-error CFO marginalization."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import ds7_fast_baseline_adapter as fast
spec=importlib.util.spec_from_file_location('cfo_quadrature',HERE.parent/'offset_quadrature/model.py')
quad=importlib.util.module_from_spec(spec);spec.loader.exec_module(quad)


class MarginalModel:
    def __init__(self,document,config,order=32,geometry=None):
        self.document=document;self.order=order
        self.model=geometry if geometry is not None else fast.Stationary(document,config)

    def evaluate(self,x,gradient=True):
        x=np.asarray(x,dtype=float);total=0.;derivative=np.zeros(3)
        for track in self.document['tracks']:
            mask=track['mask'];prediction,visible=self.model.prediction(track,x)
            residual=(track['y'][None,:]-prediction)[:,mask]
            offsets,audits=fast.fit_stationary_offsets(residual)
            assert all(a['converged'] for a in audits)
            jac=np.zeros((*residual.shape,3))
            if gradient:
                for axis,step in enumerate((1e-4,1e-4,1e-5)):
                    d=np.eye(3)[axis]*step
                    jac[:,:,axis]=(self.model.prediction(track,x+d)[0][:,mask]-self.model.prediction(track,x-d)[0][:,mask])/(2*step)
            results=[quad.integrate(r,j,float(b),self.order) for r,j,b in zip(residual,jac,offsets)]
            values=np.array([r['value'] for r in results]);scores=np.where(visible,values,-np.inf)
            normal=logsumexp(scores);assert np.isfinite(normal)
            total+=float(normal-np.log(track['catalogue_size']))
            if gradient:derivative+=np.exp(scores-normal)@np.array([r['gradient'] for r in results])
        return dict(score=total,gradient=derivative)
