"""Independent-family covariance calibration, blocked prediction, paired positions.

The new curves remain predictive: they never set receiver/orbit calibration.
Empirical covariance hyperparameters use other families' incumbent residuals.
This is a conditional research approximation, not a production qualification.
"""

import argparse
from functools import partial
from pathlib import Path

import numpy as np
from scipy.linalg import solve_triangular, cho_solve

import debug_fast_graph_unassociated as report
from correlated_curve_prediction import shared_kernel, gaussian, conditional, randomized_blocks
from probe_graph_shared_high_channels import context, select_targets, inventory
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def noise_diagnostics(z, times):
    # Existing screen has a 75 Hz floor: express unit innovations on its
    # nominal 150 Hz scale rather than accidentally applying that floor to z.
    result = batch_noise_screen(np.asarray(z)[None, :]*150., np.asarray(times))
    return {k: bool(v[0]) if v.dtype == bool else float(v[0]) for k, v in result.items()}


def calibrate(d, targets, excluded):
    p, x = d['problems']['c0']; c = p.calculate(x); scan = d['scan']
    lo = min(scan.tracks[p.members[k]]['times'].min() for k in targets)-12
    hi = max(scan.tracks[p.members[k]]['times'].max() for k in targets)+12
    rows = []
    n = len(p.members)
    without_constants = c['conditional_residual_hz'] + c['features'][:, -n:] @ c['coefficient'][-n:]
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        t = scan.tracks[i]
        if t['receiver'] != 1 or row['candidate_norad'] in excluded: continue
        mask = p.keep[sl] & (t['times'] >= lo) & (t['times'] <= hi)
        if mask.sum() < 10: continue
        rows.append(dict(component=t['key'], norad=row['candidate_norad'],
            times=t['times'][mask], raw=without_constants[sl][mask],
            relative_sigma=p.point_noise[sl][mask]/scan.radio_sigma_hz))
    times = np.concatenate([r['times'] for r in rows])
    raw = np.concatenate([r['raw'] for r in rows])
    scale = np.concatenate([r['relative_sigma'] for r in rows])
    owners = np.repeat(np.arange(len(rows)), [len(r['times']) for r in rows])
    families = np.repeat([r['norad'] for r in rows], [len(r['times']) for r in rows])
    constant = 300.**2 * (owners[:, None] == owners[None, :])
    offers = []
    for scope in ('white', 'receiver', 'family'):
        amplitudes = (0.,) if scope == 'white' else (40.,80.,120.,180.)
        groups = np.zeros(len(times), int) if scope != 'family' else families
        for amplitude in amplitudes:
            for tau in ((5.,) if scope == 'white' else (2.,5.,10.,20.)):
                kernel = shared_kernel(times, groups, amplitude, tau)
                for white in (40.,60.,80.,100.,125.,150.,200.):
                    cov = constant + kernel + np.diag((white*scale)**2)
                    score = gaussian(raw, cov)['objective']
                    penalty = 0. if scope == 'white' else 2*np.log(len(raw))+2*np.log(2)
                    offers.append(dict(scope=scope, amplitude_hz=amplitude, timescale_s=tau,
                        white_hz=white, objective=score, penalty=penalty, selection_score=score+penalty))
    null = min((r for r in offers if r['scope']=='white'), key=lambda r:r['selection_score'])
    best = min((r for r in offers if r['scope']!='white'), key=lambda r:r['selection_score'])
    return dict(rows=rows, excluded_families=excluded, null=null, best_correlated=best,
        qualified=best['selection_score'] < null['selection_score'], offers=offers,
        calibration_arm='c0; frozen for both position arms',
        caveat='Incumbent calibration used these training curves; residual hyperparameter evidence is empirical and conditional.')


def entries_for_targets(d, targets, norad):
    from investigate_ds23_0268_remaining_tracks import family_frequency, corrected_observation
    from leo.analysis.research.retained_track_likelihood import profile
    p,x = d['problems']['c0']; scan=d['scan']; j=int(np.flatnonzero(scan.norads==norad)[0]); result=[]
    for k in targets:
        i=p.members[k]; t=scan.tracks[i]
        f,_=family_frequency(p,x,j,times=t['times'])
        terms=profile(corrected_observation(p,x,i),t['rf_hz']/11.5e9*f,*scan.white[i])
        result.append(dict(track_index=i,component=t['key'],candidate_index=j,norad=norad,
            alias=int(terms['alias'][0]),points=len(t['times']),observation_ids=t['observation_ids']))
    return result


