"""Row-restricted joint likelihood with the original physical constraint port.

No fitting, model constructors, storage, references or new persisted contract.
The inherited full-data model is explicit conditioning, not independent validation.
"""
import copy

import numpy as np

from leo.contracts.regional_position import PositionObservations
from leo.analysis.hard60_slope_prior import SlopePrior

FIELDS = ('times_s','measured_hz','rf_hz','receiver','channel','margin')
ROW_ARRAYS = ('baseline','design','clock_design','delta_time','rf_time_design')


class RowObjective:
    """Expose full observation metadata to constraints; score only selected rows.

    _Problem uses full min/max times through this object's observations. The
    delegate uses sliced observations and unchanged precomputed design columns.
    Callers must use selected_observations for training-count reporting.
    """
    def __init__(self, full_model, indices):
        if type(full_model) is not SlopePrior:
            raise ValueError('only the inspected SlopePrior layout is supported')
        rows = np.asarray(indices)
        n = len(full_model.observations.window_ids)
        if (rows.ndim != 1 or len(rows)==0 or rows.dtype.kind not in 'iu'
                or np.any(rows<0) or np.any(rows>=n) or np.any(rows[1:]<=rows[:-1])):
            raise ValueError('nonempty unique increasing original row indices required')
        rows = np.array(rows,dtype=int,copy=True); rows.setflags(write=False)
        original = full_model.observations
        observations = PositionObservations(tuple(original.window_ids[i] for i in rows),
            **{name:getattr(original,name)[rows] for name in FIELDS})
        delegate = copy.copy(full_model)
        delegate.observations = observations
        for name in ROW_ARRAYS:
            source = np.asarray(getattr(full_model,name))
            if source.ndim<1 or len(source)!=n or not np.isfinite(source).all():
                raise ValueError('invalid full row array: '+name)
            selected = source[rows].copy(); selected.setflags(write=False)
            setattr(delegate,name,selected)
        self.full_model = full_model
        self.selected_observations = observations
        self.rows = rows
        self._delegate = delegate

    def __getattr__(self,name):
        value = getattr(self.full_model,name)
        if callable(value):
            raise AttributeError('only the explicit joint evaluation port is subset-safe')
        return value

    def evaluate_joint(self,vector,clock):
        return self._delegate.evaluate_joint(vector,clock)

    def evaluate(self,*args,**kwargs):
        raise TypeError('row restriction supports the joint objective only')


def prior_terms(model, vector, clock):
    """Independent explicit original prior, for decomposition audits only."""
    relative = model.basis @ vector[8:]
    value = .5*(vector[7]/model.score.common_sigma_s)**2
    value += .5*np.sum((relative/model.score.relative_sigma_s)**2)
    value += .5*clock@model.precision@clock
    physical = np.zeros(model.size)
    physical[7] = vector[7]/model.score.common_sigma_s**2
    physical[8:] = model.basis.T@relative/model.score.relative_sigma_s**2
    return float(value), physical, model.precision@clock
