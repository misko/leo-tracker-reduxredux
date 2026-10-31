"""Bounded, target-excluded conditional residual covariance experiment.

Frozen geometry is inherited from earlier control/addition fits. This is not
independent localization, and held-track geometry is not refitted. No gates or
persisted associations are modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached
from leo.analysis.research.retained_track_likelihood import profile, whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

SEED = 20261031
WIDTH = 6.
PRIOR = 150.
NOISE = 150.


def split_groups(components):
    names = sorted(set(components))
    rng = np.random.default_rng(SEED)
    shuffled = list(rng.permutation(names))
    held = set(shuffled[:max(1, len(names)//3)])
    return dict(seed=SEED, training=[n for n in names if n not in held], held=sorted(held))


def basis(times, knots):
    b = np.exp(-.5*((np.asarray(times)[:, None]-knots)/WIDTH)**2)
    return b/np.maximum(b.sum(axis=1, keepdims=True), 1e-12)


def eligible(w, target, model):
    rx = w['receiver'] == target['receiver']
    sat = w['norad'] == target['norad']
    if model == 'receiver': return rx and not sat
    if model == 'satellite': return sat and not rx
    return rx or sat


def design(w, target, knots, model):
    b = basis(w['times_s'], knots)*w['rf_hz']/11.5e9
    blocks = []
    if model in ('receiver', 'joint'): blocks.append(b*(w['receiver'] == target['receiver']))
    if model in ('satellite', 'joint'): blocks.append(b*(w['norad'] == target['norad']))
    return np.column_stack(blocks)


def fit(witnesses, target, knots, model):
    train = [w for w in witnesses if w['component'] != target['component'] and eligible(w, target, model)]
    width = len(knots)*(2 if model == 'joint' else 1)
    if not train: return np.zeros(width), []
    sizes = [len(w['times_s']) for w in train]
    h = np.vstack([design(w, target, knots, model)*PRIOR for w in train])
    group = np.repeat(np.arange(len(train)), sizes)
    offsets = np.eye(len(train))[group]*300.
    a = np.column_stack((h, offsets))/NOISE
    y = np.concatenate([w['residual_hz'] for w in train])/NOISE
    coef = np.linalg.solve(np.eye(a.shape[1])+a.T@a, a.T@y)
    return coef[:width]*PRIOR, [w['component'] for w in train]


def metrics(scan, w, correction):
    raw = np.asarray(w['residual_hz'])-correction
    terms = profile(raw, np.zeros(len(raw)), *whitening(w['times_s']), bias_sigma=300.)
    r = terms['residual'][0]
    noise = batch_noise_screen(terms['innovations'], np.asarray(w['times_s']))
    return dict(RMS_hz=float(terms['rms'][0]), bias_hz=float(terms['bias'][0]),
                lag1_acf=float(noise['lag1_acf'][0]), noise_screen_pass=bool(noise['noise_screen_pass'][0]),
                noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in noise.items()},
                residual_hz=r, correction_hz=correction)


def curve(scan, index, norad, mask, residual):
    t = scan.tracks[index]
    return dict(component=t['key'], index=index, norad=int(norad), receiver=t['receiver'],
                channel=t['channel'], rf_hz=t['rf_hz'], times_s=t['times'][mask],
                observation_ids=np.asarray(t['observation_ids'])[mask], residual_hz=np.asarray(residual)[mask])


def extract(d, row, saved, target_entries, held_components):
    """Refit baseline latent receiver coefficients with held curved tracks cut."""
    scan=d['scan']; keep=d['keep'].copy(); base,_=d['problems']['c0']
    for i,sl in zip(base.members,base.slices,strict=True):
        if scan.tracks[i]['key'] in held_components: keep[sl]=False
    v=saved; kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
    p=make_event_problem(scan,d['node'],keep,row['arm'],np.array(v['phase_reference']),d['powers'],d['means'],d['model'],v['events'],**kw)
    # Predictive entries cannot update the calibration coefficients; retaining
    # them here computes held residuals at the frozen geometry only.
    attach_event_predictive(p,d['entries']+target_entries,d['powers']);cached(p)
    x=np.array(v['endpoint_east_north_km']); c=p.calculate(x); curves=[]
    for r,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        original=d['keep'][sl]
        if original.any(): curves.append(curve(scan,i,r.get('norad',r.get('candidate_norad')),original,c['conditional_residual_hz'][sl]))
    for entry,sl in zip(p.linear_entries,p.linear_slices,strict=True):
        i=entry['track_index']; raw=c['linear_raw_prediction_residual_hz'][sl]
        curves.append(curve(scan,i,entry.get('norad',scan.norads[entry['candidate_index']]),np.ones(len(raw),bool),raw))
    target=next(w for w in curves if w['component']==row['component'])
    target_ids=set(target['observation_ids'])
    calibration_ids={oid for i,sl in zip(p.members,p.slices,strict=True) for oid,k in zip(scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if k}
    assert not target_ids & calibration_ids
    witnesses=[]
    for w in curves:
        if w['component']==target['component']: continue
        if not eligible(w,target,'joint'):continue
        mask=(w['times_s']>=min(target['times_s'])-18)&(w['times_s']<=max(target['times_s'])+18)
        if mask.sum()<8:continue
        w=dict(w)
        for key in ('times_s','observation_ids','residual_hz'):w[key]=w[key][mask]
        assert not target_ids & set(w['observation_ids'])
        witnesses.append(w)
    allids=[oid for w in witnesses for oid in w['observation_ids']]
    assert len(allids)==len(set(allids)), 'overlapping witness groups'
    return target,witnesses,dict(negative_twice_elbo=c['negative_twice_elbo'],
        curved_negative_twice_elbo=c.get('curved_negative_twice_elbo',c['negative_twice_elbo']))


def run(args):
    began=time.monotonic(); args.output.mkdir(parents=True,exist_ok=True)
    protocol=dict(seed=SEED,width_s=WIDTH,coefficient_prior_hz=PRIOR,witness_noise_hz=NOISE,
      per_track_nuisance_prior_hz=300.,knots_spacing_s=6.,models=['receiver','satellite','joint'],
      selection='DS26-0050 then DS26-0223 then DS26-0251; no outcome filtering',
      randomization='one third of whole witness components held; target always excluded',
      target_fits_correction=False,baseline_geometry_frozen=True,addition_geometry_target_informed=True,
      held_geometry_inherited=True,held_curved_groups_removed_before_receiver_fit=True,
      per_track_bias_reprofiled_in_both_variants=True,position_accuracy_evaluated=False,
      GPS_used=False,new_RF=False,production_changes=False,
      interpretation='Conditional residual covariance diagnostic, not fully independent predictive likelihood or localization. Frozen geometry/phase were learned previously; held-track geometry is inherited. No full inclusion until independent correction validates.')
    write(args.output/'protocol.json',protocol)
    results=[]
    for case in args.cases:
        path=next(args.source.glob('*'+case+'/result.json')); diag=read(path);row=diag['row']
        trial=Path(diag['actual_pipeline_trial']['path']); addition=read(trial);control=read(trial.parent/'control.json')
        d=context(read(row['inventory_path'])); assignment=None; case_rows=[]
        for role,saved in (('control',control),('addition',addition)):
            for arm in ('c0','fitted_c'):
                rr=dict(row,arm=arm);v=saved['arms'][arm]
                t,ws,obj=extract(d,rr,v,addition['target_entries'],set())
                expected=v.get('curved_negative_twice_elbo',v['negative_twice_elbo'])
                replay_delta=obj['curved_negative_twice_elbo']-expected
                assert abs(replay_delta)<1e-5, (case,role,arm,replay_delta)
                if role=='addition':
                    assert abs(obj['negative_twice_elbo']-v['negative_twice_elbo'])<1e-5
                original_target_metrics=metrics(d['scan'],t,np.zeros(len(t['times_s'])))
                if assignment is None:
                    assignment=split_groups(w['component'] for w in ws)
                target,witnesses,obj=extract(d,rr,v,addition['target_entries'],set(assignment['held']))
                bykey={w['component']:w for w in witnesses}
                assert set(bykey)==set(assignment['training']+assignment['held'])
                train=[bykey[k] for k in assignment['training']]; held=[bykey[k] for k in assignment['held']]
                train_ids={oid for w in train for oid in w['observation_ids']}
                held_ids={oid for w in held for oid in w['observation_ids']}
                assert not train_ids&held_ids
                knots=np.arange(min(target['times_s'])-18,max(target['times_s'])+24,6.)
                for model in protocol['models']:
                    coef,used=fit(train,target,knots,model)
                    evaluations=[]
                    for w in [target]+[w for w in held if eligible(w,target,model)]:
                        pred=design(w,target,knots,model)@coef
                        evaluations.append(dict(component=w['component'],target=w is target,norad=w['norad'],receiver=w['receiver'],
                          points=len(pred),times_s=w['times_s'],observation_ids=w['observation_ids'],
                          baseline=metrics(d['scan'],w,np.zeros(len(pred))),corrected=metrics(d['scan'],w,pred)))
                    case_rows.append(dict(role=role,arm=arm,model=model,training_components=used,
                       full_calibration_target_metrics=original_target_metrics,curved_objective_replay_delta=replay_delta,
                       training_points=sum(len(bykey[k]['times_s']) for k in used),evaluations=evaluations))
                    z=evaluations[0]
                    print(case,role,arm,model,'target RMS',round(z['baseline']['RMS_hz'],2),round(z['corrected']['RMS_hz'],2),
                      'acf',round(z['corrected']['lag1_acf'],3),'held',[(z['component'].split('-RF')[0],round(z['baseline']['RMS_hz'],1),round(z['corrected']['RMS_hz'],1)) for z in evaluations[1:]],flush=True)
        result=dict(case=case,assignment=assignment,rows=case_rows,target_ids=target['observation_ids'],
          source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,trial,trial.parent/'control.json')})
        write(args.output/(case+'.json'),result);results.append(result)
    write(args.output/'result.json',dict(protocol=protocol,cases=results,seconds=time.monotonic()-began))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cases',nargs='+',default=['DS26-0050','DS26-0223','DS26-0251']);run(p.parse_args())