def transfer_prediction(calibration, d, extras):
    """Predict a common receiver fluctuation without any target observations."""
    rows=calibration['rows']; model=calibration['best_correlated']
    times=np.concatenate([r['times'] for r in rows]);raw=np.concatenate([r['raw'] for r in rows])
    scale=np.concatenate([r['relative_sigma'] for r in rows])
    owner=np.repeat(np.arange(len(rows)),[len(r['times']) for r in rows])
    family=np.repeat([r['norad'] for r in rows],[len(r['times']) for r in rows])
    target_time=np.concatenate([d['scan'].tracks[e['track_index']]['times'] for e in extras])
    target_family=np.repeat([e['norad'] for e in extras],[e['points'] for e in extras])
    all_time=np.r_[times,target_time]
    groups=np.zeros(len(all_time),int) if model['scope']=='receiver' else np.r_[family,target_family]
    kernel=shared_kernel(all_time,groups,model['amplitude_hz'],model['timescale_s'])
    n=len(times);cross=kernel[n:,:n]
    train=kernel[:n,:n]+np.diag((model['white_hz']*scale)**2)+300.**2*(owner[:,None]==owner[None,:])
    root=np.linalg.cholesky(train)
    mean=cross@cho_solve((root,True),raw)
    covariance=kernel[n:,n:]-cross@cho_solve((root,True),cross.T)
    return dict(mean_hz=mean,covariance=(covariance+covariance.T)/2,
                target_observations_used=False,training_arm='c0; fixed for both arms')


def prediction_geometry(p, entries, powers, extra_entries, model):
    from ds23_predictive_linear import linear_geometry
    from ds23_height_problem import geometry_features
    all_entries = entries + extra_entries
    view, values, sigma, groups, slices = linear_geometry(p, all_entries)
    base_count = sum(e['points'] for e in entries)
    target = np.arange(len(values)) >= base_count
    white = sigma*np.sqrt(2)
    white[target] = model['white_hz']*sigma[target]/p.scan.radio_sigma_hz
    fixed = np.diag(white**2) + 300.**2*(groups[:,None]==groups[None,:])
    # New-curve measurement process is independent of already calibrated
    # curves, but jointly shared between the new CH7/CH8 observations.
    transfer=model.get('transfer')
    fixed[np.ix_(target,target)] += (np.asarray(transfer['covariance']) if transfer else
        shared_kernel(view.flat_times[target],np.zeros(target.sum(),int),model['amplitude_hz'],model['timescale_s']))
    curved = getattr(p,'curved_calculate',p.calculate)
    order = np.argsort(view.flat_times,kind='stable')
    def evaluate(x):
        c=curved(x); g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry=geometry_features(view,x,0.)
        design=geometry['features']; raw=values-view.q*geometry['intercept']-design@c['coefficient']
        if transfer:raw[target]-=np.asarray(transfer['mean_hz'])
        uncertainty=solve_triangular(np.linalg.cholesky(gram),design.T,lower=True).T
        cov=fixed+uncertainty@uncertainty.T
        return c,raw,cov,geometry
    return evaluate,view,slices,order,base_count


def validation(d, extras, model, seed=20261029):
    records={}
    for arm,(p,x) in d['problems'].items():
        evaluate,view,_,order,_=prediction_geometry(p,[],d['powers'],extras,model)
        _,raw,cov,_=evaluate(x); times=view.flat_times
        training,split=randomized_blocks(times,seed=seed)
        # Sort first so withheld Cholesky innovations have time order.
        raw,cov,times,training=raw[order],cov[np.ix_(order,order)],times[order],training[order]
        held=conditional(raw,cov,training)
        held['noise']=noise_diagnostics(held['whitened'],times[~training])
        owner=np.repeat(np.arange(len(extras)),[e['points'] for e in extras])[order]
        held['per_track_noise']={e['component']:noise_diagnostics(held['whitened'][owner[~training]==k],
            times[~training][owner[~training]==k]) for k,e in enumerate(extras)}
        held['RMS_hz']=float(np.sqrt(np.mean(held['residual_hz']**2)))
        joint=gaussian(raw,cov)
        joint['noise']=noise_diagnostics(joint['whitened'],times)
        records[arm]=dict(split=split, order=order,training_points=int(training.sum()),
            withheld_points=int((~training).sum()), times_s=times, raw_hz=raw,
            training_sorted=training,held=held,joint=joint)
    return records


