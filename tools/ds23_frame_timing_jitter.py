"""RF-only per-frame timing jitter with a fixed Gaussian engineering prior.

Carrier, global epoch and code rate retain their old meanings. Each guarded
frame gets one timing perturbation, with separate complex gain and DC. Sample
splits keep the same guarded support, independent of estimated parameters.
"""

import copy
import numpy as np

from fast_local_pilot_refinement import FastPilotWorkspace


def restrict_samples(workspace, half):
    if half not in (0, 1):
        raise ValueError('first or second temporal half required')
    p = copy.copy(workspace)
    p.frames = [ix[:len(ix)//2] if half == 0 else ix[len(ix)//2:] for ix in workspace.frames]
    p.raw_sum = [p.y[ix].sum() for ix in p.frames]
    p.raw_energy = [float(np.vdot(p.y[ix], p.y[ix]).real-abs(p.raw_sum[k])**2/len(ix))
                    for k, ix in enumerate(p.frames)]
    # Never share a mutable rotation cache between disjoint training problems.
    from collections import OrderedDict
    p._rotation_cache = OrderedDict(); p._rotation_cached_bytes = 0
    return p


class FrameJitterWorkspace(FastPilotWorkspace):
    def signal_and_derivatives(self, parameters, control=False):
        f, offset, ppm = parameters[:3]
        jitter = np.asarray(parameters[3:])
        if jitter.shape != (len(self.frames),):
            raise ValueError('one jitter per original guarded frame required')
        # Parameter-independent original frame membership includes held-out
        # samples even when self.frames has been restricted to training data.
        labels = np.clip(np.floor((self.n-self.epoch)/self.period).astype(int), 0, len(jitter)-1)
        delta = self.n-self.epoch-offset-jitter[labels]
        a = 1+ppm*1e-6
        position = delta*a*32
        index = np.floor(position).astype(np.int64); fraction = position-index
        wave = self.control if control else self.wave
        left, right = wave[index % len(wave)], wave[(index+1) % len(wave)]
        rotation = np.exp(2j*np.pi*f*(self.t-self.mid))
        signal = (left+(right-left)*fraction)*rotation
        slope = (right-left)*rotation
        d = np.column_stack((2j*np.pi*(self.t-self.mid)*signal*100,
                             -32*a*slope, 32e-6*delta*slope*20))
        return signal, d, -.1*32*a*slope

    def jitter_statistics(self, parameters, sigma):
        if sigma <= 0 or not np.isfinite(parameters).all():
            raise ValueError('finite parameters and positive jitter SD required')
        signal, derivative, jitter_derivative = self.signal_and_derivatives(parameters)
        n = len(parameters); normal = np.zeros((n, n)); rhs = np.zeros(n)
        explained = raw = 0.; count = 0
        for k, ix in enumerate(self.frames):
            s = signal[ix]; s = s-s.mean()
            y = self.y[ix]-self.raw_sum[k]/len(ix)
            energy = float(np.vdot(s, s).real)
            if energy <= 1e-20:
                continue
            amplitude = np.vdot(s, y)/energy; residual = y-amplitude*s
            explained += abs(np.vdot(s, y))**2/energy; raw += self.raw_energy[k]; count += len(ix)
            d = np.column_stack((derivative[ix], jitter_derivative[ix]))
            summed, cross = d.sum(axis=0), s.conj()@d
            gram = d.conj().T@d-np.outer(summed.conj(), summed)/len(ix)-np.outer(cross.conj(), cross)/energy
            columns = [0, 1, 2, 3+k]
            normal[np.ix_(columns, columns)] += abs(amplitude)**2*gram.real
            rhs[columns] += (amplitude.conjugate()*(d.conj().T@residual)).real
        sse = max(raw-explained, raw*1e-15)
        variance = sse/max(count, 1)
        normal *= 2/variance; rhs *= 2/variance
        precision = np.r_[np.zeros(3), np.full(n-3, (.1/sigma)**2)]
        scaled = np.asarray(parameters)/np.r_[100., 1., 20., np.full(n-3, .1)]
        normal += np.diag(precision); rhs -= precision*scaled
        cost = 2*count*np.log(variance)+float(np.sum((np.asarray(parameters[3:])/sigma)**2))
        return dict(normal=normal, rhs=rhs, cost=cost, score=explained/max(raw, 1e-20),
                    residual_energy=sse, raw_energy=raw, sample_count=count)

    def jitter_fit(self, baseline, *, sigma=.15, iterations=24):
        parameters = np.r_[baseline['CFO_hz'], baseline['offset_samples'], baseline['modulation_ppm'],
                           np.zeros(len(self.frames))]
        scale = np.r_[100., 1., 20., np.full(len(self.frames), .1)]
        lower = np.r_[baseline['CFO_hz']-800., -.75, -40., np.full(len(self.frames), -.6)]
        upper = np.r_[baseline['CFO_hz']+800., .75, 40., np.full(len(self.frames), .6)]
        current = self.jitter_statistics(parameters, sigma); calls = 1; damping = 1e-3
        for _ in range(iterations):
            diagonal = np.maximum(np.diag(current['normal']), 1e-8); improved = False
            for _ in range(7):
                step = np.linalg.solve(current['normal']+damping*np.diag(diagonal), current['rhs'])
                limits = np.r_[.6, .25, .5, np.full(len(self.frames), 2.)]
                step /= max(1., float(np.max(abs(step)/limits)))
                proposed = np.clip(parameters+scale*step, lower, upper)
                if np.max(abs((proposed-parameters)/scale)) < 1e-3:
                    break
                candidate = self.jitter_statistics(proposed, sigma); calls += 1
                if candidate['cost'] < current['cost']-1e-8:
                    parameters, current = proposed, candidate; damping = max(1e-8, damping/3)
                    improved = True; break
                damping *= 10
            if not improved:
                break
        return dict(CFO_hz=float(parameters[0]), offset_samples=float(parameters[1]), modulation_ppm=float(parameters[2]),
                    frame_jitter_samples=parameters[3:], score=float(current['score']),
                    residual_energy=float(current['residual_energy']), sample_count=current['sample_count'],
                    penalized_profile_cost=float(current['cost']), optimizer_calls=calls,
                    boundary=bool(np.any(abs(parameters-lower)<1e-4) or np.any(abs(parameters-upper)<1e-4)),
                    fixed_jitter_prior_sigma_samples=sigma)

    def prediction(self, fit, half):
        train = restrict_samples(self, half); test = restrict_samples(self, 1-half)
        parameters = np.r_[fit['CFO_hz'], fit['offset_samples'], fit['modulation_ppm'],
                           fit.get('frame_jitter_samples', np.zeros(len(self.frames)))]
        signal, *_ = self.signal_and_derivatives(parameters)
        sse = energy = 0.; n = 0
        for first, second in zip(train.frames, test.frames, strict=True):
            u = np.column_stack((signal[first], np.ones(len(first))))
            coefficient = np.linalg.lstsq(u, self.y[first], rcond=None)[0]
            residual = self.y[second]-np.column_stack((signal[second], np.ones(len(second))))@coefficient
            sse += float(np.vdot(residual, residual).real)
            energy += float(np.vdot(self.y[second], self.y[second]).real); n += len(second)
        return dict(squared_error=sse, sample_count=n, normalized_error=sse/max(energy, 1e-20),
                    all_nuisance_parameters_fitted_only_on_training_samples=True)
