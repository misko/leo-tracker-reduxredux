"""Four bounded S03 continuations; winner coverage remains the headline."""
from dataclasses import replace
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
MODELS=REPORTS/'2026_10_16_dsx01_models'
PREVIOUS=REPORTS/'2026_10_16_dsx01_iteration2'
sys.path[:0]=[str(MODELS),str(PREVIOUS)]
from common import load_context,refit,measure,endpoint_status,challenge_mask,point_state,save_json
from bank_expansion import fixed_shift
from mixture_model import mixture_density
from peak_data import all_peaks,lane_permutation
from transport import transport
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.shared_scan_model import elevation_geometry,horizon_weight


def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def group_metrics(context,vector,nuisance,group):
    """Posterior satellite mass summed over latent peaks, with no max count."""
    model=context.model;obs=context.observations
    ev,details=model.evaluate_details(vector,nuisance)
    posterior=details['peak_posterior'];responsibility=details['group_responsibilities']
    clutter=details['group_clutter_probability']
    associated=responsibility.max(1)>clutter
    entropy=np.bincount(group,weights=-posterior*np.log(np.maximum(posterior,1e-300)))
    out=dict(groups=len(associated),associated=int(associated.sum()),
        objective=float(ev[0]),likelihood_nll=float(ev[3].nll),
        mean_peak_posterior_entropy=float(entropy.mean()),
        mean_group_clutter_probability=float(clutter.mean()))
    # Fixed endpoint, actual support times, same normalized weights and all physics.
    tau=vector[7]+model.basis@vector[8:]
    prediction=predict_orbits(context.bank,obs,context.prior,vector[:2],tau,derivatives=False)[0]
    prediction+=model.original.correction(vector,nuisance[:model.base_nuisance_count])[:,None]
    visibility=horizon_weight(elevation_geometry(context.bank,obs,context.prior,vector[:2],tau)[0],model.visibility_width)[0]
    sigma,_,q,_,_=model.hyperparameters(nuisance[model.base_nuisance_count:])
    null_obs=lane_permutation(obs)
    null,nd=mixture_density(null_obs.measured_hz,prediction,visibility,sigma,q,model.score,group)
    null_associated=nd['group_responsibilities'].max(1)>nd['group_clutter_probability']
    out['within_lane_time_permutation']=dict(associated=int(null_associated.sum()),
        likelihood_nll=float(null.nll),qualification='Fixed endpoint half-rotation control; not fitted null or calibrated significance')
    return out,associated,null_associated


