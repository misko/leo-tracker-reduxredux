"""Cubic moment correction about the declared mean support time."""
import numpy as np


def correction(values,h,moments):
    fm2,fm1,f0,fp1,fp2=np.asarray(values,float)
    m=np.asarray(moments,float)
    if h<=0 or m.shape!=(4,) or not np.isfinite(m).all() or m[0]!=1 or m[1]!=0:
        raise ValueError('requires finite centered factorial moments')
    second=(fp1-2*f0+fm1)/(h*h)
    third=(fp2-2*fp1+2*fm1-fm2)/(2*h**3)
    return float(m[2]*second+m[3]*third)
