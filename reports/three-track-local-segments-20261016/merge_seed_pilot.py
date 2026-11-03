"""Matched fixed-point test of combining accepted fitted band calibrations."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
import numpy as np

from evaluate import observations,audit
from leo.cli.shared_fast_position import load_input
from leo.application.channel_group_refinement import objective,carried_seed
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.shared_scan_model import CountedObjective
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.regional_position_bank import build_regional_bank
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--attempt',type=Path,required=True);p.add_argument('--tle-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);args=p.parse_args()
if args.output.exists():raise FileExistsError('Use a new pilot receipt')
args.output.mkdir(parents=True,exist_ok=False)
stage=args.attempt/'output/stages'
point_path=stage/'discovery-point:-150:-150.json';row=json.loads(point_path.read_text())
if not all(row['fits'].get(view,{}).get('converged') for view in ['low','high']):
    raise ValueError('Pilot requires accepted independent band fits at the predeclared first point')
preparation=json.loads((stage/'preparation.json').read_text());prior=RegionalPrior(**preparation['prior'])
nodes=np.array(preparation['clock_nodes_s']);receipt=json.loads((args.attempt/'preparation-receipt.json').read_text())
payload=(args.attempt/'training-input.json').read_bytes()
if hashlib.sha256(payload).hexdigest()!=receipt['derived_input_sha256']:raise ValueError('Training input differs')
source=load_input(json.loads(payload));obs=observations(source)
views=dict(all=SimpleNamespace(observations=obs),
    low=SimpleNamespace(observations=observation_subset(obs,np.flatnonzero(obs.channel<=4))),
    high=SimpleNamespace(observations=observation_subset(obs,np.flatnonzero(obs.channel>=5))))
archive=TleArchiveReader(args.tle_root);snapshot=next(s for s in archive.list_snapshots() if s.digest==receipt['tle_sha256'])
catalogue=parse_element_sets(archive.read(snapshot));lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
numbers=json.loads((stage/'bank.json').read_text())['receipt']['retained_numbers']
full,_=build_regional_bank(catalogue,[lookup[n] for n in numbers],source.timing.first_sample_estimate_utc_ns,obs,prior)
if list(map(int,full.numbers))!=numbers:raise ValueError('Regional bank ordering differs')
bank=full.select(row['satellite_indices'])
if list(map(int,bank.numbers))!=row['catalogue_numbers']:raise ValueError('Point candidate ordering differs')
model=objective(views['all'],bank,prior,nodes)
merged=carried_seed(row,[row],model,views,full,prior,nodes,True)
control=row['fits']['all']
result=dict(scope='Predeclared first discovery point only, with fixed position and original observations. Compare another 15s of the original failed combined fit against a seed projected from the accepted fitted low/high correction functions. Matched c=0 and fitted-c refinements are conditional on those same fitted-c band donors. No held values, target membership or identity labels are used; no position accuracy inference.',
    point_sha256=hashlib.sha256(point_path.read_bytes()).hexdigest(),
    derived_input_sha256=receipt['derived_input_sha256'],projection_rms_hz=merged['projection_rms_hz'],
    original_all_stationarity=control['stationarity'],results=[])
for seed_name,seed in [('continue_failed_all',control),('merge_accepted_bands',merged)]:
    for arm in ['fitted-c','zero-c']:
        v=np.array(seed['vector']);n=np.array(seed['nuisance']);begun=time.monotonic()
        options=dict(arm=arm,seconds=15.,iterations=600,fixed_position=True,
                     local_center=v[:2].tolist(),local_radius_km=25.)
        counted=CountedObjective(model,seconds=20.,maximum=1999)
        try:
            fit=fit_group_calibration(counted,v,n,**options);counted.maximum=2000
            checked=audit(counted,fit,options)
        except (ValueError,TimeoutError) as error:
            fit={};checked=dict(accepted=False,reason=str(error),error_type=type(error).__name__)
        elapsed=time.monotonic()-begun
        if elapsed>20:checked.update(accepted=False,reason='20s overall allowance exceeded')
        out=dict(seed=seed_name,arm=arm,options=options,audit=checked,fit=fit,
                 elapsed_seconds=elapsed,actual_objective_calls=counted.calls)
        result['results'].append(out)
        (args.output/(seed_name+'_'+arm+'.json')).write_text(json.dumps(out,indent=2,default=lambda a:a.tolist())+'\n')
        print(json.dumps({k:v for k,v in out.items() if k!='fit'}),flush=True)
(args.output/'summary.json').write_text(json.dumps(result,indent=2,default=lambda a:a.tolist())+'\n')
