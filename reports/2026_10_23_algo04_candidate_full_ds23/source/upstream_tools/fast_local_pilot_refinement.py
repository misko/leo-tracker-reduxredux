"""Bounded continuous carrier/epoch/rate fit with analytic projected derivatives."""

import numpy as np
from local_pilot_refinement import PilotWorkspace


class FastPilotWorkspace(PilotWorkspace):
    """Use the same pilot likelihood, per-frame complex gains and DC as the grid."""

    parameter_scale = np.array([100., 1., 20.])

    def statistics(self, parameters, subset='all', derivatives=True):
        f, offset, ppm = np.asarray(parameters, float)
        if not np.isfinite(parameters).all() or subset not in ('all', 'odd', 'even'):
            raise ValueError('finite carrier/epoch/rate and a named frame subset required')
        position = (self.n-self.epoch-offset)*(1+ppm*1e-6)*32
        index = np.floor(position).astype(np.int64)
        fraction = position-index
        a, b = self.wave[index % len(self.wave)], self.wave[(index+1) % len(self.wave)]
        replica = a+(b-a)*fraction
        rotation = np.exp(2j*np.pi*f*(self.t-self.mid))
        signal = replica*rotation
        if derivatives:
            slope = (b-a)*rotation
            jacobian = np.column_stack((2j*np.pi*(self.t-self.mid)*signal*100,
                -32*(1+ppm*1e-6)*slope,
                32e-6*(self.n-self.epoch-offset)*slope*20))
        normal, rhs, explained, raw = np.zeros((3, 3)), np.zeros(3), 0., 0.
        for k, ix in enumerate(self.frames):
            if subset == 'odd' and k % 2 == 0 or subset == 'even' and k % 2 == 1:
                continue
            s = signal[ix]
            s = s-s.mean()
            y = self.y[ix]-self.raw_sum[k]/len(ix)
            energy = float(np.vdot(s, s).real)
            if energy <= 1e-20:
                continue
            cross = np.vdot(s, y)
            amplitude = cross/energy
            residual = y-amplitude*s
            explained += abs(cross)**2/energy
            raw += self.raw_energy[k]
            if derivatives:
                d = jacobian[ix]
                summed, cross_d = d.sum(axis=0), s.conj() @ d
                # Apply the rank-two DC/gain projection in the 3×3 normal
                # system rather than allocating/projecting another N×3 array.
                gram = d.conj().T @ d - np.outer(summed.conj(), summed)/len(ix)
                gram -= np.outer(cross_d.conj(), cross_d)/energy
                normal += abs(amplitude)**2*gram.real
                rhs += (amplitude.conjugate()*(d.conj().T @ residual)).real
        return dict(score=float(explained/max(raw, 1e-20)), normal=normal, rhs=rhs,
            gradient_score=2*rhs/max(raw, 1e-20), raw_energy=raw)

    def optimize(self, start, center, radius=800., iterations=16):
        parameters = np.asarray(start, float).copy()
        lower = np.array([center-radius, -.75, -40.])
        upper = np.array([center+radius, .75, 40.])
        parameters = np.clip(parameters, lower, upper)
        current = self.statistics(parameters)
        damping, calls, accepted = 1e-3, 1, 0
        history = [dict(parameters=parameters.copy(), score=current['score'])]
        for _ in range(iterations):
            diagonal = np.maximum(np.diag(current['normal']), current['raw_energy']*1e-14)
            improved = False
            for _ in range(6):
                try:
                    step = np.linalg.solve(current['normal']+damping*np.diag(diagonal), current['rhs'])
                except np.linalg.LinAlgError:
                    damping *= 10
                    continue
                # Scaled coordinates: at most 60 Hz, .25 samples or 10 ppm.
                step /= max(1., float(np.max(abs(step)/np.array([.6, .25, .5]))))
                proposed = np.clip(parameters+self.parameter_scale*step, lower, upper)
                # 0.1 Hz, .001 sample and .02 ppm are below the measurement
                # precision being qualified; avoid chasing interpolation knots.
                if np.max(abs((proposed-parameters)/self.parameter_scale)) < 1e-3:
                    break
                candidate = self.statistics(proposed)
                calls += 1
                if candidate['score'] > current['score']+1e-12:
                    parameters, current = proposed, candidate
                    damping = max(1e-8, damping/3)
                    accepted += 1
                    history.append(dict(parameters=parameters.copy(), score=current['score']))
                    improved = True
                    break
                damping *= 10
            if not improved:
                break
        return dict(parameters=parameters, score=current['score'], calls=calls,
            accepted_steps=accepted, history=history)

    def fast_joint_fit(self, center, *, starts=1, iterations=16, radius=800., scout_radius=600.):
        if starts < 1 or iterations < 1 or not 0 < scout_radius <= radius:
            raise ValueError('positive bounded local search required')
        frequencies = center+np.arange(-scout_radius, scout_radius+.1, 100.)
        score = self.evaluate(frequencies)
        f = float(frequencies[int(np.argmax(score))])
        seeds = []
        # Adjacent seeds differ by at most one sample over the full probe.
        rate_step = min(20., 1e6/len(self.y))
        for ppm in np.linspace(-40, 40, int(np.ceil(80/rate_step))+1):
            for offset in (-.5, 0., .5):
                seeds.append((float(self.evaluate([f], offset, ppm)[0]), f, offset, float(ppm)))
        chosen = sorted(seeds, reverse=True)[:starts]
        trials = [self.optimize([f, offset, ppm], center, radius, iterations) for _, f, offset, ppm in chosen]
        best = max(trials, key=lambda r:r['score'])
        f, offset, ppm = best['parameters']
        # Re-evaluate through the reference scorer, independently of the Jacobian.
        exact = float(self.evaluate([f], offset, ppm)[0])
        control = float(self.evaluate([f], offset, ppm, control=True)[0])
        return dict(CFO_hz=float(f), offset_samples=float(offset), modulation_ppm=float(ppm),
            score=exact, control_score=control, margin=exact-control,
            frequency_search_boundary=abs(f-center) >= radius-.5,
            epoch_search_boundary=abs(offset) >= .75-1e-5,
            code_rate_search_boundary=abs(ppm) >= 40-1e-4,
            subset='all', optimizer_calls=sum(t['calls'] for t in trials), seed_count=len(trials),
            optimizer_score_difference=float(best['score']-exact), selected_history=best['history'])
