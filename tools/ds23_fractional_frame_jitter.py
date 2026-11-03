"""Separate genuinely irregular frame timing from rounded-template artifacts."""

import numpy as np

from decoupled_pilot_clocks import isolated_pilot_wave
from ds23_frame_timing_jitter import FrameJitterWorkspace
from probe_native_code_carrier import interpolate_periodic


class FractionalFrameJitterWorkspace(FrameJitterWorkspace):
    def __init__(self, samples, fs, edge, epoch):
        super().__init__(samples, fs, edge, epoch)
        self.wave = isolated_pilot_wave(fs, edge)
        self.control = isolated_pilot_wave(fs, edge, True)

    def replica(self, offset=0., ppm=0., control=False):
        position = (self.n-self.epoch-offset)*(1+ppm*1e-6)
        local = position-np.floor(position/self.period)*self.period
        return interpolate_periodic(self.control if control else self.wave, local*32)

    def signal_and_derivatives(self, parameters, control=False):
        f, offset, ppm = parameters[:3]; jitter = np.asarray(parameters[3:])
        if jitter.shape != (len(self.frames),):
            raise ValueError('one jitter per original guarded frame required')
        labels = np.clip(np.floor((self.n-self.epoch)/self.period).astype(int), 0, len(jitter)-1)
        delta = self.n-self.epoch-offset-jitter[labels]; a = 1+ppm*1e-6
        position = delta*a
        position = (position-np.floor(position/self.period)*self.period)*32
        index = np.floor(position).astype(np.int64); fraction = position-index
        wave = self.control if control else self.wave
        left, right = wave[index % len(wave)], wave[(index+1) % len(wave)]
        rotation = np.exp(2j*np.pi*f*(self.t-self.mid))
        signal = (left+(right-left)*fraction)*rotation; slope = (right-left)*rotation
        derivative = np.column_stack((2j*np.pi*(self.t-self.mid)*signal*100,
                                      -32*a*slope, 32e-6*delta*slope*20))
        return signal, derivative, -.1*32*a*slope

    def statistics(self, parameters, subset='all', derivatives=True):
        if subset != 'all':
            from ds23_frame_timing_jitter import restrict_samples
            # Legacy named subsets are whole frames. Timing validation uses
            # explicit disjoint samples through restrict_samples instead.
            raise ValueError('fractional jitter baseline requires explicit sample support')
        result = self.jitter_statistics(np.r_[parameters, np.zeros(len(self.frames))], .15)
        factor = result['residual_energy']/result['sample_count']/2
        normal = result['normal'][:3, :3]*factor; rhs = result['rhs'][:3]*factor
        return dict(score=result['score'], normal=normal, rhs=rhs, raw_energy=result['raw_energy'],
                    gradient_score=2*rhs/max(result['raw_energy'], 1e-20))
