"""Bounded, separately saved numerical polish of frozen calibration fits.

Reconstruct each saved training fold and its unchanged nonlinear RX correction.
This does not retrain the spline, change associations, or replace source folds.
Any success is conditional on that saved spline, not validation of its training.
"""
import argparse
import inspect
import json
from pathlib import Path

import numpy as np
from calibration import blocked_folds
from cohort import digest
from fisher_position import fit
from numeric_data import load,view


def verify_reconstruction(value,saved):
    if not np.isfinite(value) or abs(value-saved)>1e-6:
        raise ValueError('saved calibration objective does not reconstruct')


def run(directory,fold):
    source=directory/'calibration-v2'/f'fold-{fold}.json'
    saved=json.loads(source.read_text())
    data=load(directory)
    for path,expected in data.sources.items():
        if saved['signature']['observations'].get(path)!=expected:
            raise ValueError('calibration inputs changed')
    data=view(data,blocked_folds(data.times,data.group)!=fold)
    for rx in (0,1):
        mask=data.receiver==rx
        data.measured[mask]-=np.interp(data.times[mask],saved['spline_nodes_s'],saved['correction_knots_hz'][rx])
    from rf_calibration_diagnostic import CalibrationObjective
    from timing_model import TimingObjective
    paths=[Path(__file__),Path(inspect.getfile(fit)),Path(inspect.getfile(CalibrationObjective)),Path(inspect.getfile(TimingObjective))]
    signature=dict(source=str(source),source_sha256=digest(source.read_bytes()),
                   implementation={str(p):digest(p.read_bytes()) for p in paths},budget_s=30.,scope=__doc__)
    root=directory/'calibration-polish-v1';root.mkdir(exist_ok=True)
    for arm in ('fitted-c','zero-c'):
        target=root/f'fold-{fold}-{arm}.json'
        if target.exists():
            if json.loads(target.read_text())['signature']!=signature:raise ValueError('polish signature mismatch')
            continue
        original=saved['arms'][arm]
        objective=CalibrationObjective(data,np.asarray(original['parameters']),np.asarray(saved['satellite_indices']),False,30.)
        objective.center=saved['rf_center_hz'];objective.features=((data.rf-objective.center)/1e9)[:,None]
        objective.likelihood.features=objective.features
        objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
        objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
        if arm=='zero-c':objective.bounds[-1]=(0.,0.)
        objective.base.deadline=float('inf')
        vector=np.asarray(original['vector'])
        value,_=objective.evaluate(vector);verify_reconstruction(value,original['objective'])
        result=fit(objective,vector,[0.,0.],30.,True)
        with target.open('x') as stream:
            json.dump(dict(signature=signature,original_objective=value,result=result),stream,indent=2,allow_nan=False)
        print('CALIBRATION POLISH',directory.parent.name,fold,arm,value,result['objective'],result['success'],result['kkt_residual'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--fold',required=True,type=int,choices=range(5))
    a=p.parse_args();run(a.directory,a.fold)
