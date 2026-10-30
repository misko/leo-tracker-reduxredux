"""Conditional objective curvature and nuisance shifts for a graph addition."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from phase_reference_checks import phase_refresh
from investigate_ds23_0268_remaining_tracks import family_frequency
from cross_curve_residual_witnesses import rate


def curvature(evaluate,x,step=.025):
    """Finite differences of a scalar position objective, in kilometre units."""
    x=np.asarray(x,float);eye=np.eye(2)*step;center=evaluate(x);g=np.zeros(2);h=np.zeros((2,2))
    for i in range(2):
        a,b=evaluate(x+eye[i]),evaluate(x-eye[i]);g[i]=(a-b)/(2*step);h[i,i]=(a-2*center+b)/step**2
    h[0,1]=h[1,0]=(evaluate(x+eye[0]+eye[1])-evaluate(x+eye[0]-eye[1])-evaluate(x-eye[0]+eye[1])+evaluate(x-eye[0]-eye[1]))/(4*step**2)
    values,vectors=np.linalg.eigh(h)
    return dict(gradient_per_km=g,hessian_per_km2=h,eigenvalues=values,eigenvectors=vectors)


def run(args):
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0'];saved={r:read(args.trial/(r+'.json')) for r in ('control','target_0')}
    target=saved['target_0']['target_entries'][0];args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=inv['job'],target=target,source=str(args.trial),phase_rounds=5,
        reference_limit_s=15,finite_difference_step_km=.025,line_fractions=np.linspace(-.5,1.5,17),
        no_GPS_in_geometry_or_fits=True,diagnostic_case_selection_from_previously_reported_position_effects=True,
        no_new_satellite_choices=True,no_new_parameters=True,future_TLE=False,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.trial/'control.json',args.trial/'target_0.json')}))
    results={}
    for arm in ('c0','fitted_c'):
        models={};x0=np.array(saved['control']['arms'][arm]['endpoint_east_north_km']);x1=np.array(saved['target_0']['arms'][arm]['endpoint_east_north_km'])
        direction=x1-x0
        for role in ('control','target_0'):
            node,keep=configuration(d['node'],d['keep'],base.slices,saved[role]['target_entries']);means,_=prior_means(d,node)
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            old=saved[role]['arms'][arm];p=make_event_problem(d['scan'],node,keep,arm,np.array(old['phase_reference']),d['powers'],means,d['model'],[],**kw)
            attach_event_predictive(p,d['entries'],d['powers']);cached(p)
            replay=p.calculate(np.array(old['endpoint_east_north_km']))['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(replay)>1e-5:raise ValueError('source objective did not replay')
            cache={}
            def evaluate(x,detail=False):
                key=tuple(x)
                if key in cache and not detail:return cache[key]
                reference=np.zeros(len(means))
                for _ in range(5):
                    p=make_event_problem(d['scan'],node,keep,arm,reference,d['powers'],means,d['model'],[],**kw)
                    attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                    reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                c=p.calculate(x);state=p.state(x)
                r=dict(x=x,objective=c['negative_twice_elbo'],curved_objective=c.get('curved_negative_twice_elbo',c['negative_twice_elbo']),
                    phase_gap_s=check['phase_change_s'],terms={k:c[k] for k in ('quadratic','logvolume','noise_gamma_cost','prior_gamma_cost','normalization_constant') if k in c})
                cache[key]=r
                if detail:
                    approximate,_=p.conditional_frequency(x);curves=[]
                    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                        active=p.keep[sl]
                        if not active.any():continue
                        t=p.scan.tracks[i];j=row['candidate_index'];times=t['times'][active];q=t['rf_hz']/11.5e9
                        f,e=family_frequency(p,x,j,times=times);res=c['conditional_residual_hz'][sl][active]-q*(f-approximate[sl][active])
                        radio=p.scan.hardware(t,state['beta'])+q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
                        curves.append(dict(component=t['key'],norad=row['candidate_norad'],receiver=t['receiver'],channel=t['channel'],
                            target=row['component']==target['component'],times_s=times,residual_hz=res,points=int(active.sum()),
                            RMS_hz=float(np.sqrt(np.mean(res**2))),radio_hz=radio[active],
                            weighted_residual_energy=float(np.sum(res**2*d['powers'][p.noise_groups[sl][active]]*c['noise_precision'][p.noise_groups[sl][active]]/p.point_noise[sl][active]**2)),
                            phase_s=float(state['phases'][j]),phase_prior_mean_s=float(means[p.labels.index(j)]),phase_prior_sigma_s=float(p.phase_sigma[p.labels.index(j)]),
                            orbit_modes_active=j in p.supported,point_noise_hz=float(np.median(p.point_noise[sl][active])),
                            noise_precision=float(c['noise_precision'][p.noise_groups[sl][active][0]]),power=float(d['powers'][p.noise_groups[sl][active][0]])))
                    r=dict(r,curves=curves,physical_receiver_beta=state['beta'],physical_receiver_smooth=state['smooth'])
                return r
            endpoints={name:evaluate(x,True) for name,x in [('control_position',x0),('addition_position',x1)]}
            line=[dict(fraction=float(f),**evaluate(x0+f*direction)) for f in np.linspace(-.5,1.5,17)]
            derivatives=curvature(lambda x:evaluate(x)['objective'],x0)
            models[role]=dict(endpoints=endpoints,line=line,curvature_at_control=derivatives,objective_replay_difference=replay,
                maximum_evaluated_phase_gap_s=max(r['phase_gap_s'] for r in cache.values()))
        a=models['control']['endpoints']['control_position'];b=models['target_0']['endpoints']['addition_position']
        changes=[]
        for old in a['curves']:
            new=next(t for t in b['curves'] if t['component']==old['component'])
            tt=np.asarray(old['times_s']);delta=np.asarray(new['radio_hz'])-old['radio_hz'];slope=rate(tt,delta)['slope_hz_s'] if len(tt)>=4 else None
            changes.append(dict(component=old['component'],norad=old['norad'],receiver=old['receiver'],channel=old['channel'],points=old['points'],
                before_RMS_hz=old['RMS_hz'],after_RMS_hz=new['RMS_hz'],residual_energy_change=new['weighted_residual_energy']-old['weighted_residual_energy'],
                phase_change_s=new['phase_s']-old['phase_s'],radio_mean_change_hz=float(np.mean(delta)),radio_slope_change_hz_s=slope))
        vals=models['control']['curvature_at_control'];weak=vals['eigenvectors'][:,0]
        results[arm]=dict(models=models,changes=changes,position_shift_km=float(np.linalg.norm(direction)),
            direction_weak_axis_alignment=float(abs(weak@direction)/max(np.linalg.norm(direction),1e-12)))
        write(args.output/(arm+'.json'),results[arm]);print(inv['job']['label'],arm,'shift',np.linalg.norm(direction),'curvature',vals['eigenvalues'],flush=True)
    write(args.output/'result.json',dict(job=inv['job'],target=target,arms=results,no_new_associations=True,
        local_curvature_is_not_calibrated_position_confidence=True,residual_energy_is_not_ELBO_decomposition=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
