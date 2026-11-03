"""Pure receiver-cone direction evidence and mass-preserving prior tilt."""
import numpy as np
from scipy.special import logsumexp
from scipy.interpolate import RectBivariateSpline
from scipy.ndimage import gaussian_filter


def cone_marginals(unit, theta, frames):
    """Conditional P(RXr present | at least one present) and ENU derivatives."""
    u = np.asarray(unit)
    shape = u.shape[:-1]
    u = u.reshape(-1, 3)
    alpha, beta, logw, roll0, roll1 = theta
    matrices = []
    for fr, roll in zip(frames, (roll0, roll1)):
        up, az, bore = fr
        matrices.append(np.stack([np.cos(roll)*up+np.sin(roll)*az,
                                  -np.sin(roll)*up+np.cos(roll)*az, bore]))
    m = np.asarray(matrices)
    xyz = np.einsum('ni,rji->nrj', u, m)
    x, y, z = xyz.transpose(2, 0, 1)
    ca, cb = 1/np.tan(alpha), 1/np.tan(beta)
    h = np.sqrt((x*ca)**2+(y*cb)**2+1e-24)
    l = (z-h)*np.exp(-logw)
    jl = (m[None, :, 2, :]-x[:, :, None]*ca**2/h[:, :, None]*m[None, :, 0, :]
          -y[:, :, None]*cb**2/h[:, :, None]*m[None, :, 1, :])*np.exp(-logw)
    scores = np.column_stack([l, l.sum(axis=1)])
    p = np.exp(scores-logsumexp(scores, axis=1)[:, None])
    js = np.concatenate([jl, jl.sum(axis=1)[:, None, :]], axis=1)
    jp = p[:, :, None]*(js-np.sum(p[:, :, None]*js, axis=1)[:, None, :])
    v = np.column_stack([1-p[:, 1], 1-p[:, 0]])
    jv = -jp[:, [1, 0], :]
    return v.reshape(shape+(2,)), jv.reshape(shape+(2, 3))


class Support:
    """Smooth display-support mask; neutral cone evidence where unsupported.

    Cubic interpolation of a two-pixel Gaussian-smoothed binary support mask.
    This prevents discrete nearest-pixel jumps in the position objective.
    """
    def __init__(self, inside, supported):
        values = np.zeros(inside.shape)
        values[inside] = supported
        values = gaussian_filter(values, 2., mode='constant')
        axis = np.linspace(-1, 1, len(values))
        self.spline = RectBivariateSpline(axis, axis, values.T, kx=3, ky=3)

    def evaluate(self, unit):
        u = np.asarray(unit); shape = u.shape[:-1]; u = u.reshape(-1, 3)
        e, n, z = u.T; h = np.hypot(e, n); safe = np.maximum(h, 1e-8)
        angle = np.arctan2(h, z); factor = 2/np.pi*angle/safe
        dfh = 2/np.pi*(z/(safe*safe+z*z)/safe-angle/safe**2)
        dfz = -2/np.pi/(safe*safe+z*z)
        near = h < 1e-8
        factor[near] = 2/np.pi/z[near]; dfh[near] = 0.
        x, y = factor*e, factor*n
        val = self.spline.ev(x, y)
        dx = self.spline.ev(x, y, dx=1); dy = self.spline.ev(x, y, dy=1)
        jac = np.column_stack([dx*factor+(dx*e+dy*n)*dfh*e/safe,
                               dy*factor+(dx*e+dy*n)*dfh*n/safe,
                               (dx*e+dy*n)*dfz])
        clip = (val<=0)|(val>=1)|(x*x+y*y>1)
        val = np.clip(val, 0, 1); val[x*x+y*y>1] = 0
        jac[clip] = 0.
        return val.reshape(shape), jac.reshape(shape+(3,))


def tilt(base, log_factor, gradient=None):
    """Keep sum(q) unchanged. Optional d loss/dq -> derivatives of b, log a."""
    b = np.asarray(base); a = np.exp(log_factor)
    total = b.sum(axis=1, keepdims=True); z = np.sum(b*a, axis=1, keepdims=True)
    ratio = np.divide(b*a, z, out=np.zeros_like(b), where=z>0)
    q = total*ratio
    if gradient is None:
        return q
    g = np.asarray(gradient)
    average = (ratio*g).sum(axis=1, keepdims=True)
    db = average+np.divide(total*a, z, out=np.zeros_like(b), where=z>0)*(g-average)
    dla = q*(g-average)
    return q, db, dla