def position_trial(d, extras, model):
    from ds23_frequency_events import make_event_problem
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_frequency_events import cached,summary
    from investigate_dsx01_localization_failures import fit
    pair={}
    for arm in ('c0','fitted_c'):
        reference=np.zeros(len(d['means'])); x=np.zeros(2); history=[]
        for epoch in range(5):
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],
                base_problem_factory=partial(make_problem,support_policy='active'))
            base=p.calculate
            evaluate,view,slices,order,base_count=prediction_geometry(p,d['entries'],d['powers'],extras,model)
            def calculate(z):
                c,raw,cov,geometry=evaluate(z); c=dict(c)
                predicted=gaussian(raw[order],cov[np.ix_(order,order)])
                c['curved_negative_twice_elbo']=c['negative_twice_elbo']
                c['negative_twice_elbo']+=predicted['objective']
                # Baseline scale 1 Hz gives nonnegative log-volume here.
                c['residual']=np.r_[c['residual'],predicted['whitened'],np.sqrt(predicted['logdet'])]
                c['linear_raw_prediction_residual_hz']=raw
                c['linear_elevation']=geometry['elevation']
                c['prediction_covariance']=cov;c['prediction_order']=order
                return c
            p.calculate=calculate;p.curved_calculate=base
            # Existing summary audits the original predictive curves only;
            # new covariance-aware curve diagnostics are recorded separately.
            p.linear_slices=slices[:len(d['entries'])];p.linear_entries=d['entries']
            cached(p)
            result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))))
            reference=phase
        row=summary(p,x,d['entries']);c=p.calculate(x)
        target=np.arange(base_count,len(view.flat_times));order_target=target[np.argsort(view.flat_times[target],kind='stable')]
        diagnostic=gaussian(c['linear_raw_prediction_residual_hz'][order_target],
                            c['prediction_covariance'][np.ix_(order_target,order_target)])
        diagnostic['noise']=noise_diagnostics(diagnostic['whitened'],view.flat_times[order_target])
        owners=np.repeat(np.arange(len(extras)),[e['points'] for e in extras])
        owners=owners[order_target-base_count]
        diagnostic['per_track_noise']={e['component']:noise_diagnostics(diagnostic['whitened'][owners==k],
            view.flat_times[order_target][owners==k]) for k,e in enumerate(extras)}
        raw_target=c['linear_raw_prediction_residual_hz'][target]
        cov_target=c['prediction_covariance'][np.ix_(target,target)]
        alpha=cho_solve((np.linalg.cholesky(cov_target),True),raw_target)
        counts=np.cumsum([0]+[e['points'] for e in extras]);physical=[]
        for k,e in enumerate(extras):
            sl=slice(counts[k],counts[k+1]);bias=float(300.**2*alpha[sl].sum())
            physical.append(dict(component=e['component'],bias_hz=bias,
                raw_RMS_after_bias_hz=float(np.sqrt(np.mean((raw_target[sl]-bias)**2)))))
        curved,predictive,associated,_=report.memberships(p,x,d['entries']+extras)
        row.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],target=diagnostic,
            target_min_elevation_deg=float(c['linear_elevation'][target].min()),
            target_times_s=view.flat_times[order_target],target_raw_hz=c['linear_raw_prediction_residual_hz'][order_target],
            displacement_from_CH1_m=float(1000*np.linalg.norm(x-d['problems'][arm][1])),
            physical_target_checks=physical,curved_points=len(curved),predictive_points=len(predictive),
            proposed_associated_points=len(associated),proposed_associated_ids=sorted(associated),
            postfit_only_points=len(associated-curved-predictive))
        pair[arm]=row
        print('Position',model['scope'],arm,x,diagnostic['noise'],'movement',row['displacement_from_CH1_m'],flush=True)
    return pair


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    d=context(args);targets=select_targets(d); inv=inventory(d,targets)
    candidate=inv['screens'][0]['active']['norad']
    excluded=sorted({candidate,*[s['previous_nominee'] for s in inv['screens']]})
    calibration=calibrate(d,targets,excluded)
    report.write(args.output/'calibration.json',calibration)
    print('Calibration',calibration['null'],calibration['best_correlated'],'qualified',calibration['qualified'],flush=True)
    extras=entries_for_targets(d,targets,candidate)
    report.write(args.output/'target_entries.json',extras)
    results={}
    transferred=dict(calibration['best_correlated'],transfer=transfer_prediction(calibration,d,extras))
    report.write(args.output/'transfer_prediction.json',transferred['transfer'])
    for name,model in (('white',calibration['null']),('correlated',calibration['best_correlated']),('transferred',transferred)):
        held=validation(d,extras,model)
        report.write(args.output/(name+'_validation.json'),held)
        print(name,'validation',[(a,r['held']['RMS_hz'],r['held']['objective'],r['held']['noise']) for a,r in held.items()],flush=True)
        results[name]=dict(model=model,validation=held)
    for name,result in results.items():
        model=result['model']
        pair=position_trial(d,extras,model)
        report.write(args.output/(name+'_positions.json'),pair)
        result['positions']=pair
    alternate=entries_for_targets(d,targets,inv['screens'][0]['previous_nominee'])
    alternate_check=validation(d,alternate,calibration['best_correlated'])
    report.write(args.output/'alternate_satellite_validation.json',dict(norad=alternate[0]['norad'],arms=alternate_check))
    gain={a:results['white']['validation'][a]['held']['objective']-results['correlated']['validation'][a]['held']['objective'] for a in ('c0','fitted_c')}
    report.write(args.output/'decision.json',dict(independent_training_preferred_correlated=calibration['qualified'],
        withheld_negative_twice_log_predictive_gain=gain,
        target_identity_previously_selected_on_full_curve=True,
        target_curves_never_update_calibration=True,
        predictive_covariance_conditional_approximation=True,
        position_truth_used=False,post_observation_TLE_used=False,
        note='A covariance screen pass is not production qualification; independent satellite identity and cohort validation remain required.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run','ch1','source-root','output'):parser.add_argument('--'+name,required=True,type=Path)
    run(parser.parse_args())
