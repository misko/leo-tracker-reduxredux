"""Bounded candidate-only GLRT refinement; score callback has no orbit input."""
import math

ALIAS=1/4.4e-6
def circular(x):
    return (x+ALIAS/2)%ALIAS-ALIAS/2

def refine(score,frequency,epoch,iterations=3):
    """Compare three lifts, recenter, then refine epoch on shrinking grids.

    The callback recomputes raw-IQ correlations and searches the GLRT residual
    grid. Reject maxima more than 1 kHz circularly from the requested center.
    No merging, signal subtraction, or forced orbit alignment occurs here.
    """
    if not math.isfinite(frequency) or not math.isfinite(epoch):raise ValueError('Nonfinite seed')
    trace=[];best=None;calls=0
    for it in range(iterations):
        trials=[]
        centers=[frequency+k*ALIAS for k in (-1,0,1)] if it==0 else [frequency]
        offsets=[0.] if it==0 else [-.5/it,-.25/it,0.,.25/it,.5/it]
        for center in centers:
            for offset in offsets:
                value=dict(score(center,epoch+offset));calls+=1
                if abs(circular(value['tracking_cfo_hz']-center))>1000:continue
                value.update(center_hz=center,epoch=epoch+offset)
                trials.append(value)
        if best is not None:trials.append(best)
        if not trials:return dict(status='no_local_maximum',trace=trace,calls=calls)
        best=max(trials,key=lambda r:r['margin'])
        trace.append(dict(best));frequency=best['tracking_cfo_hz'];epoch=best['epoch']
    return dict(status='refined',trace=trace,calls=calls,**best)
