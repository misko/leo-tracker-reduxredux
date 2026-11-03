"""Conditional simultaneous-component receiver-clock likelihood.

Frame transmitter gains are free.  Both receiver extraction covariances are
retained, including their complex cross-component entries.  The common-clock
model has one physical RX frequency difference; the comparator has one per
component. This is RF-only research, not a calibrated positioning observation.
"""

from itertools import product
import numpy as np
from scipy.optimize import minimize


def align_frame_phase_branch(native_delta, times, target, covariance, *, exact=True):
    """Keep carrier aliases intact while choosing a local 750 Hz clock branch.

    Demodulated gains depend on the *raw* carrier difference. Subtracting a
    227272.727Hz carrier alias before interpreting them loses22.727Hz modulo
    the750Hz frame cadence. For exact timing, removing m*750 from the native
    difference requires the matching target-gain/covariance phase rotation.
    """
    raw, t = np.asarray(native_delta, float), np.asarray(times, float)
    b, vb = np.asarray(target), np.asarray(covariance)
    if raw.ndim != 1 or b.shape != (len(t), len(raw)) or vb.shape != (len(t), len(raw), len(raw)):
        raise ValueError('matching raw carrier differences, frames, and complex covariance required')
    if not all(np.isfinite(v).all() for v in [raw, t, b, vb]):
        raise ValueError('finite RF data required')
    cycles = np.rint((raw-raw[0])/750).astype(np.int64)
    aligned = raw-cycles*750
    rotation = np.exp(2j*np.pi*(t-t.mean())[:, None]*(cycles*750)[None]) if exact else np.ones_like(b)
    changed = b*rotation
    changed_covariance = rotation[:, :, None]*vb*rotation[:, None, :].conj()
    return dict(native_delta_hz=aligned, gain=changed, covariance=changed_covariance,
        removed_frame_phase_cycles=cycles, exact_sample_times=exact,
        no_pilot_CFO_alias_subtracted_before_frame_phase=True)


def validate(times, first, second, covariance_first, covariance_second):
    t, a, b, va, vb = map(np.asarray, (times, first, second, covariance_first, covariance_second))
    if t.ndim != 1 or len(t) < 4 or a.ndim != 2 or b.shape != a.shape or a.shape[0] != len(t):
        raise ValueError('four ordered frames and matching complex component vectors required')
    expected = (len(t), a.shape[1], a.shape[1])
    if va.shape != expected or vb.shape != expected or not 1 <= a.shape[1] <= 4:
        raise ValueError('full matching component covariance required')
    if not all(np.isfinite(v).all() for v in (t, a, b, va, vb)) or np.any(np.diff(t) <= 0):
        raise ValueError('finite ordered samples and covariances required')
    for covariance in [va, vb]:
        if not np.allclose(covariance, covariance.swapaxes(1, 2).conj(), atol=1e-10, rtol=1e-8):
            raise ValueError('Hermitian extraction covariance required')
        if np.any(np.linalg.eigvalsh(covariance) <= 0):
            raise ValueError('positive definite extraction covariance required')
    return t.astype(float), a.astype(complex), b.astype(complex), va.astype(complex), vb.astype(complex)


def project_components(coefficients, covariance, training, component_width=1):
    """Train channel directions, retaining covariance between scalar gains."""
    c, cov, train = np.asarray(coefficients), np.asarray(covariance), np.asarray(training, bool)
    if c.ndim != 2 or c.shape[1] % component_width or cov.shape != (len(c), c.shape[1], c.shape[1]):
        raise ValueError('matching joint coefficients and full complex covariance required')
    if train.shape != (len(c),) or train.sum() < 4:
        raise ValueError('four training frames required')
    count = c.shape[1] // component_width
    projection = np.zeros((count, c.shape[1]), complex)
    rank_one = []
    for k in range(count):
        sl = slice(k*component_width, (k+1)*component_width)
        _, singular, vh = np.linalg.svd(c[train, sl], full_matrices=False)
        projection[k, sl] = vh[0].conj()
        rank_one.append(float(singular[0]**2/np.sum(singular**2)))
    gains = c @ projection.T
    propagated = np.einsum('ai,nij,bj->nab', projection, cov, projection.conj())
    return dict(gain=gains, covariance=propagated, projection=projection,
        training_rank_one_fractions=rank_one)


