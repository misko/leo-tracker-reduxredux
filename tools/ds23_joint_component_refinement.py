"""Joint two-component CFO/epoch/rate estimation without frame continuity.

Seventeen independent complex channel/DC coefficients are profiled at each
guarded frame intersection. Physical derivatives retain fractional frame
placement. Fixed symbol folds assess prediction on other raw samples.
"""

import numpy as np
from ds23_conditional_pilot_components import component_segments
from ds23_fractional_differential_phase import fractional_geometry, isolated_channel_waves


class JointComponentWorkspace:
    scale = np.array([100., 1., 20., 100., 1., 20.])

    def __init__(self, samples, fs, edge, epochs, fits):
        self.y = np.asarray(samples, complex); self.fs = fs; self.edge = edge
        self.epochs = np.asarray(epochs, float); self.n = np.arange(len(self.y)); self.t = self.n/fs
        self.centered = self.t-self.t.mean()
        self.start = np.array([[f['CFO_hz'], f['offset_samples'], f['modulation_ppm']] for f in fits]).ravel()
        a, b = [fractional_geometry(self.y, fs, edge, epoch, fit) for epoch, fit in zip(epochs, fits, strict=True)]
        self.segments = component_segments(a, b); self.symbol = a['symbol']
        if len(self.segments) < 10: raise ValueError('ten supported joint frame intersections required')

    def columns_and_derivatives(self, parameters, component):
        f, offset, ppm = parameters; delta = self.n-self.epochs[component]-offset; rate = 1+ppm*1e-6
        period = self.fs/750; position = delta*rate; local = position-np.floor(position/period)*period
        fine = local*32; index = np.floor(fine).astype(np.int64); fraction = fine-index
        waves = isolated_channel_waves(self.fs, self.edge)
        left = np.column_stack([w[index % len(w)] for w in waves])
        right = np.column_stack([w[(index+1) % len(w)] for w in waves])
        rotation = np.exp(2j*np.pi*f*self.centered)[:, None]
        columns = (left+(right-left)*fraction[:, None])*rotation; slope = (right-left)*rotation
        derivatives = np.stack((2j*np.pi*self.centered[:, None]*columns*100,
                                -32*rate*slope, 32e-6*delta[:, None]*slope*20), axis=2)
        return columns, derivatives

    def statistics(self, parameters, parity=None, derivatives=True, prediction=False):
        parameters = np.asarray(parameters).reshape(2, 3)
        (a, da), (b, db) = [self.columns_and_derivatives(v, k) for k, v in enumerate(parameters)]
        design = np.column_stack((a, b, np.ones(len(self.y))))
        normal, rhs, error, raw, count = np.zeros((6, 6)), np.zeros(6), 0., 0., 0
        heldout_error, heldout_raw, heldout_count = 0., 0., 0
        for segment in self.segments:
            ix = segment if parity is None else segment[self.symbol[segment] % 2 == parity]
            if len(ix) < 25: continue
            x, y = design[ix], self.y[ix]; coef, _, rank, _ = np.linalg.lstsq(x, y, rcond=1e-8)
            if rank != 17: raise ValueError('joint component model lost channel rank')
            residual = y-x@coef; error += float(np.vdot(residual, residual).real)
            raw += float(np.vdot(y, y).real); count += len(ix)
            if derivatives:
                d = np.column_stack((np.einsum('nij,i->nj', da[ix], coef[:8]),
                                     np.einsum('nij,i->nj', db[ix], coef[8:16])))
                q, _ = np.linalg.qr(x, mode='reduced'); projected = d-q@(q.conj().T@d)
                normal += (projected.conj().T@projected).real
                rhs += (d.conj().T@residual).real
            if prediction:
                if parity is None: raise ValueError('prediction requires a disjoint symbol fold')
                test = segment[self.symbol[segment] % 2 != parity]
                r = self.y[test]-design[test]@coef
                heldout_error += float(np.vdot(r, r).real)
                heldout_raw += float(np.vdot(self.y[test], self.y[test]).real); heldout_count += len(test)
        if count <= 17*len(self.segments): raise ValueError('insufficient joint training samples')
        return dict(score=1-error/raw, squared_error=error, raw_energy=raw, samples=count,
                    normal=normal, rhs=rhs, gradient_score=2*rhs/raw,
                    heldout_squared_error=heldout_error, heldout_raw_energy=heldout_raw, heldout_samples=heldout_count)

    def optimize(self, parity=None, active=(0, 1, 2, 3, 4, 5), iterations=12):
        parameters = self.start.copy(); active = np.asarray(active)
        lower = self.start.copy(); upper = self.start.copy()
        lower[[0, 3]] -= 120; upper[[0, 3]] += 120
        lower[[1, 4]] = -.75; upper[[1, 4]] = .75; lower[[2, 5]] = -40; upper[[2, 5]] = 40
        current = self.statistics(parameters, parity); calls, damping = 1, 1e-3
        history = [dict(parameters=parameters.copy(), score=current['score'])]
        for _ in range(iterations):
            normal = current['normal'][np.ix_(active, active)]; rhs = current['rhs'][active]
            diagonal = np.maximum(np.diag(normal), current['raw_energy']*1e-14); improved = False
            for _ in range(5):
                step = np.zeros(6); step[active] = np.linalg.solve(normal+damping*np.diag(diagonal), rhs)
                step /= max(1., float(np.max(abs(step)/np.array([.6, .25, .5, .6, .25, .5]))))
                proposed = np.clip(parameters+self.scale*step, lower, upper)
                if np.max(abs((proposed-parameters)/self.scale)) < 1e-3: break
                candidate = self.statistics(proposed, parity); calls += 1
                if candidate['score'] > current['score']+1e-12:
                    parameters, current = proposed, candidate; damping = max(1e-8, damping/3)
                    history.append(dict(parameters=parameters.copy(), score=current['score'])); improved = True; break
                damping *= 10
            if not improved: break
        return dict(parameters=parameters, score=current['score'], calls=calls, history=history,
                    boundary=bool(np.any(parameters <= lower+1e-5) or np.any(parameters >= upper-1e-5)))
