"""Experimental residual plus shared-threshold branch scorer; no baseline changes."""
import numpy as np
from acquire import enu_state_ecef_km,WGS84_A_KM,WGS84_F,LIGHT_KM_S
from visibility_geometry_adapter import visibility_geometry
from visibility_state_gradient import weight_components,selected_weight_gradient


class SharedVisibilityPort:
    def __init__(self,original,width_deg=.1):
        self.original=original;self.likelihood=original.likelihood;self.width_deg=width_deg
        self.candidate_count=original.candidate_count;self.observation=original.observation
        self.observation_ids=original.observation_ids;self._key=None
        self.scales=np.array([WGS84_A_KM**2,WGS84_A_KM**2,(WGS84_A_KM*(1-WGS84_F))**2])

    def receiver(self,e,n):
        l=self.likelihood;c=l.config
        return enu_state_ecef_km(e,n,l.height_surface(e,n),c.prior_center_lat_deg,c.prior_center_lon_deg)

    def _evaluate(self,state):
        state=np.asarray(state,dtype=float)
        if state.shape!=(5+self.candidate_count,) or not np.all(np.isfinite(state)):raise ValueError('invalid scan state')
        key=state.tobytes()
        if key==self._key:return
        l=self.likelihood;c=l.config
        margins,jac=visibility_geometry(l,state,self.receiver,self.scales)
        components=weight_components(margins,jac,self.width_deg,c.signal_prior)
        position,velocity=l._orbit_states_per_satellite(state[2]+state[5:])
        line=position-self.receiver(state[0],state[1]);unit=line/np.linalg.norm(line,axis=-1,keepdims=True)
        doppler=c.doppler_sign*c.reference_frequency_hz/LIGHT_KM_S*np.sum(velocity*unit,axis=-1)
        drift=state[3+l.receiver_indices]*l.drift_scale*l.centered_times
        means=(doppler+drift[None,:])@l.contrasts.T
        residual=l.observation[None,:]-means
        quadratic=np.einsum('...i,ij,...j->...',residual,l.precision,residual)
        density=l._residual_log_density(quadratic,l.covariance,l.log_normalizer)
        self._scores=np.r_[density,l.background_log_likelihood]+components[0]
        self._components=components;self._means=means;self._key=key

    def score_all(self,state):
        self._evaluate(state);return self._scores.copy()

    def score_selected(self,state,index):
        self._evaluate(state)
        if not 0<=index<=self.candidate_count:raise ValueError('invalid branch')
        return float(self._scores[index])

    def score_gradient(self,state,index):
        self._evaluate(state);gradient=selected_weight_gradient(self._components,index)
        if index<self.candidate_count:
            prediction=self.original.predict_selected(state,index)
            np.testing.assert_allclose(prediction.mean,self._means[index],rtol=1e-9,atol=1e-7)
            residual=self.observation-prediction.mean;solved=np.linalg.solve(prediction.covariance,residual)
            weight=(4+len(residual))/(4+float(residual@solved))
            gradient+=weight*prediction.jacobian.T@solved
        return gradient