def frequency_corrections(parameters, native_delta, mode):
    count = len(native_delta)
    if mode == 'common':
        return parameters[2*count]+native_delta[0]-native_delta
    if mode in ('separate', 'independent'):
        return np.asarray(parameters[2*count:3*count])
    raise ValueError('common, separate, or independent model required')


def loss(parameters, times, first, second, covariance_first, covariance_second,
         native_delta, mode, *, prior=True, gradient=False):
    """Proper complex conditional NLL, with matching frequency priors."""
    count = first.shape[1]
    frequency_count = 1 if mode == 'common' else count
    p = np.asarray(parameters, float)
    if p.shape != (3*count+frequency_count,) or np.shape(native_delta) != (count,):
        raise ValueError('matching clock, ratios, discrepancy, and native differences required')
    ratio = p[:2*count:2]+1j*p[1:2*count:2]
    frequencies = frequency_corrections(p, np.asarray(native_delta), mode)
    phase = np.exp(2j*np.pi*times[:, None]*frequencies[None])
    rotation = phase*ratio[None]
    shared = mode != 'independent'
    predictor = first if shared else np.ones_like(first)
    discrepancy = np.exp(p[-count:])
    covariance = covariance_second.copy()
    if shared:
        covariance += rotation[:, :, None]*covariance_first*rotation[:, None, :].conj()
    covariance += np.diag(discrepancy)[None]
    residual = second-rotation*predictor
    precision = np.linalg.inv(covariance)
    precision_residual = np.einsum('nij,nj->ni', precision, residual)
    _, logdet = np.linalg.slogdet(covariance)
    value = float(np.sum(logdet+count*np.log(np.pi)
        + np.einsum('ni,ni->n', residual.conj(), precision_residual).real))
    if prior:
        value += float(np.sum((frequencies/100.)**2))
    if not gradient:
        return value
    covariance_gradient = precision-precision_residual[:, :, None]*precision_residual[:, None, :].conj()
    result = np.empty(len(p))
    for index in range(len(p)):
        dr = np.zeros_like(rotation)
        if index < 2*count:
            k = index//2
            dr[:, k] = phase[:, k]*(1j if index % 2 else 1.)
        elif index < 2*count+frequency_count:
            if mode == 'common':
                dr = 2j*np.pi*times[:, None]*rotation
            else:
                k = index-2*count
                dr[:, k] = 2j*np.pi*times*rotation[:, k]
        dcov = np.zeros_like(covariance)
        if shared:
            dcov = dr[:, :, None]*covariance_first*rotation[:, None, :].conj()
            dcov += rotation[:, :, None]*covariance_first*dr[:, None, :].conj()
        if index >= 2*count+frequency_count:
            k = index-(2*count+frequency_count)
            dcov[:, k, k] += discrepancy[k]
        de = -dr*predictor
        result[index] = (np.einsum('nij,nji->', covariance_gradient, dcov).real
            + 2*np.einsum('ni,ni->', de.conj(), precision_residual).real)
        if prior and 2*count <= index < 2*count+frequency_count:
            result[index] += float(2*np.sum(frequencies)/10000) if mode == 'common' else 2*frequencies[index-2*count]/10000
    return value, result


