"""Independent full predictive integral audit, without fitting any parameter."""
import numpy as np
from scipy.integrate import dblquad
from scipy.stats import multivariate_normal
from bounded import box_log_probability,correct_score


def test_corrected_predictive_density_matches_direct_position_integration():
    mean=np.array([.4,-.2]);s=np.array([[1.,.2],[.2,.7]])
    raw=np.array([.8,-.3]);noise=np.array([.5,.7]);u=np.array([[.3],[.1]])
    j=np.array([[.8,-.2],[.1,.6]]);c=np.diag(noise**2)+u@u.T
    low=(-1.,-1.2);high=(1.3,.9)
    unbounded=-2*multivariate_normal.logpdf(raw,mean=np.zeros(2),cov=c+j@s@j.T)
    corrected=correct_score(unbounded,raw,noise,u,j,mean,s,low,high)
    def integrand(x1,x0):
        at=np.array([x0,x1])
        return multivariate_normal.pdf(at,mean=mean,cov=s)*multivariate_normal.pdf(raw,mean=j@(at-mean),cov=c)
    integral=dblquad(integrand,low[0],high[0],lambda x:low[1],lambda x:high[1],epsabs=1e-11,epsrel=1e-10)[0]
    density=integral/np.exp(box_log_probability(mean,s,low,high)['log_probability'])
    assert np.isclose(np.exp(-corrected['negative_twice_log_density']/2),density,rtol=1e-10,atol=1e-11)
