"""Joint raw-IQ receiver-clock likelihood, without transmitter phase continuity.

Two components have independent complex transmitter gains in every frame.
Receiver2 has a fixed complex channel ratio per component and either one
physical clock contrast or two contrasts for a controlled mismatch test.
Carrier, code epoch/rate, ratios, and their full covariance are fitted together.
"""

import numpy as np
from ds23_training_channel_rf import TrainingChannelWorkspace


def conditional_frame_density(source, target, source_basis, target_basis, source_variance, target_variance):
    """Predict target IQ from source IQ, integrating complex source-gain error.

    Both frame DCs are nuisance parameters. The target density is expressed on
    its N-1 dimensional zero-mean subspace. No target signal coefficient is fit.
    """
    ys, yt = np.asarray(source), np.asarray(target)
    bs, bt = np.asarray(source_basis), np.asarray(target_basis)
    if bs.ndim != 2 or bt.ndim != 2 or bs.shape[1] != bt.shape[1] or len(ys) != len(bs) or len(yt) != len(bt):
        raise ValueError('matching source/target IQ and component designs required')
    if min(source_variance, target_variance) <= 0:
        raise ValueError('positive independent raw-IQ noise variances required')
    x = np.column_stack((bs, np.ones(len(bs))))
    coefficient = np.linalg.lstsq(x, ys, rcond=1e-8)[0]
    gain_covariance = source_variance*np.linalg.inv(x.conj().T@x)[:-1, :-1]
    basis = bt-bt.mean(axis=0)
    error = yt-bt@coefficient[:-1]
    error -= error.mean()
    normal = np.linalg.inv(gain_covariance)+basis.conj().T@basis/target_variance
    rhs = basis.conj().T@error/target_variance
    quadratic = float(np.vdot(error, error).real/target_variance
        - np.vdot(rhs, np.linalg.solve(normal, rhs)).real)
    logdet = ((len(yt)-1)*np.log(target_variance)
        + np.linalg.slogdet(normal)[1]+np.linalg.slogdet(gain_covariance)[1])
    nll = quadratic+float(logdet)+(len(yt)-1)*np.log(np.pi)
    return dict(NLL=float(nll), quadratic=quadratic, target_dimensions=len(yt)-1,
        source_coefficients=coefficient, source_gain_covariance=gain_covariance,
        target_residual_energy=float(np.vdot(error, error).real))


