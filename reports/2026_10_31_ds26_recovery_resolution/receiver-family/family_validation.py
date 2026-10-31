"""Training-only whole-family receiver transfer; fixed model, bounded research."""
import argparse, copy, hashlib, json, signal, time
from pathlib import Path
import numpy as np
from scipy.linalg import cho_solve
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training,training_factory
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.retained_track_likelihood import profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

TARGET=63468
SEED=20261031
KNOTS=np.arange(-18.,324.,6.)


def assignments(families):
    ordered=np.random.default_rng(SEED).permutation(sorted(set(families)-{TARGET}))
    return [sorted(map(int,a)) for a in np.array_split(ordered,3)]


def family_cut(rows,slices,keep,excluded):
    result=np.array(keep,copy=True)
    for r,sl in zip(rows,slices,strict=True):
        if int(r.get('norad',r.get('candidate_norad'))) in excluded:result[sl]=False
    return result


def basis(times):
    b=np.exp(-.5*((np.asarray(times)[:,None]-KNOTS)/6.)**2)
    return b/b.sum(axis=1,keepdims=True)


def design(w):
    b=basis(w['times_s'])*w['rf_hz']/11.5e9
    return np.column_stack((b*(w['receiver']==1),b*(w['receiver']==2)))


def correction_fit(witnesses):
    assert all(w['norad']!=TARGET for w in witnesses)
    h=np.vstack([design(w)*150. for w in witnesses])
    sizes=[len(w['times_s']) for w in witnesses]
    groups=np.repeat(np.arange(len(witnesses)),sizes)
    a=np.column_stack((h,np.eye(len(witnesses))[groups]*300.))/150.
    y=np.concatenate([w['raw_hz'] for w in witnesses])/150.
    gram=np.eye(a.shape[1])+a.T@a
    covariance=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))
    return (covariance@(a.T@y))[:h.shape[1]]*150.,covariance[:h.shape[1],:h.shape[1]]*150.**2


def forecast(w,training,coefficient,covariance):
    counts=np.zeros(len(w['times_s']),int)
    for n in sorted({v['norad'] for v in training}):
        ts=[v['times_s'] for v in training if v['norad']==n and v['receiver']==w['receiver']]
        if ts:
            t=np.concatenate(ts);counts+=(abs(np.asarray(w['times_s'])[:,None]-t).min(axis=1)<=18.)
    support=counts>=2
    h=design(w);raw=h@coefficient
    delta=np.where(support,raw,0.)
    sigma=np.sqrt(np.maximum(0,np.einsum('ij,jk,ik->i',h,covariance,h)))
    return dict(prediction_hz=delta,unmasked_model_prediction_hz=raw,correction_sigma_hz=sigma,
      support=support,distinct_families_within_18s=counts)


def metrics(w,delta,sigma,mask=None):
    mask=np.ones(len(w['times_s']),bool) if mask is None else np.asarray(mask,bool)
    if mask.sum()<4:return dict(points=int(mask.sum()),status='insufficient_points')
    t=np.asarray(w['times_s'])[mask];raw=(np.asarray(w['raw_hz'])-delta)[mask]
    terms=profile(raw,np.zeros(len(raw)),*whitening(t),bias_sigma=300.)
    ns=batch_noise_screen(terms['innovations'],t)
    noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in ns.items()}
    failed=[k for k,bad in [('RMS',terms['rms'][0]>450),('offset',abs(terms['bias'][0])>3000),
      ('frozen_alias',terms['alias'][0]!=0),('visibility',np.min(np.asarray(w['elevation_deg'])[mask])<0),
      ('mean',noise['mean_z']>3),('slope',noise['slope_z']>3),('quadratic',noise['quadratic_bic_gain']>10),
      ('step',noise['maximum_step_z']>4),('ACF',abs(noise['lag1_acf'])>4/np.sqrt(len(t)))] if bad]
    # Approximate conditional marginal coverage; not a calibrated probability.
    uncertainty=np.sqrt(150.**2*2+300.**2+np.asarray(w['base_variance_hz2'])[mask]+np.asarray(sigma)[mask]**2)
    return dict(points=len(t),RMS_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),
      extra_alias=int(terms['alias'][0]),failed_gates=failed,noise=noise,residual_hz=terms['residual'][0],
      approximate_marginal_95_coverage=float(np.mean(abs(terms['residual'][0])<=1.96*uncertainty)),
      median_predictive_sigma_hz=float(np.median(uncertainty)))


def curves(d,p,x,definitions):
    scan=d['scan'];c=p.calculate(x);u=c['features'][p.keep];g=p.noise_groups[p.keep]
    weights=c['noise_precision'][g]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None])
    covariance=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))
    state=p.state(x);output=[]
    for entry in definitions:
        i=entry['track_index'];track=scan.tracks[i];q=track['rf_hz']/11.5e9
        f,e=family_frequency(p,x,entry['candidate_index'],times=track['times'])
        raw=track['values']+entry['alias']*(1/4.4e-6)-p.scan.hardware(track,state['beta'])-q*scan.rx_basis[i]@state['smooth'][track['receiver']-1]-q*f
        view,*_=linear_geometry(p,[entry]);geo=geometry_features(view,x,0.);h=geo['features']
        bv=np.einsum('ij,jk,ik->i',h,covariance,h)
        mask=np.asarray(entry['use_mask'],bool)
        output.append(dict(component=entry['component'],norad=int(entry['norad']),receiver=track['receiver'],channel=track['channel'],
          rf_hz=track['rf_hz'],times_s=track['times'][mask],observation_ids=np.asarray(track['observation_ids'])[mask],
          raw_hz=raw[mask],elevation_deg=e[mask],base_variance_hz2=bv[mask]))
    return output


