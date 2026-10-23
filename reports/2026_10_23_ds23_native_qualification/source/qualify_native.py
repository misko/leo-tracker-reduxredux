"""One RF-selected whole-path exclusion pass; no evaluation GPS in policy."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import contextlib
import json
import signal
import time
import traceback
import numpy as np
import mechanism as mech
from probe_algo03_feasible_recovery import gate_slacks
from run_algo01_ds23_sample import read,write,sha

OUT=Path(__file__).resolve().parents[1]
FROZEN=mech.FROZEN
ARMS=mech.ARMS
CONTROLS=['DS23-0041','DS23-0272','DS23-0259']


def bad_new_paths(entries,parent_entries,slacks_by_arm):
    """Union paired RF failures; original entries can never be excluded."""
    old={e['component'] for e in parent_entries}
    new={e['component'] for e in entries}-old
    rejected={};unchangeable={}
    for arm,slacks in slacks_by_arm.items():
        for key,value in slacks.items():
            if not np.isfinite(value):raise ValueError('nonfinite gate slack')
            if value>=0:continue
            matching=[name for name in new if key.startswith(name+'/linear/')]
            if matching:
                assert len(matching)==1
                rejected.setdefault(matching[0],{})[arm+':'+key]=value
            else:unchangeable[arm+':'+key]=value
    return sorted(rejected),rejected,unchangeable


def eligible(rescue):return bool(rescue and rescue.get('eligible',False))


def protected_exclusion(entries,keys,parent_coverage):
    removed=[e for e in entries if e['component'] in keys]
    protected=set().union(*(set(v['accepted_observation_ids']) for v in parent_coverage.values()))
    assert all(not protected.intersection(e['observation_ids']) for e in removed),'exclusion touches parent IDs'
    return [e for e in entries if e['component'] not in keys],removed


def paired_accept(pair,cov,parent_cov):
    return bool(mech.exp.qualifies(pair) and mech.exp.preserve(parent_cov,cov))


def run(case):
    folder=OUT/'raw'/case;folder.mkdir(parents=True,exist_ok=True)
    destination=folder/'result.json'
    if destination.exists():return {'case':case,'status':read(destination)['status'],'reused':True}
    started=time.monotonic()
    result=dict(case=case,status='pending',candidate_accepted=False,attempted_refit=False)
    with (folder/'run.log').open('w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        try:
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s bounded case')));signal.alarm(240)
            parent,kind,paths,frozen=mech.load(case)
            g=frozen['ordinary_graph'];result['graph_parent']=g
            result['previous_final']=frozen['final']
            rescue=read(FROZEN/'raw'/case/'native_feasibility'/(case+'.json'))
            result['original_rescue_eligible']=eligible(rescue)
            result['original_rescue_accepted']=bool(rescue.get('accepted'))
            result['policy_final']=g if eligible(rescue) else frozen['final']
            result['disable_rescue_final']=result['policy_final']
            if not eligible(rescue):
                result.update(status='unchanged_control',reason='outside frozen native-rescue eligibility; exact original outcome reused')
                return result
            full=mech.append(parent,paths)
            primary=read(FROZEN/'raw'/case/'native'/(case+'.json'))['methods']['persistent5s']
            slacks={};audits={}
            for arm,saved in primary['arms'].items():
                p=mech.exp.paths.build(full,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
                delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
                assert abs(delta)<1e-5,'primary objective replay changed'
                slacks[arm]=gate_slacks(p,x,full['entries'])
                audits[arm]=dict(objective_difference=delta,ids=mech.id_audit(p,full['entries']))
            keys,reasons,unchangeable=bad_new_paths(full['entries'],parent['entries'],slacks)
            reduced_entries,removed=protected_exclusion(full['entries'],keys,g['coverage'])
            result.update(original_primary_arms=primary['arms'],primary_slacks=slacks,primary_audits=audits,
                excluded_keys=keys,excluded_entries=removed,RF_exclusion_reasons=reasons,
                failures_on_protected_evidence=unchangeable,
                original_new_paths=len(paths),original_new_points=sum(len(f['times']) for f in paths),
                excluded_new_points=sum(e['points'] for e in removed))
            if not keys:
                result.update(status='graph_fallback_no_new_path_failure',reason='no failing new individual path to exclude; original evidence protected')
                return result
            if len(reduced_entries)==len(parent['entries']):
                result.update(status='graph_fallback_no_new_paths_left',reason='all new paths excluded; retain graph parent')
                return result
            changed=dict(full,entries=reduced_entries);result['attempted_refit']=True
            pair={arm:mech.refit(parent,changed,kind,arm,1.) for arm in ARMS}
            cov=mech.exp.coverage(changed,kind,pair)
            accepted=paired_accept(pair,cov,g['coverage'])
            result.update(refit_arms=pair,refit_coverage=cov,remaining_entries=reduced_entries,
                paired_gates_pass=mech.exp.qualifies(pair),original_parent_IDs_preserved=mech.exp.preserve(g['coverage'],cov),
                candidate_accepted=accepted,status='accepted' if accepted else 'graph_fallback_refit_rejected')
            if accepted:
                result['policy_final']=dict(arms=pair,coverage=cov,kind=kind,node=parent['node'],mask=parent['keep'],
                    means=parent['means'],entries=reduced_entries)
            # Identical full masks for diagnostic score comparison only.
            result['common_full_mask_scores']={}
            for arm,saved in pair.items():
                p=mech.exp.paths.build(full,kind,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
                result['common_full_mask_scores'][arm]=dict(objective=p.calculate(x)['negative_twice_elbo'],
                    gate_slacks=gate_slacks(p,x,full['entries']))
            if case=='DS23-0365':
                prior=read(Path('/srv/bulk/leo/research/algo04-native-mechanisms-20261023/solver0365/followup/results.json'))
                assert keys==[prior['removed_entry']['component']]
                result['development_canary_max_difference']={a:float(np.max(abs(np.asarray(pair[a]['endpoint_east_north_km'])-prior['ablation'][a]['summary']['endpoint_east_north_km']))) for a in ARMS}
                assert max(result['development_canary_max_difference'].values())<1e-7
        except Exception as exc:
            result.update(status='execution_failure',candidate_accepted=False,error=repr(exc),traceback=traceback.format_exc())
            if 'graph_parent' in result:result['policy_final']=result['graph_parent']
        finally:
            signal.alarm(0);result['seconds']=time.monotonic()-started
            write(destination,result)
    return result


def worker(case):
    r=run(case)
    return {k:r[k] for k in ['case','status','seconds'] if k in r}


def freeze():
    available=[];cases=[];inputs={}
    for f in sorted((FROZEN/'raw').glob('*/result.json')):
        d=read(f);case=d['case'];available.append(case)
        inputs[str(f)]=sha(f)
        rescue=f.parent/'native_feasibility'/(case+'.json')
        if rescue.exists() and eligible(read(rescue)):cases.append(case)
    assert len(available)==410 and len(cases)==29
    for case in cases+CONTROLS:
        for f in [FROZEN/'raw'/case/'native_feasibility'/(case+'.json'),FROZEN/'raw'/case/'native'/(case+'.json'),FROZEN/'raw'/case/'native'/(case+'_persistent5s_selection.json')]:inputs[str(f)]=sha(f)
    protocol=dict(eligible_cases=cases,controls=CONTROLS,available=available,manifest_total=413,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        trigger='exact original RF-only near-feasible native rescue eligibility; no GPS case selection',
        exclusion='union across c arms of all negative individual linear gate slacks on newly added whole native paths only',
        attempts=1,no_iterative_pruning=True,no_constraint_rescue=True,no_original_ID_removal=True,
        refit='cold regional center [0,0], zero phase reference, five rounds x48 ordinary iterations',
        comparator_budget='previous constrained rescue five rounds x40 from ordinary endpoint; starts/budgets differ across algorithms, matched within c arms',
        acceptance='unchanged paired gates, phase convergence <=.01s, every graph-parent accepted ID retained',
        fallback='graph parent on no removable new path, all new paths removed, or failed paired refit',
        comparisons=['published reference','ordinary graph plus prior native policy','disable native rescue','one-pass exclusion'],
        full_cohort='assembled410 comparison; only29eligible plus3control cases inspected; all other endpoints reused exactly',
        fixed_causal_catalogue_aliases_noise_priors=True,no_GPS_inference_no_future_TLE_no_new_RF=True,
        region_center=[37.906,-122.545],region_km=25,case_cap_s=240,
        source_hashes={str(Path(__file__)):sha(Path(__file__)),str(Path(mech.__file__)):sha(Path(mech.__file__))},input_hashes=inputs)
    OUT.mkdir(parents=True,exist_ok=True);f=OUT/'protocol.json'
    if f.exists():assert read(f)==protocol,'frozen protocol changed'
    else:write(f,protocol)
    return protocol


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=6);parser.add_argument('--freeze-only',action='store_true');args=parser.parse_args()
    protocol=freeze()
    if not args.freeze_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(worker,c) for c in protocol['eligible_cases']+protocol['controls']]):print(future.result(),flush=True)
