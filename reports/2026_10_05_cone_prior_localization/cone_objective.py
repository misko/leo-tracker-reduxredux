"""Position-dependent cone priors with full likelihood/geometry gradients."""
import numpy as np

from cone_geometry import cone_marginals, tilt
from smooth_visibility_model import observer_pose, gate_terms, finite_set_terms
from position_structure_study import Objective as BaseObjective, row_weights
from joint_inputs import FRAME_LATITUDE_DEG, FRAME_LONGITUDE_DEG

FRAME = (FRAME_LATITUDE_DEG, FRAME_LONGITUDE_DEG)


def pose(point):
    xyz, up = observer_pose(point, FRAME)
    east = np.array([-up[1], up[0], 0.]); east /= np.linalg.norm(east)
    north = np.cross(up, east)
    return xyz, np.stack([east, north, up])


def directions(data, parameters, derivatives=True):
    """Same archived linear ephemeris interpolation as frequency prediction."""
    p = np.asarray(parameters); n = len(data.times); k = len(data.numbers)
    query = data.times[:, None]+p[6:][None, :]
    nodes = data.nodes; step = nodes[1]-nodes[0]
    ix = np.floor((query-nodes[0])/step).astype(int)
    if np.any(ix<0) or np.any(ix>=len(nodes)-1):
        raise ValueError('Outside ephemeris support')
    frac = ((query-nodes[0])/step-ix)[..., None]
    sat = np.arange(k)[None, :]
    left, right = data.position[sat, ix], data.position[sat, ix+1]
    positions = left*(1-frac)+right*frac
    observer, basis = pose(p[:2])
    los = positions-observer; length = np.linalg.norm(los, axis=-1)
    world = los/length[..., None]; unit = world@basis.T
    if not derivatives:
        return unit
    dp = np.empty((n, k, 3, 2))
    for j in range(2):
        delta = np.eye(2)[j]*1e-3
        xp, bp = pose(p[:2]+delta); xm, bm = pose(p[:2]-delta)
        dx = (xp-xm)/.002; db = (bp-bm)/.002
        du = (-dx+world*(world@dx)[..., None])/length[..., None]
        dp[..., j] = du@basis.T+world@db.T
    rate = (right-left)/step
    dt = ((rate-world*np.sum(world*rate, axis=-1)[..., None])/length[..., None])@basis.T
    return unit, dp, dt


class Likelihood:
    def __init__(self, data, features):
        self.measured = data.measured; self.features = features
        self.coefficients = np.zeros(features.shape[1]); self.weights = row_weights(data, 'C1')
        self.alias_hz = 1/4.4e-6; self.clutter_rate = 2.
        self.detection_probability = .8/len(data.numbers)
        self.geometry = None; self.last_result = None

    def evaluate(self, predicted, visible, *, sigma_hz, **unused):
        sine, log_factor = self.geometry
        gate, dg = gate_terms(sine, 'Q1')
        base = self.detection_probability*gate
        q = tilt(base, log_factor)
        result = finite_set_terms(self.measured, predicted+(self.features@self.coefficients)[:, None],
                                  q, self.weights, sigma_hz, self.clutter_rate)
        _, db, dla = tilt(base, log_factor, -result['probability_gradient'])
        result['sine_loss_gradient'] = db*self.detection_probability*dg
        result['log_factor_loss_gradient'] = dla
        self.last_result = result
        return result


class Objective(BaseObjective):
    def __init__(self, data, center, arm, strength, theta, frames, support):
        super().__init__(data, center, arm, 'C1')
        self.data = data; self.strength = strength; self.theta = theta
        self.frames = frames; self.support = support
        self.likelihood = Likelihood(data, self.features)
        self.base.likelihood = self.likelihood
        self.cache_key = None; self.geometry_cache = None

    def geometry(self, physical):
        key = np.r_[physical[:2], physical[6:]]
        if self.cache_key is not None and np.array_equal(key, self.cache_key):
            return self.geometry_cache
        u, dp, dt = directions(self.data, physical)
        loga = np.zeros(u.shape[:2]); ja = np.zeros_like(u)
        if self.strength:
            v, jv = cone_marginals(u, self.theta, self.frames)
            rx = np.broadcast_to(self.data.receiver[:, None, None], u.shape[:2]+(1,))
            value = np.take_along_axis(v, rx, axis=-1)[..., 0]
            derivative = np.take_along_axis(jv, rx[..., None], axis=2)[..., 0, :]
            conf, jc = self.support.evaluate(u)
            a = .1+.9*value
            loga = self.strength*conf*np.log(a)
            ja = self.strength*(jc*np.log(a)[..., None]+conf[..., None]*.9/a[..., None]*derivative)
        self.cache_key = key.copy(); self.geometry_cache = (u, dp, dt, loga, ja)
        return self.geometry_cache

    def evaluate(self, vector):
        self.base.check_deadline()
        state = self.base.state(np.asarray(vector[:self.size]))
        if not state['ephemeris_valid']:
            return super().evaluate(vector)
        u, dp, dt, loga, ja = self.geometry(state['parameters'])
        self.likelihood.geometry = (u[..., 2], loga)
        value, gradient = super().evaluate(vector)
        result = self.likelihood.last_result
        dunit = ja*result['log_factor_loss_gradient'][..., None]
        dunit[..., 2] += result['sine_loss_gradient']
        physical = np.zeros(6+len(self.data.numbers))
        physical[:2] = np.einsum('nkj,nkjd->d', dunit, dp)
        physical[6:] = np.sum(dunit*dt, axis=(0, 2))
        gradient[:self.size] += self.base.vector_gradient(physical, vector[:self.size])
        return value, gradient
