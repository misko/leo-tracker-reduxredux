import numpy as np


def shifted_track(track,before,after,candidate):
    delta=np.asarray(after[candidate])-np.asarray(before[candidate])
    if delta.shape!=np.asarray(track['y']).shape or not np.all(np.isfinite(delta)):
        raise ValueError('Invalid frequency displacement')
    y=np.asarray(track['y'])+delta
    return dict(track,y=y,measured_hz=y.copy())
