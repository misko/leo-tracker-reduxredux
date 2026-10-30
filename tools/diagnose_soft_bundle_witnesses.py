"""Target-excluded descriptive witnesses at immutable matched-control endpoints."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from predictive_graph_bundle import bundle_context,validated_bundle_context
from predictive_label_mixture import LabelMixture,SharedComponent
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from investigate_ds23_0268_remaining_tracks import family_frequency
from phase_reference_checks import reference_domain
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from residual_witness_prediction import predict


def disjoint_witnesses(witnesses,target_ids):
    """Reject whole witnesses sharing even one physical observation with target."""
    target=set(target_ids);kept=[];excluded=[]
    for w in witnesses:
        if 'observation_ids' not in w:raise ValueError('witness observation provenance required')
        overlap=target.intersection(w['observation_ids'])
        if overlap:excluded.append(dict(component=w['component'],shared_observation_ids=sorted(overlap)))
        else:kept.append(w)
    return kept,excluded


def transfer(target,witnesses):
    rows=[];r=np.asarray(target['residual_hz']);t=np.asarray(target['times_s'])
    for relation in ('same_receiver','same_receiver_band','other_receiver','same_satellite','same_satellite_other_receiver'):
        selected=[w for w in witnesses if w['receiver']!=target['receiver']] if relation=='same_satellite_other_receiver' else witnesses
        actual='same_satellite' if relation=='same_satellite_other_receiver' else relation
        for width in (3.,6.,12.):
            for scaling in ('hz','fractional'):
                pr=predict(target,selected,width_s=width,relation=actual,scaling=scaling,minimum_families=1 if actual=='same_satellite' else 2)
                residual=r-pr['prediction_hz'];covered=np.asarray(pr['qualified']);noise={k:v[0].item() for k,v in batch_noise_screen(residual[None],t).items()}
                correlation=None
                if covered.sum()>=4 and np.std(r[covered])>0 and np.std(pr['prediction_hz'][covered])>0:
                    correlation=float(np.corrcoef(r[covered],pr['prediction_hz'][covered])[0,1])
                rows.append(dict(relation=relation,width_s=width,scaling=scaling,supported_points=int(covered.sum()),points=len(t),
                    baseline_RMS_hz=float(np.sqrt(np.mean(r*r))),corrected_RMS_hz=float(np.sqrt(np.mean(residual**2))),
                    supported_baseline_RMS_hz=float(np.sqrt(np.mean(r[covered]**2))) if covered.any() else None,
                    supported_corrected_RMS_hz=float(np.sqrt(np.mean(residual[covered]**2))) if covered.any() else None,
                    correlation_on_supported=correlation,noise_after=noise,residual_after_hz=residual,**pr))
    return rows


def collect(p,x,entries):
    c=p.calculate(x);approx,_=p.conditional_frequency(x);phase=p.state(x)['phases'];tracks=[];unavailable=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=p.keep[sl]
        if active.sum()<4:continue
        track=p.scan.tracks[i];j=row['candidate_index'];times=track['times'][active]
        domain=reference_domain(p.sky['time_s'],times,np.zeros(len(times),int),[phase[j]],padding_s=0)
        if not domain['in_domain']:unavailable.append(dict(component=track['key'],domain=domain));continue
        f,e=family_frequency(p,x,j,times=times)
        residual=c['conditional_residual_hz'][sl][active]-p.q[sl][active]*(f-approx[sl][active])
        tracks.append(dict(component=track['key'],norad=row['candidate_norad'],receiver=track['receiver'],channel=track['channel'],
            rf_hz=track['rf_hz'],times_s=times,residual_hz=residual,minimum_elevation_deg=float(e.min()),
            observation_ids=np.asarray(track['observation_ids'])[active],role='curved_calibration'))
    for entry in entries:
        i=entry['track_index'];track=p.scan.tracks[i];j=entry['candidate_index'];times=track['times']
        domain=reference_domain(p.sky['time_s'],times,np.zeros(len(times),int),[phase[j]],padding_s=0)
        if not domain['in_domain']:unavailable.append(dict(component=track['key'],domain=domain));continue
        view,y,*_=linear_geometry(p,[entry]);g=geometry_features(view,x,0.);begin=p.hardware.shape[1]+p.smooth.shape[1]
        f,e=family_frequency(p,x,j,times=times);raw=y-g['features'][:,:begin]@c['coefficient'][:begin]-view.q*f
        terms=profile(raw,np.zeros(len(times)),*p.scan.white[i],bias_sigma=300.)
        tracks.append(dict(component=track['key'],norad=entry['norad'],receiver=track['receiver'],channel=track['channel'],
            rf_hz=track['rf_hz'],times_s=times,residual_hz=terms['residual'][0],minimum_elevation_deg=float(e.min()),
            observation_ids=track['observation_ids'],role='incumbent_predictive',profile_bias_hz=float(terms['bias'][0])))
    return tracks,unavailable


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);pr=read(args.trial/'protocol.json');inv=read(args.inventory);d=context(inv)
    shared=args.shared
    if shared:
        if len(pr.get('graph_bundle_sources',[]))!=1 or len(pr['targets'])!=1:raise ValueError('one validated shared graph bundle required')
        d,target=validated_bundle_context(d,inv,Path(pr['graph_bundle_sources'][0]));entry=pr['targets'][0]
        if entry['track_index']!=target['track_index'] or entry['observation_ids']!=target['observation_ids']:raise ValueError('shared target geometry mismatch')
        candidates=[dict(norad=entry['norad'],aliases=[entry['alias']])];mixture=None
    else:
        d,target=bundle_context(d,inv,Path(pr['target']['bundle_source']),pr['target']['track_id']);candidates=pr['candidates']
        mixture=LabelMixture(d,target,candidates,.025,args.phase_limit)
    control=read(args.trial/'control.json');track=d['scan'].tracks[target['track_index']];results=[]
    write(args.output/'protocol.json',dict(job=inv['job'],candidates=candidates,target=target,shared_identity=shared,
        primary=dict(relation='same_receiver',width_s=6.,scaling='hz',minimum_families=2),
        all_variants_predeclared=True,phase_step_s=.025,phase_limit_s=args.phase_limit,positions_and_receiver_fits_frozen=True,
        target_absent_from_control_likelihood=True,full_fit_witnesses_not_independent_holdout=True,
        no_target_fitted_correction=True,GPS_used=False,future_TLE=False,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.trial/'protocol.json',args.trial/'control.json')}))
    for arm,v in control['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km'])
        difference=p.calculate(x)['negative_twice_elbo']-v['negative_twice_elbo']
        if abs(difference)>1e-5:raise ValueError('control objective replay failed')
        witnesses,unavailable=collect(p,x,d['entries']);witnesses,excluded=disjoint_witnesses(witnesses,target['observation_ids'])
        if excluded:raise ValueError('target observations entered the control calibration')
        if shared:
            component=SharedComponent(entry).evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
            detail=dict(components=[dict(component,entry=entry,weight=1.,kind='shared_posterior')])
        else:detail=mixture.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
        targets=[]
        for c in detail['components']:
            diag=c['diagnostics'][0];residual=np.array(diag['raw_residual_hz'])-diag['profile_bias_hz']
            t=dict(component=track['key'],norad=c['entry']['norad'],receiver=track['receiver'],channel=track['channel'],
                rf_hz=track['rf_hz'],times_s=track['times'],residual_hz=residual)
            targets.append(dict(target=t,weight=c['weight'],kind=c['kind'],baseline_noise=diag['noise'],
                phase_boundary_mass=c['phase_boundary_mass'],phase_mean_s=c.get('phase_mean_s'),transfers=transfer(t,witnesses)))
        row=dict(arm=arm,objective_replay_difference=difference,endpoint_east_north_km=x,targets=targets,
            witnesses=witnesses,unavailable=unavailable,excluded=excluded)
        results.append(row);write(args.output/(arm+'.json'),row)
        print(inv['job']['label'],arm,len(witnesses),'witnesses',flush=True)
    write(args.output/'result.json',dict(job=inv['job'],results=results,no_acceptance_authorized=True,
        diagnostic_only=True,target_not_used_for_position_or_receiver_fit=True,target_phase_and_orbit_fit_uses_full_target=not shared,
        witnesses_condition_on_full_incumbent_fit=True,no_new_position_estimate=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--phase-limit',type=float,default=15.)
    p.add_argument('--shared',action='store_true',help='Audit one validated shared-family bundle against its no-target control')
    run(p.parse_args())
