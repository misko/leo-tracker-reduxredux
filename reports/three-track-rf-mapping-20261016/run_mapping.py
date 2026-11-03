"""Bounded matched RF-mapping controls over existing cold-training observations."""
import argparse,hashlib,json,sys,time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-coordinate-timing-20261016'))
sys.path.insert(0,str(HERE.parent/'three-track-joint-band-recalibration-20261016'))
from run import context,profile
from evaluate import audit,observations,classify_frozen_endpoint
from band_transport import unfreeze,freeze
from rf_mapping import MODES,remap,calibration_seed
from leo.application.channel_group_refinement import objective
from leo.analysis.shared_scan_model import SmoothVisibilityModel,CountedObjective
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.cli.shared_fast_position import load_input


def run(args):
    if args.output.exists():raise FileExistsError('Use a new mapping-control namespace')
    ctx=context(args);parent=json.loads(args.parent.read_text())
    if parent['arm']!=args.arm or not parent['audit']['accepted'] or not parent['profile']['complete']:
        raise ValueError('Matching accepted complete timing-search donor required')
    for name,digest in parent['source_sha256'].items():
        if hashlib.sha256((HERE.parent/'three-track-coordinate-timing-20261016'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Executed timing source differs')
    checked=audit(ctx.model,parent['fit'],parent['options'])
    if not checked['accepted'] or abs(checked['objective']-parent['audit']['objective'])>1e-7:
        raise ValueError('Parent endpoint fails original replay')
    if parent['derived_input_sha256']!=ctx.derivation['derived_input_sha256']:raise ValueError('Parent training inventory differs')
    tuning_payload=args.tuning.read_bytes();record=json.loads(tuning_payload);targets=record['configuration']['targets']
    remap(ctx.obs,targets,'recorded')  # Check tuning evidence before creating the attempt.
    args.output.mkdir(parents=True,exist_ok=False)
    result=dict(arm=args.arm,parent_sha256=hashlib.sha256(args.parent.read_bytes()).hexdigest(),
        derived_input_sha256=ctx.derivation['derived_input_sha256'],tuning_sha256=hashlib.sha256(tuning_payload).hexdigest(),
        source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ['rf_mapping.py','run_mapping.py']},
        recorded_targets=targets,calibration_id=record['configuration'].get('calibration_id'),cases=[],
        scope='Conditional RF-mapping controls, not hardware identification. Same training observations, measured CFO, candidate bank, priors, initial physical receiver correction, all-candidate timing grid and budgets across recorded/static-9750/static-10600 hypotheses. Both RF arms use their corresponding matched timing-search donor. No target membership or held CFO enters fitting. Bank retained from recorded-RF cold discovery; alternative maps do not receive fresh full-regional discovery. Spatial continuation remains the same original 25km disk. Receiver-specific alternative LO combinations are not tested. No independent identity or position truth.')
    snapshots=[]
    for mode in MODES:
        folder=args.output/mode;folder.mkdir(exist_ok=False);started=time.monotonic()
        obs=remap(ctx.obs,targets,mode)
        joint=objective(SimpleNamespace(observations=obs),ctx.bank,ctx.prior,ctx.nodes)
        free=SmoothVisibilityModel(joint,np.ones(len(obs.times_s),bool))
        v,n,carry=calibration_seed(ctx.model,parent['fit'],joint)
        frozen,seed,shift,transport=freeze(free,dict(vector=v,nuisance=n))
        local=SimpleNamespace(model=frozen,fit=seed,obs=obs,bank=ctx.bank,prior=ctx.prior)
        v,n,sweep=profile(local,args.arm,folder)
        row=dict(mode=mode,calibration_transport=carry,initial_freeze_transport=transport,
            profile=sweep,fit={},audit=dict(accepted=False,reason='Incomplete timing sweep'))
        (folder/'profile.json').write_text(json.dumps(dict(vector=v,nuisance=n,**sweep),indent=2,default=lambda a:a.tolist())+'\n')
        if sweep['complete']:
            training,vv,nn,unfreeze_proof=unfreeze(frozen,dict(vector=v,nuisance=n),shift,joint)
            row['unfreeze_transport']=unfreeze_proof
            options=dict(parent['options'],arm=args.arm,seconds=60.,iterations=600)
            counted=CountedObjective(training,seconds=65.,maximum=4999);fit_started=time.monotonic()
            try:
                fitted=fit_group_calibration(counted,vv,nn,**options);counted.maximum=5000
                checked=audit(counted,fitted,options)
                row.update(fit=fitted,audit=checked,options=options)
            except (ValueError,TimeoutError) as error:
                row['audit']=dict(accepted=False,reason=str(error),error_type=type(error).__name__)
            row['fit_elapsed_seconds']=time.monotonic()-fit_started
            row['actual_objective_calls']=counted.calls
            if row['fit_elapsed_seconds']>65:row['audit'].update(accepted=False,reason='65s total allowance exceeded')
            if row['fit']:
                prediction_model,prediction_fit,prediction_shift,closure=freeze(training,row['fit'])
                row['prediction_transport']=closure
                snapshots.append((row,prediction_model,prediction_fit,prediction_shift))
        row['elapsed_seconds']=time.monotonic()-started
        result['cases'].append(row)
        (folder/'case.json').write_text(json.dumps(row,indent=2,default=lambda a:a.tolist())+'\n')
        print(json.dumps(dict(event='mapping-fit-complete',arm=args.arm,mode=mode,
            audit=row['audit'],profile_complete=sweep['complete'],elapsed_seconds=row['elapsed_seconds'])),flush=True)
    accepted=[r for r in result['cases'] if r['audit']['accepted']]
    result['training_selected_mapping']=min(accepted,key=lambda r:(r['audit']['objective'],r['mode']))['mode'] if accepted else None
    # Select using training only before loading any original held CFO values.
    payload=args.input.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=ctx.derivation['parent_input_sha256']:raise ValueError('Original evaluation input differs')
    full=observations(load_input(json.loads(payload)))
    for row,model,fit,shift in snapshots:
        row['pipeline_classification']=classify_frozen_endpoint(model,fit,shift,remap(full,targets,row['mode']),ctx.derivation,ctx.nodes)
        (args.output/row['mode']/'case.json').write_text(json.dumps(row,indent=2,default=lambda a:a.tolist())+'\n')
    (args.output/'result.json').write_text(json.dumps(result,indent=2,default=lambda a:a.tolist())+'\n')
    print(json.dumps(dict(arm=args.arm,training_selected_mapping=result['training_selected_mapping'],
        cases=[dict(mode=r['mode'],audit=r['audit'],tracks=[{k:t[k] for k in ['track','training_satellite','test_matches_training_satellite','test_count','test_rms_hz']} for t in r.get('pipeline_classification',{}).get('tracks',[])]) for r in result['cases']])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['attempt','parent','tle-root','input','tuning','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--arm',choices=['fitted-c','zero-c'],required=True);run(p.parse_args())
