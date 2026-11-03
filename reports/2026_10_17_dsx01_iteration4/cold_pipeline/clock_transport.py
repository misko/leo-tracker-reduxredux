"""Prediction-only constant boundary extension of learned residual clocks."""
from dataclasses import replace
import numpy as np
from leo.analysis.sequential_group_calibration import FrozenSequentialCalibration


def extend_frozen_clock(calibration,minimum_s,maximum_s):
    """Extend residual knots constantly; preserve every learned affine term."""
    if not np.isfinite([minimum_s,maximum_s]).all() or minimum_s>maximum_s:
        raise ValueError('Finite ordered evaluation domain required')
    common=calibration.common;nodes=common.clock_nodes_s
    if not len(nodes):return calibration
    expanded=nodes.copy();knots=common.clock_knots_hz.copy();group=common.group_clock_knots_hz.copy()
    if minimum_s<nodes[0]:
        expanded=np.r_[minimum_s,expanded]
        knots=np.column_stack([knots[:,0],knots]);group=np.column_stack([group[:,0],group])
    if maximum_s>nodes[-1]:
        expanded=np.r_[expanded,maximum_s]
        knots=np.column_stack([knots,knots[:,-1]]);group=np.column_stack([group,group[:,-1]])
    extended=replace(common,clock_nodes_s=expanded,clock_knots_hz=knots,group_clock_knots_hz=group)
    return FrozenSequentialCalibration(extended,calibration.shift)