def fit(times, first, second, covariance_first, covariance_second, native_delta, *, mode='common'):
    t, a, b, va, vb = validate(times, first, second, covariance_first, covariance_second)
    native = np.asarray(native_delta, float)
    count = a.shape[1]
    if native.shape != (count,) or not np.isfinite(native).all():
        raise ValueError('finite native receiver differences required')
    frequency_count = 1 if mode == 'common' else count
    center = float(t.mean())
    t = t-center
    scale_a = np.maximum(np.sqrt(np.mean(abs(a)**2, axis=0)), 1e-12)
    scale_b = np.maximum(np.sqrt(np.mean(abs(b)**2, axis=0)), 1e-12)
    a, b = a/scale_a[None], b/scale_b[None]
    va = va/(scale_a[None, :, None]*scale_a[None, None, :])
    vb = vb/(scale_b[None, :, None]*scale_b[None, None, :])
    if mode == 'common':
        lower_f = np.array([max(native-native[0]-375)])
        upper_f = np.array([min(native-native[0]+375)])
        if lower_f[0] >= upper_f[0]:
            raise ValueError('native component differences have no common 750Hz correction branch')
    else:
        lower_f, upper_f = np.full(count, -375.), np.full(count, 375.)
    lower = np.r_[np.full(2*count, -3.), lower_f, np.full(count, -16.)]
    upper = np.r_[np.full(2*count, 3.), upper_f, np.full(count, 3.)]
    scale = np.r_[np.ones(2*count), np.full(frequency_count, 100.), np.ones(count)]
    predictor = a if mode != 'independent' else np.ones_like(a)
    weights = 1/(np.diagonal(va+vb, axis1=1, axis2=2).real+.1)

    def seed(freq):
        corrections = freq+native[0]-native if mode == 'common' else freq
        rotation = np.exp(-2j*np.pi*t[:, None]*corrections[None])
        ratio = np.sum(weights*b*predictor.conj()*rotation, axis=0)/np.sum(weights*abs(predictor)**2, axis=0)
        return np.clip(np.r_[np.column_stack((ratio.real, ratio.imag)).ravel(), freq,
            np.full(count, np.log(.1))], lower, upper)

    if mode == 'common':
        candidates = [seed(np.array([f])) for f in np.linspace(lower_f[0], upper_f[0], 751)]
    else:
        proposals = []
        frequencies = np.linspace(-375, 375, 751)
        for k in range(count):
            cross = np.exp(-2j*np.pi*frequencies[:, None]*t[None]) @ (weights[:, k]*b[:, k]*predictor[:, k].conj())
            chosen = []
            for j in np.argsort(abs(cross))[::-1]:
                if all(abs(frequencies[j]-f) >= 20 for f in chosen):
                    chosen.append(float(frequencies[j]))
                    if len(chosen) == 3:
                        break
            proposals.append(chosen)
        candidates = [seed(np.array(f)) for f in product(*proposals)]
    ranked = sorted(candidates, key=lambda p:loss(p, t, a, b, va, vb, native, mode))
    selected = []
    for p in ranked:
        if all(np.linalg.norm(p[2*count:2*count+frequency_count]-q[2*count:2*count+frequency_count]) >= 20 for q in selected):
            selected.append(p)
            if len(selected) == 3:
                break
    trials = []
    for start in selected:
        def objective(x):
            value, derivative = loss(x*scale, t, a, b, va, vb, native, mode, gradient=True)
            return value, derivative*scale
        result = minimize(objective, start/scale, jac=True, method='L-BFGS-B',
            bounds=list(zip(lower/scale, upper/scale, strict=True)),
            options=dict(maxiter=180, ftol=1e-10, gtol=1e-6))
        if np.isfinite(result.fun):
            trials.append(result)
    if not trials:
        raise ValueError('no finite joint clock fit')
    best = min(trials, key=lambda r:r.fun)
    parameters = best.x*scale
    delta = frequency_corrections(parameters, native, mode)
    return dict(parameters=parameters, mode=mode, native_delta_hz=native, time_center_s=center,
        first_scale=scale_a, second_scale=scale_b, penalized_training_NLL=float(best.fun),
        converged=bool(best.success), optimizer_message=str(best.message),
        corrected_RX_delta_hz=None if mode == 'independent' else native+delta,
        residual_frequency_corrections_hz=delta,
        boundary=bool(np.any(abs(parameters-lower) < 1e-3) or np.any(abs(parameters-upper) < 1e-3)),
        branch_correction_boundary=bool(np.any(abs(delta) >= 374.5)),
        frequency_ambiguity_period_hz=750., total_frequency_uncertainty_not_calibrated=True)


def predict(model, times, first, second, covariance_first, covariance_second):
    t, a, b, va, vb = validate(times, first, second, covariance_first, covariance_second)
    sa, sb = np.asarray(model['first_scale']), np.asarray(model['second_scale'])
    a, b = a/sa[None], b/sb[None]
    va, vb = va/(sa[None, :, None]*sa[None, None, :]), vb/(sb[None, :, None]*sb[None, None, :])
    value = loss(np.asarray(model['parameters']), t-model['time_center_s'], a, b, va, vb,
        np.asarray(model['native_delta_hz']), model['mode'], prior=False)
    return float(value+2*len(t)*np.log(sb).sum())
