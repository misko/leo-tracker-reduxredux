"""Pilot workspaces restricted to explicitly supplied physical IQ samples."""

import numpy as np
from decoupled_pilot_clocks import ContinuousCoupledWorkspace


def restricted_workspace(samples,fs,edge,epoch,segments):
    ws=ContinuousCoupledWorkspace(samples,fs,edge,epoch)
    frames=[np.asarray(ix,int) for ix in segments]
    if len(frames)<4 or any(len(ix)<40 for ix in frames):raise ValueError('four supported native training segments required')
    joined=np.concatenate(frames)
    if len(joined)!=len(np.unique(joined)) or np.any(joined<0) or np.any(joined>=len(samples)):
        raise ValueError('training segments must be disjoint and inside the saved IQ')
    ws.frames=frames
    ws.raw_sum=[ws.y[ix].sum() for ix in frames]
    ws.raw_energy=[float(np.sum(abs(ws.y[ix])**2)-abs(ws.y[ix].sum())**2/len(ix)) for ix in frames]
    return ws
