"""Attach shuffled observations to unchanged archived orbit geometry."""
import copy
import numpy as np


def with_control_observations(data,arrays):
    result=copy.copy(data);n=len(arrays['times_s'])
    fields={'times':'times_s','measured':'measured_hz','rf':'rf_hz','receiver':'receiver','channel':'channel','group':'group'}
    for attribute,key in fields.items():
        value=np.asarray(arrays[key])
        if value.shape!=(n,):raise ValueError('Misaligned control observations')
        setattr(result,attribute,value.copy())
    donor=np.asarray(arrays['source_row'],int)
    if sorted(donor.tolist())!=list(range(len(data.times))):raise ValueError('Control must preserve every source row exactly once')
    result.margin=np.asarray(data.margin)[donor].copy()
    result.original_rows=np.arange(n)
    return result
