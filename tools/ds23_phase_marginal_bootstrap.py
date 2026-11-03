"""Paired physical-frame bootstrap weights for the phase-marginal RF model."""

import numpy as np
from ds23_phase_marginal_iq import PhaseMarginalIQ


class FrameResampledPhaseIQ(PhaseMarginalIQ):
    def __init__(self,*args,draw_indices,**kwargs):
        super().__init__(*args,**kwargs)
        draw=np.asarray(draw_indices)
        if draw.ndim!=1 or not np.issubdtype(draw.dtype,np.integer) or len(np.unique(draw))<4:
            raise ValueError('at least four distinct integer paired-frame indices required')
        if np.any(draw<0) or np.any(draw>=len(self.frames)):
            raise ValueError('bootstrap frame indices outside physical support')
        original=list(self.frames);self.frames=[original[k] for k in draw]
        self.used=np.concatenate(self.frames);self.bootstrap_indices=draw.copy()