def run(source_id,arms,methods):
    original=load_context(source_id)
    seed_path=PREVIOUS/'results'/f'{source_id}-fitted-c-profile.json'
    receipt=json.loads(seed_path.read_text())
    manifest=json.loads((PREVIOUS/'manifest.json').read_text())
    binding=next(x for x in manifest['files'] if x['path']==str(seed_path.relative_to(PREVIOUS)))
    if binding['sha256']!=digest(seed_path):raise ValueError('Sealed profile seed changed')
    if receipt['source']['tracking_input_sha256']!=original.source['tracking_input_sha256']:
        raise ValueError('Seed source mismatch')
    seedv=np.asarray(receipt['vector']);seedn=np.asarray(receipt['nuisance'])
    shift=fixed_shift(original.model)
    peaks,group,winner=all_peaks(original,shift)
    with (MODELS.parent/'2026_10_16_dsx01_fast_association_losses'/'membership.csv').open() as stream:
        members=[r for r in csv.DictReader(stream) if r['source_id']==source_id]
    row_lookup={key:i for i,key in enumerate(original.observations.window_ids)}
    window_masks={rid:np.array([row_lookup[r['observation_id']] for r in members if r['region_id']==rid])
        for rid in sorted(set(r['region_id'] for r in members))}
    challenge=challenge_mask(original)
    baseline=(original.vector,original.nuisance)
    seed_group_v,seed_group_n,closure=transport(original.model,peaks.model,seedv,seedn,shift)
    print(json.dumps(dict(stage='prepared',source_id=source_id,groups=len(original.observations.times_s),
        peaks=len(group),calibration_transport=closure)),flush=True)
    for arm in arms:
        v=seedv.copy();n=seedn.copy()
        if arm=='zero-c':v[6]=0.
        pv,pn,forward=transport(original.model,peaks.model,v,n,shift)
        initial_group,_,_=group_metrics(peaks,pv,pn,group)
        for method in methods:
            path=HERE/'results'/f'{source_id}-{arm}-{method}.json'
            if path.exists():continue
            fit_context=original if method=='winner-continuation' else peaks
            fv,fn=(v,n) if method=='winner-continuation' else (pv,pn)
            fit_context=replace(fit_context,fixed_c=arm=='zero-c',deadline=time.monotonic()+120)
            result=refit(fit_context,fv,fn,max_evaluations=1000,max_seconds=120,fixed_c=fit_context.fixed_c)
            x,y=result['vector'],result['nuisance']
            if method=='mixture-continuation':
                ov,on,backward=transport(peaks.model,original.model,x,y,shift)
                mv,mn=x,y
            else:
                ov,on=x,y
                mv,mn,backward=transport(original.model,peaks.model,x,y,shift)
            assert result['diagnostics']['evaluations']<=1000
            metric,ga,na=group_metrics(peaks,mv,mn,group)
            _,_,best,associated,residual=point_state(original.model,ov,on)
            _,_,_,seed_associated,seed_residual=point_state(original.model,v,n)
            windows=[]
            for rid,rows in window_masks.items():
                windows.append(dict(region_id=rid,observations=len(rows),
                    seed_associated=int(seed_associated[rows].sum()),associated=int(associated[rows].sum()),
                    new_vs_seed=int((associated[rows]&~seed_associated[rows]).sum()),
                    lost_vs_seed=int((~associated[rows]&seed_associated[rows]).sum()),
                    mixture_group_associated=int(ga[rows].sum()),
                    permutation_group_associated=int(na[rows].sum())))
            record=dict(source_id=source_id,arm=arm,method=method,mode='full',
                vector=ov,nuisance=on,mixture_vector=mv,mixture_nuisance=mn,
                diagnostics=result['diagnostics'],audit=endpoint_status(fit_context,x,y),
                winner_full_scan=measure(original,ov,on,original=baseline),
                winner_challenge=measure(original,ov,on,original=baseline,mask=challenge),
                winner_vs_seed=measure(original,ov,on,original=(v,n)),
                winner_seed=measure(original,v,n),mixture_group=metric,mixture_group_seed=initial_group,
                windows=windows,group_count=len(original.observations.times_s),peak_count=len(group),
                calibration_transport=dict(seed=forward,endpoint=backward),
                source=original.source,seed=dict(path=str(seed_path),sha256=digest(seed_path),
                    policy='Same complete fixed-bank fitted-profile endpoint; zero-c sets only c to zero before transport'),
                budget=dict(full_objectives=1000,wall_seconds=120,extra_orbit_projection_calls=0),
                code_sha256={name:digest(HERE/name) for name in ['run_pilot.py','mixture_model.py','transport.py','peak_data.py']},
                upstream_code_sha256={str(MODELS/'common.py'):digest(MODELS/'common.py')},
                qualification='Full-data warm development. Winner associations on original fixed observations at 125Hz are primary. '
                'Group latent-peak posterior is separate; no any-peak max is credited. Different observation likelihoods have incomparable raw NLL. '
                'No fitted null; within-lane rotation is only a fixed-endpoint negative control. Configured coordinates are measurement only.')
            path.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(path.with_suffix('.npz'),associated=associated,residual_hz=residual,
                satellite_number=original.bank.numbers[best],times_s=original.observations.times_s,
                group_associated=ga,permutation_group_associated=na,peak_group=group,winner_peak_index=winner)
            save_json(path,record)
            print(json.dumps(dict(stage='fit_complete',source_id=source_id,arm=arm,method=method,
                associated=record['winner_full_scan']['associated'],challenge=record['winner_challenge']['associated'],
                configured_reference_distance_km=record['winner_full_scan'].get('configured_reference_distance_km'),
                group_associated=metric['associated'],null_group_associated=metric['within_lane_time_permutation']['associated'],
                seed_group_associated=initial_group['associated'],seed_null_group_associated=initial_group['within_lane_time_permutation']['associated'],
                evaluations=result['diagnostics']['evaluations'],accepted=record['audit']['accepted'],
                stationarity=record['audit'].get('stationarity'))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default='S03')
    parser.add_argument('--arms',nargs='+',default=['fitted-c','zero-c'],choices=['fitted-c','zero-c'])
    parser.add_argument('--methods',nargs='+',default=['winner-continuation','mixture-continuation'],choices=['winner-continuation','mixture-continuation'])
    args=parser.parse_args();run(args.source,args.arms,args.methods)
