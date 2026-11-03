"""Same acquisition score with matrix products replacing tensor contractions."""
import numpy as np
from window_inputs import prepare_scan  # Establish pinned research imports.
from acquisition_dot import FixedHeightTrackLikelihood, WGS84_A_KM, WGS84_F, enu_state_ecef_km, LIGHT_KM_S
from leo.analysis.localization_geometry_blas import stationary_range_rate_grid_blas

class BlasTrackLikelihood(FixedHeightTrackLikelihood):
    def __init__(self, *args, geometry_cache=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.geometry_cache = {} if geometry_cache is None else geometry_cache

    def __call__(self, points_en_km, nuisance_hypotheses):
        points = np.asarray(points_en_km, dtype=float)
        if np.asarray(nuisance_hypotheses).shape != (1, 0):
            raise ValueError('proposal fixes all nuisance coordinates')
        key = (points.shape, points.tobytes())
        if key not in self.geometry_cache:
            receivers = np.stack([
                enu_state_ecef_km(east, north, self.height_surface(float(east), float(north)),
                                 self.config.prior_center_lat_deg,
                                 self.config.prior_center_lon_deg)
                for east, north in points
            ])
            semiminor = WGS84_A_KM*(1-WGS84_F)
            up = receivers/np.array([WGS84_A_KM**2, WGS84_A_KM**2, semiminor**2])
            up /= np.linalg.norm(up, axis=1, keepdims=True)
            self.geometry_cache[key] = receivers, up
        receivers, up = self.geometry_cache[key]
        positions, velocities = self._orbit_states(np.zeros(1))
        rate, sine_elevation = stationary_range_rate_grid_blas(
            positions[0], velocities[0], receivers, up,
        )
        doppler = self.config.doppler_sign*self.config.reference_frequency_hz/LIGHT_KM_S*rate
        means = doppler @ self.contrasts.T
        residual = self.observation[None, None, :]-means
        quadratic = np.sum((residual @ self.precision)*residual, axis=-1)
        logs = self._residual_log_density(quadratic, self.covariance, self.log_normalizer)
        elevation = np.degrees(np.arcsin(sine_elevation))
        visible = np.all(elevation >= -self.config.horizon_margin_deg, axis=2)
        count = len(self.bank.norad_ids)
        logs = np.where(visible, logs+np.log(self.config.signal_prior/count), -np.inf)
        background_prior = (self.config.background_prior
                            + self.config.signal_prior*(count-visible.sum(axis=1))/count)
        background = np.log(background_prior)+self.background_log_likelihood
        return np.concatenate((logs, background[:, None]), axis=1)[:, None, :]
