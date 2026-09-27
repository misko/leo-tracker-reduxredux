"""Fast, checked integration of circular offset and concentration."""
import importlib.util
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

spec=importlib.util.spec_from_file_location('uncertainty',Path(__file__).resolve().parent.parent/'2026_09_27_ds6_uncertainty_audit/run.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)


class PhaseIntegral:
    def __init__(self,n,kappa,weights):
        self.n=n;self.kappa=np.asarray(kappa);self.weights=np.asarray(weights)
        # Dense relative spacing resolves the sharp concentration tail near R=n.
        self.deficit=np.r_[0.,np.geomspace(1e-12,float(n),16385)]
        self.values=self.exact(n-self.deficit)

    def exact(self,resultant):
        r=np.asarray(resultant)
        return logsumexp(u.log_i0(r[...,None]*self.kappa)-self.n*u.log_i0(self.kappa)+np.log(self.weights),axis=-1)

    def from_resultant(self,resultant):
        return np.interp(np.clip(self.n-np.asarray(resultant),0.,float(self.n)),self.deficit,self.values)

    def score(self,y,prediction):
        assert len(y)==self.n
        return self.from_resultant(abs(np.exp(1j*(y-prediction)).sum(axis=-1)))

    def audit(self):
        # Check all interpolation-cell midpoints, including arbitrarily near R=n.
        mids=(self.deficit[1:]+self.deficit[:-1])/2
        return float(np.max(abs(self.from_resultant(self.n-mids)-self.exact(self.n-mids))))


def combine(groups):
    total=sum(g['train'] for g in groups);z=logsumexp(total)
    cfo=sum(g['cfo_train'] for g in groups);joint=sum(g['cfo_joint'] for g in groups)
    return dict(training_log_evidence=float(z-np.log(total.size)),
        held_phase_log_predictive=float(logsumexp(sum(g['phase_all'] for g in groups))-z),
        held_cfo_log_predictive=float(logsumexp(sum(g['cfo_all'] for g in groups))-z),
        cfo_only_held_log_predictive=float(logsumexp(joint)-logsumexp(cfo)),
        cfo_time_posterior=np.exp(cfo-logsumexp(cfo)).tolist(),
        phase_time_posterior=np.exp(logsumexp(total,axis=0)-z).tolist())