def timeout(signum,frame):raise TimeoutError('570 second overall scientific execution limit')


def run(args):
    began=time.monotonic();signal.signal(signal.SIGALRM,timeout);signal.alarm(570)
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    diag=read(args.source);row=diag['row'];trial=read(diag['actual_pipeline_trial']['path']);inv=read(row['inventory_path']);d=context(inv)
    # Replace full-data RF noise selection with the same fixed preprocessing in
    # both arms, including predictive position entries.
    d['scan'].fixed_window_noise=dict(d['scan'].fixed_window_noise,extra_parameter_BIC_gain=0.)
    d['scan'].radio_sigma_hz=150.
    base,_=d['problems']['c0'];definitions=[]
    for k,(r,i,sl) in enumerate(zip(base.rows,base.members,base.slices,strict=True)):
        if not d['keep'][sl].any():continue
        definitions.append(dict(component=r['component'],track_index=i,candidate_index=r['candidate_index'],
          norad=r['candidate_norad'],alias=int(base.alias[k]),use_mask=d['keep'][sl]))
    for e in d['entries']+trial['target_entries']:
        definitions.append(dict(e,use_mask=np.ones(len(d['scan'].tracks[e['track_index']]['times']),bool)))
    keys=[e['component'] for e in definitions];assert len(keys)==len(set(keys))
    families={e['norad'] for e in definitions if e['norad']!=TARGET};folds=assignments(families)
    protocol=dict(case='DS26-0050',seed=SEED,held_families_by_fold=folds,target_family=TARGET,target_component=row['component'],
      initial_east_north_km=[0.,0.],position_box_km=[-12.5,12.5],phase_rounds=5,position_steps_per_round=48,
      arms=['c0','fitted_c'],fixed_noise_hz=150.,coefficient_prior_hz=150.,nuisance_prior_hz=300.,
      basis_width_s=6.,knots_s=KNOTS,correction='receiver-only; independent block per receiver',
      support='at least two distinct training NORAD families within18s on same receiver; zero applied elsewhere',
      all_target_family_removed=True,held_across_receivers_and_channels=True,predictive_training_entries_filtered=True,
      nomination='Original frozen graph candidate and alias definitions; conditional nominations, not independent identity discovery',
      phase_prior='Causal pre-RF TLE prior; no target/held phase training',family_weights='all one',GPS_used=False,
      future_TLE=False,new_RF=False,production_changed=False,overall_limit_s=570,thread_limit=1,
      uncertainty='Conditional empirical coefficient covariance plus correction posterior, fixed predictive noise and track bias. Excludes position uncertainty, covariance cross-terms, orbit nonlinearity and learned precision uncertainty. Coverage is descriptive, not calibrated.',
      source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.source,Path(diag['actual_pipeline_trial']['path']),Path(row['inventory_path']))})
    write(out/'protocol.json',protocol);results=[]
    try:
      for fold,held in enumerate(folds):
        excluded=set(held)|{TARGET};keep=family_cut(base.rows,base.slices,d['keep'],excluded)
        entries=[e for e in d['entries'] if e['norad'] not in excluded]
        dd=dict(d,entries=entries)
        # Existing factory enforces the repository's 25km regional box.
        for arm in protocol['arms']:
          start=time.monotonic();p,x,meta=fit_training(dd,dd['node'],keep,arm,start=(0.,0.),predictive=True)
          assert np.allclose(p.lower,[-12.5,-12.5]) and np.allclose(p.upper,[12.5,12.5]),(p.lower,p.upper)
          active={int(r['candidate_norad']) for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
          assert not active&excluded and not {e['norad'] for e in entries}&excluded
          allcurves=curves(d,p,x,definitions);training=[w for w in allcurves if w['norad'] not in excluded]
          evaluation=[w for w in allcurves if w['norad'] in excluded]
          trainids=[str(o) for w in training for o in w['observation_ids']];evalids=[str(o) for w in evaluation for o in w['observation_ids']]
          assert len(trainids)==len(set(trainids)) and len(evalids)==len(set(evalids)) and not set(trainids)&set(evalids)
          coefficient,covariance=correction_fit(training);evaluations=[]
          for w in evaluation:
            forecasted=forecast(w,training,coefficient,covariance);delta=forecasted['prediction_hz'];sd=forecasted['correction_sigma_hz']
            evaluations.append(dict(**w,target=w['component']==row['component'],forecast=forecasted,
              before=metrics(w,np.zeros(len(delta)),np.zeros(len(delta))),after=metrics(w,delta,sd),
              supported_before=metrics(w,np.zeros(len(delta)),np.zeros(len(delta)),forecasted['support']),
              supported_after=metrics(w,delta,sd,forecasted['support'])))
          rec=dict(fold=fold,arm=arm,held_families=held,training_families=sorted(active),training=meta,
            training_curve_components=[w['component'] for w in training],training_observation_ids=trainids,
            training_predictive_entries=[e['component'] for e in entries],target_or_held_updates_geometry=False,
            lower=p.lower,upper=p.upper,seconds=time.monotonic()-start,evaluations=evaluations)
          write(out/f'fold-{fold}-{arm}.json',rec);results.append(rec)
          t=next(w for w in evaluations if w['target']);print('fold',fold,arm,'seconds',round(rec['seconds'],2),'target',t['before']['RMS_hz'],t['after']['RMS_hz'],'fails',t['after']['failed_gates'],'support',sum(t['forecast']['support']),flush=True)
      write(out/'result.json',dict(protocol=protocol,folds=results,seconds=time.monotonic()-began,status='complete'))
    except Exception as exc:
      write(out/'terminal.json',dict(status='bounded_failure',error=repr(exc),seconds=time.monotonic()-began,completed_arms=len(results)))
      raise
    finally:signal.alarm(0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
