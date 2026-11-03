"""Whole paired-frame resampling for a joint-IQ RF uncertainty diagnostic."""

import numpy as np
from ds23_joint_receiver_iq import JointReceiverIQ


class FrameResampledJointIQ(JointReceiverIQ):
    """Repeat complete observed blocks as bootstrap weights, never new evidence."""

    def __init__(self, samples, fs, edge, epochs, segments, noise_variance, draw_indices):
        super().__init__(samples, fs, edge, epochs, segments, noise_variance)
        draw = np.asarray(draw_indices)
        if draw.ndim != 1 or not np.issubdtype(draw.dtype, np.integer) or len(draw) < 4:
            raise ValueError('integer paired-frame resampling indices required')
        if np.any(draw < 0) or np.any(draw >= len(segments)) or len(np.unique(draw)) < 4:
            raise ValueError('at least four distinct valid physical frames required')
        original = list(self.frames)
        self.frames = [original[k] for k in draw]
        self.used = np.concatenate(self.frames)
        self.raw = sum(float(np.sum(abs(self.y[r, ix]-self.y[r, ix].mean())**2)/self.noise[r])
            for ix in self.frames for r in [0, 1])
        self.bootstrap_indices = draw.copy()
