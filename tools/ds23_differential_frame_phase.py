"""RF-only held-frame tests of single and differential carrier continuity.

The two transmitters may reset their phase independently. No continuity is
assumed by extraction. Matching keeps each transmitter frame at most once,
so short intersections never masquerade as independent phase observations.
"""

import numpy as np
from scipy.optimize import linear_sum_assignment
from ds23_conditional_pilot_components import component_geometry, component_segments


def unique_frame_intersections(first, second, segments):
    a = np.array([first['frame'][s[0]] for s in segments]); b = np.array([second['frame'][s[0]] for s in segments])
    aa, ai = np.unique(a, return_inverse=True); bb, bi = np.unique(b, return_inverse=True)
    lengths = np.zeros((len(aa), len(bb))); indices = np.full(lengths.shape, -1, int)
    for k, segment in enumerate(segments):
        if len(segment) > lengths[ai[k], bi[k]]:
            lengths[ai[k], bi[k]], indices[ai[k], bi[k]] = len(segment), k
    row, col = linear_sum_assignment(-lengths)
    chosen = [segments[indices[r, c]] for r, c in zip(row, col, strict=True) if indices[r, c] >= 0]
    return sorted(chosen, key=lambda s: s[0])


def project_channel_phase(coefficients, covariance, train):
    c, cov = np.asarray(coefficients), np.asarray(covariance)
    if c.ndim != 2 or cov.shape != (len(c), c.shape[1], c.shape[1]) or train < 3 or train >= len(c):
        raise ValueError('matching channel coefficient covariance and nonempty held-out frames required')
    # The channel shape is learned solely from the training frames.
    _, singular, vh = np.linalg.svd(c[:train], full_matrices=False)
    direction = vh[0].conj(); gain = c@direction
    variance = np.einsum('i,nij,j->n', direction.conj(), cov, direction).real
    if np.any(variance <= 0):
        raise ValueError('positive projected coefficient variance required')
    return dict(gain=gain, phase_weight=abs(gain)**2/variance,
                training_rank_one_energy_fraction=float(singular[0]**2/np.sum(singular**2)))


def extract_phases(samples, fs, edge, first_epoch, first_fit, second_epoch, second_fit):
    y = np.asarray(samples, complex)
    a = component_geometry(y, fs, edge, first_epoch, first_fit)
    b = component_geometry(y, fs, edge, second_epoch, second_fit)
    segments = unique_frame_intersections(a, b, component_segments(a, b))
    if len(segments) < 10:
        raise ValueError('ten distinct matched transmitter frames required')
    design = np.column_stack((a['exact'], b['exact'], np.ones(len(y))))
    coef, covariance, times = [], [], []
    for ix in segments:
        x = design[ix]; c, _, rank, _ = np.linalg.lstsq(x, y[ix], rcond=1e-8)
        if rank != 17:
            raise ValueError('two-component channel design lost rank')
        residual = y[ix]-x@c; noise = float(np.vdot(residual, residual).real/(len(ix)-17))
        coef.append(c); covariance.append(noise*np.linalg.inv(x.conj().T@x)); times.append(float(ix.mean()/fs))
    coef, covariance = np.array(coef), np.array(covariance); train = max(6, len(segments)*2//3)
    first = project_channel_phase(coef[:, :8], covariance[:, :8, :8], train)
    second = project_channel_phase(coef[:, 8:16], covariance[:, 8:16, 8:16], train)
    return dict(time_s=np.array(times), first=first, second=second, train_frames=train,
                frame_pairs=[[int(a['frame'][s[0]]), int(b['frame'][s[0]])] for s in segments])


def heldout_phase_frequency(times, phasor, weights, train, *, controls=256, seed=0):
    t, z, w = np.asarray(times, float), np.asarray(phasor, complex), np.asarray(weights, float)
    if t.ndim != 1 or len(t) < 10 or z.shape != t.shape or w.shape != t.shape or not (6 <= train <= len(t)-3):
        raise ValueError('ten phases with six training and three held-out frames required')
    if not all(np.isfinite(v).all() for v in (t, z, w)) or np.any(w <= 0) or np.any(abs(z) <= 0):
        raise ValueError('finite supported phases and positive weights required')
    z = z/abs(z); w = np.minimum(w, np.median(w[:train])*10); t = t-t[:train].mean()
    rng = np.random.default_rng(seed)
    phases = np.angle(z)[None]+np.vstack((np.zeros(len(t)), rng.uniform(-np.pi, np.pi, (controls, len(t)))))
    records = []; scores = []
    for harmonic in [1, 2, 4]:
        frequency = np.linspace(-375/harmonic, 375/harmonic, 751)
        rotation = np.exp(-2j*np.pi*harmonic*frequency[:, None]*t[None])
        values = np.exp(1j*harmonic*phases)
        train_vectors = rotation[:, :train]@(values[:, :train]*w[:train]).T/w[:train].sum()
        index = np.argmax(abs(train_vectors), axis=0); column = np.arange(controls+1)
        center = np.angle(train_vectors[index, column]); prediction = values*rotation[index]*np.exp(-1j*center[:, None])
        test = (prediction[:, train:]*w[train:]).sum(axis=1)/w[train:].sum()
        coherence = abs(train_vectors[index, column]); score = np.minimum(coherence, test.real)
        scores.append(score)
        records.append(dict(harmonic=harmonic, residual_frequency_hz=float(frequency[index[0]]),
            training_coherence=float(coherence[0]), heldout_predictive_cosine=float(test.real[0]),
            heldout_coherence=float(abs(test[0])), heldout_phase_RMS_rad=float(np.sqrt(np.average(np.angle(prediction[0, train:])**2, weights=w[train:]))),
            search_boundary=bool(index[0] in [0, len(frequency)-1])))
    maxima = np.max(scores, axis=0); best = int(np.argmax(np.array(scores)[:, 0]))
    probability = float((1+sum(maxima[1:] >= maxima[0]))/(controls+1))
    return dict(harmonics=records, best_harmonic=records[best]['harmonic'], continuity_score=float(maxima[0]),
        phase_randomization_tail_probability=probability, surrogate_controls=controls,
        candidate_for_independent_replication=bool(maxima[0] > .85 and probability < .01 and not records[best]['search_boundary']),
        no_frequency_correction_applied=True, harmonic_search_included_in_surrogate_control=True,
        frequency_and_intercept_fit_only_on_training_frames=True)
