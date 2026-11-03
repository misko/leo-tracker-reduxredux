"""Jointly profile simultaneous pilot components on fixed training IQ support."""

import numpy as np

from ds23_training_channel_rf import TrainingChannelWorkspace


def common_segments(geometries, minimum_samples=112, trim=16):
    """Keep every physical transmitter frame at most once in each geometry."""
    if len(geometries) < 2:
        raise ValueError('at least two component geometries required')
    valid = np.logical_and.reduce([g['valid'] for g in geometries])
    labels = np.column_stack([g['frame'] for g in geometries])
    changes = np.any(np.diff(labels, axis=0) != 0, axis=1) | (np.diff(valid.astype(int)) != 0)
    boundaries = np.r_[0, np.flatnonzero(changes)+1, len(valid)]
    candidates = [np.arange(a+trim, b-trim) for a, b in zip(boundaries[:-1], boundaries[1:], strict=True)
        if valid[a] and b-a >= minimum_samples+2*trim]
    used = [set() for _ in geometries]
    result = []
    for ix in sorted(candidates, key=lambda ix:(-len(ix), int(ix[0]))):
        keys = labels[ix[0]]
        if any(int(k) in u for k, u in zip(keys, used, strict=True)):
            continue
        result.append(ix)
        for k, u in zip(keys, used, strict=True):
            u.add(int(k))
    return sorted(result, key=lambda ix:ix[0])


class JointComponentWorkspace(TrainingChannelWorkspace):
    """Two carriers/epochs/rates; flat or eight-tone channels for each frame."""

    parameter_scale = np.tile([100., 1., 20.], 2)

    def __init__(self, samples, fs, edge, epochs, segments, *, per_tone=False):
        if len(epochs) != 2:
            raise ValueError('exactly two simultaneous components required')
        super().__init__(samples, fs, edge, epochs[0], segments)
        self.components = [TrainingChannelWorkspace(samples, fs, edge, epoch, segments) for epoch in epochs]
        self.per_tone = per_tone

    def columns(self, parameters, *, derivatives=False, control=False):
        parameters = np.asarray(parameters, float)
        if parameters.shape != (6,) or not np.isfinite(parameters).all():
            raise ValueError('six finite RF parameters required')
        result, derivative = [], []
        for k, component in enumerate(self.components):
            values = component.columns(parameters[3*k:3*k+3], derivatives=derivatives, control=control)
            if derivatives:
                values, d = values
            if not self.per_tone:
                values = values.sum(axis=1, keepdims=True)
                if derivatives:
                    d = tuple(v.sum(axis=1, keepdims=True) for v in d)
            result.append(values)
            if derivatives:
                derivative.append(d)
        columns = np.column_stack(result)
        if not derivatives:
            return columns
        zero = np.zeros_like(result[0])
        all_derivatives = tuple(np.column_stack((d, zero)) for d in derivative[0])
        all_derivatives += tuple(np.column_stack((zero, d)) for d in derivative[1])
        return columns, all_derivatives

    def statistics(self, parameters, subset='all', derivatives=True, *, control=False):
        if subset not in ('all', 'odd', 'even'):
            raise ValueError('named frame subset required')
        if derivatives:
            columns, derivative = self.columns(parameters, derivatives=True, control=control)
        else:
            columns = self.columns(parameters, control=control)
        normal, rhs = np.zeros((6, 6)), np.zeros(6)
        raw = explained = 0.
        count = frames = 0
        for k, ix in enumerate(self.frames):
            if subset == 'odd' and k % 2 == 0 or subset == 'even' and k % 2 == 1:
                continue
            basis = columns[ix]-columns[ix].mean(axis=0)
            y = self.y[ix]-self.raw_sum[k]/len(ix)
            gram = basis.conj().T@basis
            cross = basis.conj().T@y
            coefficients = np.linalg.solve(gram, cross)
            residual = y-basis@coefficients
            explained += float(np.vdot(cross, coefficients).real)
            raw += self.raw_energy[k]
            count += len(ix)
            frames += 1
            if derivatives:
                d = np.column_stack([v[ix]@coefficients for v in derivative])
                d -= d.mean(axis=0)
                projected = d-basis@np.linalg.solve(gram, basis.conj().T@d)
                normal += (projected.conj().T@projected).real
                rhs += (d.conj().T@residual).real
        return dict(score=float(explained/max(raw, 1e-20)), normal=normal, rhs=rhs,
            gradient_score=2*rhs/max(raw, 1e-20), raw_energy=raw,
            residual_energy=float(raw-explained), sample_count=count, frames=frames)

    def joint_fit(self, seeds, *, iterations=24):
        parameters = np.array([[s['CFO_hz'], s['offset_samples'], s['modulation_ppm']] for s in seeds]).ravel()
        center = parameters.copy()
        lower = np.tile([-np.inf, -.75, -40.], 2)
        upper = np.tile([np.inf, .75, 40.], 2)
        lower[::3], upper[::3] = center[::3]-800, center[::3]+800
        current = self.statistics(parameters)
        history = [dict(parameters=parameters.copy(), score=current['score'])]
        damping = 1e-3
        for _ in range(iterations):
            diagonal = np.maximum(np.diag(current['normal']), current['raw_energy']*1e-14)
            improved = False
            for _ in range(6):
                step = np.linalg.solve(current['normal']+damping*np.diag(diagonal), current['rhs'])
                step /= max(1., float(np.max(abs(step)/np.tile([.6, .25, .5], 2))))
                proposed = np.clip(parameters+self.parameter_scale*step, lower, upper)
                if np.max(abs((proposed-parameters)/self.parameter_scale)) < 1e-3:
                    break
                candidate = self.statistics(proposed)
                if candidate['score'] > current['score']+1e-12:
                    parameters, current = proposed, candidate
                    history.append(dict(parameters=parameters.copy(), score=current['score']))
                    damping = max(1e-8, damping/3)
                    improved = True
                    break
                damping *= 10
            if not improved:
                break
        noise = current['residual_energy']/max(1,
            current['sample_count']-(17 if self.per_tone else 3)*current['frames'])
        covariance = np.linalg.pinv(current['normal'], rcond=1e-12)*noise/2
        covariance *= self.parameter_scale[:, None]*self.parameter_scale[None, :]
        return dict(parameters=parameters, score=current['score'], history=history,
            boundary=bool(np.any(abs(parameters-lower) < 1e-4) or np.any(abs(parameters-upper) < 1e-4)),
            conditional_covariance=covariance, covariance_is_local_Gaussian_proxy_not_calibrated=True,
            per_tone=self.per_tone)
