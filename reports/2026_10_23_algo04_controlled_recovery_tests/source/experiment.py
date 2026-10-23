"""Bounded rescue ablation and common held-family prediction; no evaluation GPS."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from types import SimpleNamespace
import argparse
import copy
import contextlib
import itertools
import signal
import time
import numpy as np
from scipy.optimize import minimize

import run_ds23_dbg01_iteration_002 as engine
import probe_ds23_graph_seeded_paths as paths
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import summary
from investigate_dsx01_localization_failures import fit
from ds23_frequency_events import make_event_problem
from ds23_family_cavity import predictive_density_reference, unused_student_gap
from ds23_height_problem import geometry_features
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read, write, sha
from leo.analysis.research.retained_track_likelihood import PERIOD

OUT=Path(__file__).resolve().parents[1]
SOURCE=Path('/srv/bulk/leo/research/algo04-candidate-20261023')
CASES=['DS23-0344','DS23-0256','DS23-0404','DS23-0041','DS23-0272']
ARMS=('c0','fitted_c')


def preserve(parent,child):
    return all(set(parent[a]['accepted_observation_ids'])<=set(child[a]['accepted_observation_ids']) for a in ARMS)


def qualifies(pair):
    return bool(valid(pair) and all(s['final_phase_change_s']<=.01 for s in pair.values()))


def context(case):
    d=engine.current_setup(case);frozen=read(SOURCE/'raw'/case/'result.json');r=frozen['reference']
    d.update(node=r['node'],keep=np.asarray(r['mask'],bool),means=np.asarray(r['means']),entries=r['entries'],arms=r['arms'])
    d['base']=paths.build(d,'default','c0',r['arms']['c0']['phase_reference'])
    d['original_protected']={row['candidate_index'] for row,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    d['original_protected'].update(e['candidate_index'] for e in d['entries'])
    return d,frozen


def apply_trial(d,t):
    return dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'],arms=t['arms'])


def ordinary(d,kind,arm,previous=None):
    x=np.zeros(2) if previous is None else np.asarray(previous['endpoint_east_north_km'])
    reference=np.zeros(len(d['means'])) if previous is None else np.asarray(previous['phase_reference'])
    history=[]
    for _ in range(5):
        p=paths.build(d,kind,arm,reference)
        if previous is None:
            result=fit(p,x,iterations=48)
        else:
            # Same scalar ELBO and 5x40 allowance as gate-constrained rescue,
            # with no residual-statistic constraints in the optimizer.
            origin=float(p.calculate(x)['negative_twice_elbo'])
            result0=minimize(lambda z:p.calculate(z)['negative_twice_elbo']-origin,x,
                method='SLSQP',bounds=list(zip(p.lower,p.upper)),
                options=dict(maxiter=40,ftol=1e-7,eps=1e-3))
            result=dict(parameters=result0.x,score=float(result0.fun+origin),
                        solver_success=bool(result0.success),iterations=int(result0.nit),
                        solver_message=str(result0.message))
        x=np.asarray(result['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    saved=summary(p,x,d['entries']);saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
        minimum_gate_slack=min(gate_slacks(p,x,d['entries']).values()))
    return saved


def audit(d,kind,pair):
    result=[]
    for arm,s in pair.items():
        p=paths.build(d,kind,arm,s['phase_reference']);x=np.asarray(s['endpoint_east_north_km'])
        delta=p.calculate(x)['negative_twice_elbo']-s['negative_twice_elbo']
        assert abs(delta)<1e-5,(arm,delta)
        expected=sum(t['points'] for t in s['gates']['tracks'])
        assert expected==int(d['keep'].sum())
        result.append(dict(arm=arm,objective_replay_difference=delta,curved_points=expected))
    return result


def coverage(d,kind,pair):
    return {a:paths.coverage(d,kind,a,s) for a,s in pair.items()}


def frozen_bank(case):
    base=SOURCE/'raw'/case
    original=read(base/'single_curve_reentry'/f'{case}_positions.json')
    support=read(base/'support_aware_reentry'/f'{case}.json')
    return [(f'default_{i:02d}','default',t) for i,t in enumerate(original['trials'])]+[(f'support_{i:02d}','support',t) for i,t in enumerate(support['trials'])]


def ranking_key(t):
    return (-t['added_curved_points'],tuple(a['component'] for a in t['additions']),t['arms']['c0']['corrected_selection_loss'])


def norescue(case):
    destination=OUT/'raw'/case;destination.mkdir(parents=True,exist_ok=True)
    d,frozen=context(case);records=[]
    for name,kind,old in frozen_bank(case):
        dd=apply_trial(d,old);pair={a:ordinary(dd,kind,a) for a in ARMS}
        first=copy.deepcopy(pair)
        extend=not valid(pair) and min(s['minimum_gate_slack'] for s in pair.values())>=-.25
        if extend:pair={a:ordinary(dd,kind,a,s) for a,s in pair.items()}
        t=dict(old,arms=pair,kind=kind,name=name,unconstrained_initial_arms=first,
               constrained_refinement_attempted=False,ordinary_extra_budget_used=extend)
        for arm,s in pair.items():
            p=paths.build(dd,kind,arm,s['phase_reference'])
            active={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}|{e['candidate_index'] for e in dd['entries']}
            s['corrected_selection_loss']=s['negative_twice_elbo']-(len(set(p.labels)-active))*unused_student_gap(d['model']['nu'])
        t['paired_valid']=qualifies(pair);t['audit']=audit(dd,kind,pair)
        if t['paired_valid']:
            t['coverage']=coverage(dd,kind,pair)
            t['parent_IDs_preserved']=preserve(frozen['reference']['coverage'],t['coverage'])
        else:t['parent_IDs_preserved']=False
        records.append(t);write(destination/'norescue_checkpoint.json',dict(case=case,trials=records))
        print(case,name,'qualified',t['paired_valid'],'retained',t['parent_IDs_preserved'],flush=True)
    eligible=[t for t in records if t['paired_valid'] and t['parent_IDs_preserved']]
    selected=min(eligible,key=ranking_key) if eligible else None
    write(destination/'norescue.json',dict(case=case,trials=records,selected=selected,
        policy='ordinary optimization with matched extra budget; original maximum-points ranking',
        no_GPS_used=True,reference_fallback=selected is None))


def held_indices(p,reference_keep,family):
    held=np.zeros(len(p.keep),bool);train=p.keep.copy()
    for row,sl in zip(p.rows,p.slices,strict=True):
        if row['candidate_index']==family:
            held[sl]=reference_keep[sl]
            train[sl]=False
    assert not np.any(held&train)
    return train,held


def gaussian_prediction(raw,features,prior_precision,training_features,training_weight,sigma):
    gram=np.diag(prior_precision)+training_features.T@(training_weight[:,None]*training_features)
    covariance=np.linalg.inv(gram)
    score,_=predictive_density_reference(raw,features,covariance,sigma)
    marginal=np.diag(sigma**2)+features@covariance@features.T
    dense=float(raw@np.linalg.solve(marginal,raw)+np.linalg.slogdet(marginal)[1]+len(raw)*np.log(2*np.pi))
    assert abs(score-dense)<1e-5
    return score,marginal


def family_prediction(d,kind,arm,saved,reference_keep,family):
    p0=paths.build(d,kind,arm,saved['phase_reference']);mask,held=held_indices(p0,reference_keep,family)
    dd=dict(d,keep=mask,entries=[]);x=np.asarray(saved['endpoint_east_north_km'])
    reference=np.zeros(len(dd['means']))
    for _ in range(5):
        p=paths.build(dd,kind,arm,reference);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        change=float(np.max(abs(phase-reference)));reference=phase
    c=p.calculate(x);g=p.noise_groups[mask]
    weight=dd['powers'][g]*c['noise_precision'][g]/p.point_noise[mask]**2
    raw=c['conditional_residual_hz'][held]
    sigma=p.point_noise[held]*np.sqrt(2/dd['powers'][p.noise_groups[held]])
    score,cov=gaussian_prediction(raw,c['features'][held],c['coefficient_prior_precision'],c['features'][mask],weight,sigma)
    geometry=geometry_features(p,x,0.)
    max_sd=float(np.sqrt(np.diag(cov)).max())
    visible=bool(np.min(geometry['elevation'][held])>=0)
    qualified=bool(change<=.01 and visible and max_sd<PERIOD/20)
    # Mixture applied to the whole held family. No per-point pruning or
    # unmodeled comparison of losses on different observation sets.
    clutter=2*int(held.sum())*np.log(PERIOD)
    mixture=float(-2*np.logaddexp(np.log(.95)-score/2,np.log(.05)-clutter/2))
    ids=[oid for i,sl in zip(p.members,p.slices,strict=True) for oid,use in zip(p.scan.tracks[i]['observation_ids'],held[sl],strict=True) if use]
    return dict(family=int(family),norad=int(p.scan.norads[family]),points=int(held.sum()),observation_ids=ids,
        score=score,mixture_score=mixture,clutter_score=clutter,qualified=qualified,
        maximum_marginal_SD_hz=max_sd,phase_change_s=change,
        raw_RMS_hz=float(np.sqrt(np.mean(raw**2))),raw_residual_hz=raw,
        marginal_SD_hz=np.sqrt(np.diag(cov)),times=p.flat_times[held],
        conditional_covariance_keeps_phase_orbit_radio_and_fragment=True,
        no_held_family_points_used_for_nuisance_update=True,
        position_is_full_fit_endpoint_not_cross_validated=True)


def rank(case):
    destination=OUT/'raw'/case;d,frozen=context(case);new=read(destination/'norescue.json')
    bank=[dict(name='reference',kind='default',node=d['node'],mask=d['keep'],means=d['means'],entries=d['entries'],arms=d['arms'],additions=[],added_curved_points=0,coverage=frozen['reference']['coverage'])]
    for name,kind,t in frozen_bank(case):
        if not qualifies(t['arms']):continue
        dd=apply_trial(d,t);cov=coverage(dd,kind,t['arms'])
        if preserve(frozen['reference']['coverage'],cov):bank.append(dict(t,name='rescued_'+name,kind=kind,coverage=cov))
    bank.extend(dict(t,name='ordinary_'+t['name']) for t in new['trials'] if t['paired_valid'] and t['parent_IDs_preserved'])
    sizes={}
    for r,sl in zip(d['base'].rows,d['base'].slices,strict=True):
        sizes[r['candidate_index']]=sizes.get(r['candidate_index'],0)+int(d['keep'][sl].sum())
    families=sorted([j for j,n in sizes.items() if n],key=lambda j:(-sizes[j],j))[:3]
    results=[]
    for t in bank:
        dd=apply_trial(d,t);byarm={a:[family_prediction(dd,t['kind'],a,t['arms'][a],d['keep'],j) for j in families] for a in ARMS}
        scores={a:float(sum(v['mixture_score'] for v in values)) for a,values in byarm.items()}
        results.append(dict(name=t['name'],predictions=byarm,scores=scores,qualified=all(v['qualified'] for values in byarm.values() for v in values)))
        write(destination/'ranking_checkpoint.json',dict(case=case,results=results))
        print(case,'rank',t['name'],scores,flush=True)
    base=results[0];threshold=float(2*np.log(max(1,len(bank))))
    # Same branch required to improve the fixed evidence in both c arms.
    passing=[r for r in results[1:] if r['qualified'] and base['qualified'] and all(base['scores'][a]-r['scores'][a]>threshold for a in ARMS)]
    best=min(passing,key=lambda r:(r['scores']['c0'],r['name'])) if passing else base
    selected=next(t for t in bank if t['name']==best['name'])
    for r in results:
        for arm in ARMS:
            assert [v['observation_ids'] for v in r['predictions'][arm]]==[v['observation_ids'] for v in base['predictions'][arm]]
    write(destination/'ranking.json',dict(case=case,results=results,bank=bank,selected=selected,
        families=families,threshold=threshold,selector='paired improvement in common-family composite predictive score',
        not_full_cross_validation='position and nomination came from full evidence; only nuisance refit excludes family',
        Gaussian_empirical_Bayes_approximation=True,not_a_calibrated_probability_or_full_joint_evidence=True,
        no_GPS_used=True))


def worker(case,stage):
    folder=OUT/'raw'/case;folder.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    with (folder/(stage+'.log')).open('w') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded 600 second stage')));signal.alarm(600)
            globals()[stage](case);status=dict(case=case,status='complete',seconds=time.monotonic()-start)
        except Exception as exc:
            import traceback
            status=dict(case=case,status='failed',error=repr(exc),traceback=traceback.format_exc(),seconds=time.monotonic()-start)
        finally:signal.alarm(0)
    write(folder/(stage+'_status.json'),status);return status


def freeze():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=CASES,development=CASES[:3],positive_controls=CASES[3:],
        predeclared_same_site_cases_not_blind_validation=True,causal_catalogue_only=True,
        regional_center=[37.906,-122.545],region_width_km=25,cold_start=[0,0],
        base_budget='5 phase rounds x48 iterations',extra_budget='5 rounds x40; same near-feasible -.25 trigger; ordinary SLSQP without residual constraints',
        hypothesis_bank='all archived default and support whole-curve trials; no new satellites',
        ranking='three largest reference curved families by original point count; fixed held IDs; conditional full covariance; .95 family signal + .05 uniform clutter',
        ranking_selection='same branch improves both c arms by >2log(number of branches); c0 composite score tie-break',
        caveat='full-fit position is reused for held-family nuisance prediction; not full cross-validation',
        no_GPS_in_inference=True,no_new_RF=True,no_ALGO_release=True,
        source_sha256=sha(Path(__file__)),inputs={c:sha(SOURCE/'raw'/c/'result.json') for c in CASES})
    file=OUT/'protocol.json'
    if file.exists():assert read(file)==protocol,'preserve frozen protocol'
    else:write(file,protocol)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['norescue','rank']);args=parser.parse_args();freeze()
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows=[]
        for future in as_completed([pool.submit(worker,c,args.stage) for c in CASES]):
            row=future.result();rows.append(row);print(row,flush=True)
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