class JointReceiverIQ:
    def __init__(self, samples, fs, edge, epochs, segments, noise_variance, *, separate_clocks=False):
        self.y = np.asarray(samples, complex)
        self.epochs = np.asarray(epochs, float)
        self.noise = np.asarray(noise_variance, float)
        if self.y.ndim != 2 or self.y.shape[0] != 2 or self.epochs.shape != (2, 2):
            raise ValueError('two equal-length RX streams and RX-by-component epochs required')
        if self.noise.shape != (2,) or not np.isfinite(self.noise).all() or np.any(self.noise <= 0):
            raise ValueError('two positive training-only raw-IQ noise variances required')
        self.frames = [np.asarray(ix, int) for ix in segments]
        self.parts = [[TrainingChannelWorkspace(self.y[r], fs, edge, self.epochs[r, k], self.frames)
            for k in [0, 1]] for r in [0, 1]]
        self.clock_count = 2 if separate_clocks else 1
        self.code_start = 2+self.clock_count
        self.ratio_start = self.code_start+8
        self.width = self.ratio_start+4
        self.scale = np.r_[np.full(2+self.clock_count, 100.), np.tile([1., 20.], 4), np.ones(4)]
        self.mid = self.parts[0][0].mid
        self.fs = fs
        self.n = np.arange(self.y.shape[1])
        self.raw = sum(float(np.sum(abs(self.y[r, ix]-self.y[r, ix].mean())**2)/self.noise[r])
            for ix in self.frames for r in [0, 1])
        self.used = np.concatenate(self.frames)

    def ratios(self, parameters):
        p = np.asarray(parameters)
        return p[self.ratio_start::2]+1j*p[self.ratio_start+1::2]

    def signals(self, parameters, *, derivatives=False):
        p = np.asarray(parameters, float)
        if p.shape != (self.width,) or not np.isfinite(p).all():
            raise ValueError('finite matching raw-IQ receiver parameters required')
        signals, local_derivatives = [], []
        for r in [0, 1]:
            rx_signals, rx_derivatives = [], []
            for k in [0, 1]:
                frequency = p[k]+(p[2+(k if self.clock_count == 2 else 0)] if r else 0.)
                offset = self.code_start+4*r+2*k
                coordinates = [frequency, p[offset], p[offset+1]]
                values = self.parts[r][k].columns(coordinates, derivatives=derivatives)
                if derivatives:
                    values, derivative = values
                    rx_derivatives.append(np.column_stack([v.sum(axis=1) for v in derivative]))
                rx_signals.append(values.sum(axis=1))
            signals.append(np.column_stack(rx_signals))
            if derivatives:
                local_derivatives.append(rx_derivatives)
        if derivatives:
            return signals, local_derivatives
        return signals

    def statistics(self, parameters, *, derivatives=True, details=False):
        p = np.asarray(parameters)
        if derivatives:
            signals, derivative = self.signals(p, derivatives=True)
        else:
            signals = self.signals(p)
        ratio = self.ratios(p)
        normal, rhs = np.zeros((self.width, self.width)), np.zeros(self.width)
        quadratic = 0.
        coefficients = []
        for ix in self.frames:
            length = len(ix)
            x = np.zeros((2*length, 4), complex)
            x[:length, :2] = signals[0][ix]
            x[length:, :2] = signals[1][ix]*ratio[None]
            x[:length, 2], x[length:, 3] = 1., 1.
            weights = np.repeat(1/np.sqrt(self.noise), length)
            x *= weights[:, None]
            y = np.r_[self.y[0, ix], self.y[1, ix]]*weights
            gram = x.conj().T@x
            coefficient = np.linalg.solve(gram, x.conj().T@y)
            residual = y-x@coefficient
            quadratic += float(np.vdot(residual, residual).real)
            if details:
                coefficients.append(coefficient)
            if derivatives:
                d = np.zeros((2*length, self.width), complex)
                for k in [0, 1]:
                    first = derivative[0][k][ix]*coefficient[k]
                    second = derivative[1][k][ix]*coefficient[k]*ratio[k]
                    d[:length, k] = first[:, 0]
                    d[length:, k] = second[:, 0]
                    d[length:, 2+(k if self.clock_count == 2 else 0)] += second[:, 0]
                    for r, block in [(0, first), (1, second)]:
                        start = self.code_start+4*r+2*k
                        d[r*length:(r+1)*length, start:start+2] = block[:, 1:]
                    z = signals[1][ix, k]*coefficient[k]
                    d[length:, self.ratio_start+2*k] = z
                    d[length:, self.ratio_start+2*k+1] = 1j*z
                d *= weights[:, None]
                projected = d-x@np.linalg.solve(gram, x.conj().T@d)
                normal += (projected.conj().T@projected).real
                rhs += (d.conj().T@residual).real
        result = dict(quadratic=quadratic, score=float(1-quadratic/max(self.raw, 1e-20)),
            normal=normal, rhs=rhs, gradient_quadratic_scaled=-2*rhs,
            raw_energy=self.raw, complex_samples=2*len(self.used), frame_count=len(self.frames))
        if details:
            result['frame_coefficients'] = np.asarray(coefficients)
        return result

    def fit(self, start, *, iterations=30):
        p = np.asarray(start, float).copy()
        if p.shape != (self.width,):
            raise ValueError('matching joint raw-IQ initialization required')
        lower = np.r_[p[:2]-800., p[2:self.code_start]-375., np.tile([-.75, -40.], 4), np.full(4, -5.)]
        upper = np.r_[p[:2]+800., p[2:self.code_start]+375., np.tile([.75, 40.], 4), np.full(4, 5.)]
        p = np.clip(p, lower, upper)
        current = self.statistics(p)
        damping = 1e-3
        history = [dict(parameters=p.copy(), quadratic=current['quadratic'], score=current['score'])]
        calls = 1
        limits = np.r_[np.full(2+self.clock_count, .6), np.tile([.25, .5], 4), np.full(4, .3)]
        for _ in range(iterations):
            diagonal = np.maximum(np.diag(current['normal']), max(self.raw, 1.)*1e-14)
            improved = False
            for _ in range(7):
                step = np.linalg.solve(current['normal']+damping*np.diag(diagonal), current['rhs'])
                step /= max(1., float(np.max(abs(step)/limits)))
                proposed = np.clip(p+self.scale*step, lower, upper)
                if np.max(abs((proposed-p)/self.scale)) < 1e-4:
                    break
                candidate = self.statistics(proposed)
                calls += 1
                if candidate['quadratic'] < current['quadratic']-1e-9:
                    p, current = proposed, candidate
                    history.append(dict(parameters=p.copy(), quadratic=current['quadratic'], score=current['score']))
                    damping = max(1e-8, damping/3)
                    improved = True
                    break
                damping *= 10
            if not improved:
                break
        covariance = np.linalg.pinv(current['normal'], rcond=1e-12)/2
        covariance *= self.scale[:, None]*self.scale[None, :]
        eigenvalues = np.linalg.eigvalsh(current['normal'])
        rank = int(np.sum(eigenvalues > max(float(eigenvalues.max()), 1e-30)*1e-12))
        return dict(parameters=p, score=current['score'], quadratic=current['quadratic'],
            source_carrier_hz=p[:2], receiver_clock_hz=p[2:self.code_start],
            code_coordinates=p[self.code_start:self.ratio_start],
            channel_ratios_real=self.ratios(p).real, channel_ratios_imag=self.ratios(p).imag,
            covariance=covariance, information_rank=rank, normal_eigenvalues=eigenvalues,
            covariance_full_rank=rank == self.width,
            frequency_covariance=covariance[:self.code_start, :self.code_start] if rank == self.width else None,
            boundary=bool(np.any(abs(p-lower) < 1e-4) or np.any(abs(p-upper) < 1e-4)),
            history=history, calls=calls, separate_clocks=self.clock_count == 2,
            covariance_is_conditional_Gaussian_proxy_not_calibrated=True)

    def predict(self, parameters, segments, *, source_receiver=0):
        if source_receiver not in [0, 1]:
            raise ValueError('source receiver0 or1 required')
        held = [np.asarray(ix, int) for ix in segments]
        if np.intersect1d(self.used, np.concatenate(held)).size:
            raise ValueError('held target/source IQ overlaps RF training support')
        signals = self.signals(parameters)
        signals[1] *= self.ratios(parameters)[None]
        target = 1-source_receiver
        frames = [conditional_frame_density(self.y[source_receiver, ix], self.y[target, ix],
            signals[source_receiver][ix], signals[target][ix], self.noise[source_receiver], self.noise[target])
            for ix in held]
        return dict(NLL=float(sum(r['NLL'] for r in frames)),
            quadratic=float(sum(r['quadratic'] for r in frames)),
            target_dimensions=sum(r['target_dimensions'] for r in frames),
            per_frame_NLL=[r['NLL'] for r in frames],
            source_receiver=source_receiver, target_signal_coefficients_not_fit=True)
