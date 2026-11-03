"""Audit finite-difference gradients and hard visibility changes in a saved fit."""
import argparse
import json
from pathlib import Path

import numpy as np

from calibration import blocked_folds
from cohort import digest
from numeric_data import load,view


def audit(directory,fold):
    data=load(directory)
    path=directory/'calibration-v2'/f'fold-{fold}.json'
    saved=json.loads(path.read_text())
    data=view(data,blocked_folds(data.times,data.group)!=fold)
    for rx in (0,1):
        mask=data.receiver==rx
        data.measured[mask]-=np.interp(data.times[mask],saved['spline_nodes_s'],saved['correction_knots_hz'][rx])
    from rf_calibration_diagnostic import CalibrationObjective
    from truth_start_diagnostic import projected_gradient
    result=saved['arms']['fitted-c']
    objective=CalibrationObjective(data,np.asarray(result['parameters']),np.asarray(saved['satellite_indices']),False,30.)
    objective.center=saved['rf_center_hz']
    objective.features=((data.rf-objective.center)/1e9)[:,None]
    objective.likelihood.features=objective.features
    objective.base.deadline=float('inf')
    vector=np.asarray(result['vector'])
    bounds=list(objective.bounds)
    bounds[:2]=[(v,v) for v in vector[:2]]
    value,gradient=objective.evaluate(vector)
    projected,_=projected_gradient(vector,gradient,bounds,objective.scale)
    records=[]
    for index in np.argsort(-abs(projected))[:5]:
        for step in (1e-4,1e-5,1e-6):
            delta=np.zeros_like(vector)
            delta[index]=step*objective.scale[index]
            vp=objective.evaluate(vector+delta)[0]
            vm=objective.evaluate(vector-delta)[0]
            _,visible_plus=objective.base.predict((vector+delta)[:objective.size])
            _,visible_minus=objective.base.predict((vector-delta)[:objective.size])
            changed=np.argwhere(visible_plus!=visible_minus)
            records.append(dict(index=int(index),scaled_step=step,analytic_scaled_gradient=float(gradient[index]*objective.scale[index]),
                                finite_difference_scaled_gradient=float((vp-vm)/(2*step)),score_jump=float(vp-vm),
                                visibility_changes=len(changed),changed_matrix_indices=changed.tolist()))
    output=directory/f'calibration-visibility-audit-fold-{fold}.json'
    with output.open('x') as stream:
        json.dump(dict(source_sha256=digest(path.read_bytes()),implementation_sha256=digest(Path(__file__).read_bytes()),
                       objective=float(value),saved_nuisance_gradient=result['nuisance_gradient'],audit=records,
                       interpretation='A non-vanishing score jump with visibility changes invalidates a smooth central-difference comparison at that point. It does not by itself certify a nonsmooth local minimum.'),stream,indent=2)
    print(json.dumps(dict(scan=directory.name,fold=fold,maximum_visibility_changes=max(r['visibility_changes'] for r in records),output=str(output))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--fold',type=int,required=True,choices=range(5))
    a=p.parse_args()
    audit(a.directory,a.fold)
