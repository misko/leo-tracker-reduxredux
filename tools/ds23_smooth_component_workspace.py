"""Smooth interpolation of the existing, fixed oversampled pilot templates.

This research view keeps samples, frame support, RF coordinates and channel
model unchanged. Periodic cubic interpolation removes artificial derivative
jumps at the original piecewise-linear interpolation knots.
"""

import copy
from functools import lru_cache
import numpy as np
from scipy.interpolate import CubicSpline

from ds23_fractional_differential_phase import isolated_channel_waves
from ds23_joint_component_refinement import JointComponentWorkspace


@lru_cache(maxsize=4)
def periodic_template_spline(fs,edge):
    waves=np.column_stack(isolated_channel_waves(fs,edge))
    return CubicSpline(np.arange(len(waves)+1,dtype=float),np.vstack((waves,waves[0])),
        axis=0,bc_type='periodic',extrapolate='periodic')


class SmoothComponentWorkspace(JointComponentWorkspace):
    @classmethod
    def from_workspace(cls,workspace):
        result=cls.__new__(cls)
        result.__dict__=copy.copy(workspace.__dict__)
        return result

    def columns_and_derivatives(self,parameters,component):
        f,offset,ppm=np.asarray(parameters,float)
        delta=self.n-self.epochs[component]-offset;rate=1+ppm*1e-6
        period=self.fs/750;position=delta*rate
        local=position-np.floor(position/period)*period;fine=32*local
        spline=periodic_template_spline(self.fs,self.edge)
        rotation=np.exp(2j*np.pi*f*self.centered)[:,None]
        columns=spline(fine)*rotation;slope=spline(fine,1)*rotation
        derivatives=np.stack((2j*np.pi*self.centered[:,None]*columns*100,
            -32*rate*slope,32e-6*delta[:,None]*slope*20),axis=2)
        return columns,derivatives
