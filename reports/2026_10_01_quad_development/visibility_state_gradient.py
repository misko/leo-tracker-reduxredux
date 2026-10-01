"""Linear-memory association-weight gradients for scan clocks and satellite epochs."""
import numpy as np
from shared_threshold_weights import shared_log_weights


def weight_components(margins,geometry_jacobian,width_deg,signal_mass):
    logs,reduced,info=shared_log_weights(margins,geometry_jacobian,width_deg,signal_mass)
    if reduced is None:raise ValueError('visibility minimum has nondifferentiable tie')
    if reduced.shape[1]!=3:raise ValueError('geometry columns must be east, north, time')
    background_epochs=-np.exp(logs[:-1]-logs[-1])*reduced[:-1,2]
    return logs,reduced,background_epochs


def selected_weight_gradient(components,index):
    logs,reduced,epochs=components;count=len(epochs)
    if not isinstance(index,(int,np.integer)) or not 0<=index<=count:raise ValueError('invalid branch index')
    result=np.zeros(5+count);result[:3]=reduced[index]
    if index==count:result[5:]=epochs
    else:result[5+index]=reduced[index,2]
    return result
