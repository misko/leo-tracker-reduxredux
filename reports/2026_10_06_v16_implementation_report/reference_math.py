"""Small independent numerical reference for the V16 report (NumPy only).

This is not a replacement for the production IQ reader or a new position fit.
Units: Hz, seconds, km. No orbit, storage, or original research-module imports.
"""
import numpy as np

ALIAS_HZ = 1 / 4.4e-6


def wrap(value):
    return (np.asarray(value) + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def zero_sum_basis(k):
    if k < 1:
        raise ValueError("At least one satellite required")
    b = np.zeros((k, k - 1))
    for j in range(k - 1):
        scale = np.sqrt((j + 1) * (j + 2))
        b[:j + 1, j] = 1 / scale
        b[j + 1, j] = -(j + 1) / scale
    return b


def glrt_spectrum(correlations, size=4096):
    """Already conditioned complex correlations: frame by 64 pilot symbols."""
    z = np.asarray(correlations, complex)
    if z.ndim != 2 or z.shape[1] != 64 or not len(z):
        raise ValueError("Expected supported frames by 64 symbols")
    power = np.sum(abs(np.fft.fft(z, n=size, axis=1)) ** 2, axis=0)
    ceiling = np.sum(np.sum(abs(z), axis=1) ** 2)
    spectrum = power / ceiling if ceiling > 0 else np.zeros(size)
    frequencies = np.fft.fftfreq(size, d=4.4e-6)
    best = int(np.argmax(spectrum))
    return frequencies, spectrum, float(frequencies[best]), float(spectrum[best])


def single_window_terms(y, mu, visible, sigma=125., detection_budget=1.6, clutter=.5):
    """Conditioned singleton finite-set likelihood; stable log-domain arithmetic.

    Returns log density, responsibilities, clutter probability, d(NLL)/d(mu).
    No derivative of the hard visibility indicator is taken.
    """
    mu = np.asarray(mu, float)
    y = np.asarray(y, float)
    visible = np.asarray(visible, bool)
    if mu.ndim != 2 or visible.shape != mu.shape or y.shape != (len(mu),):
        raise ValueError("Window/satellite dimensions disagree")
    k = mu.shape[1]
    if not (sigma > 0 and clutter > 0 and 0 < detection_budget < k):
        raise ValueError("Invalid likelihood hyperparameters")
    q = np.where(visible, detection_budget / k, 0.)
    r = wrap(y[:, None] - mu)
    image_count = max(1, int(np.ceil((sigma * np.sqrt(-2*np.log(1e-15)) + ALIAS_HZ/2) / ALIAS_HZ)))
    images = r[:, :, None] + np.arange(-image_count, image_count+1) * ALIAS_HZ
    log_images = -.5 * (images/sigma)**2 - np.log(sigma) - .5*np.log(2*np.pi)
    log_phi = np.logaddexp.reduce(log_images, axis=2)
    mean_image = np.sum(np.exp(log_images-log_phi[:, :, None]) * images, axis=2)
    log_odds = np.full_like(q, -np.inf)
    log_odds[visible] = np.log(q[visible])-np.log1p(-q[visible])
    signal = log_odds + log_phi
    log_h = np.logaddexp(np.log(clutter/ALIAS_HZ), np.logaddexp.reduce(signal, axis=1))
    log_p0 = -clutter + np.log1p(-q).sum(axis=1)
    log_l = log_p0 - np.log(-np.expm1(log_p0)) + log_h
    responsibilities = np.exp(signal-log_h[:, None])
    clutter_probability = np.exp(np.log(clutter/ALIAS_HZ)-log_h)
    gradient = -responsibilities * mean_image / sigma**2
    return log_l, responsibilities, clutter_probability, gradient


def timing_penalty(tau, relative, common_sigma=3., relative_sigma=.15):
    relative = np.asarray(relative, float)
    return .5*(tau/common_sigma)**2 + .5*np.sum((relative/relative_sigma)**2)


def doppler(data, parameters, rf_center, coefficient):
    """Reproduce the saved research coordinate convention and orbit interpolation.

    parameters=[internal east, internal north, a0,b0,a1,b1,total shifts...].
    Internal coordinates are the old Sacramento-origin chart, NOT roof offsets.
    Input ephemerides must already be rotating ECEF, including -omega cross r.
    """
    p = np.asarray(parameters)
    lat0, lon0 = np.deg2rad([38.5816, -121.4944])
    angular = np.hypot(p[0], p[1])/6371.0088
    bearing = np.arctan2(p[0], p[1])
    lat = np.arcsin(np.sin(lat0)*np.cos(angular)+np.cos(lat0)*np.sin(angular)*np.cos(bearing))
    lon = lon0+np.arctan2(np.sin(bearing)*np.sin(angular)*np.cos(lat0), np.cos(angular)-np.sin(lat0)*np.sin(lat))
    e2 = 6.6943799901413165e-3
    n = 6378.137 / np.sqrt(1-e2*np.sin(lat)**2)
    observer = np.array([n*np.cos(lat)*np.cos(lon), n*np.cos(lat)*np.sin(lon), n*(1-e2)*np.sin(lat)])
    up = np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    times = data['times']
    query = times[:, None]+p[6:][None, :]
    nodes = data['nodes']; step = nodes[1]-nodes[0]
    if np.any(query < nodes[0]) or np.any(query >= nodes[-1]):
        raise ValueError('Outside state bank support')
    fraction = (query-nodes[0])/step
    lower = np.floor(fraction).astype(int); w = (fraction-lower)[:, :, None]
    satellites = np.arange(len(p)-6)[None, :]
    pos = (1-w)*data['position'][satellites, lower]+w*data['position'][satellites, lower+1]
    vel = (1-w)*data['velocity'][satellites, lower]+w*data['velocity'][satellites, lower+1]
    delta = pos-observer
    direction = delta/np.linalg.norm(delta, axis=2)[:, :, None]
    orbit = -data['rf'][:, None]*np.sum(direction*vel, axis=2)/299792.458
    rx = data['receiver']
    baseline = p[2+2*rx]+p[3+2*rx]*(times-150.)+coefficient*(data['rf']-rf_center)/1e9
    return orbit+baseline[:, None], np.sum(direction*up, axis=2) >= 0
