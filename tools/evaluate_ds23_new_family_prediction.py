"""Complete-population accuracy and unique-ID coverage for frozen predictions."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import csv

import numpy as np

import run_ds23_dbg01_iteration_007 as runner
from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_phase_refreshed import extend_associations
from dbg01_unassociated import ownership
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read,write,sha

RAW=runner.RAW
FULL=RAW/'new_family_full_DS23'
OUT=RAW/'new_family_evaluation'


def coverage(d,arm,saved,entries):
    p=runner.engine.baseline.build(d,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    extended=extend_associations(p,x,retained_metrics(p,x));lookup={t['key']:t for t in d['scan'].tracks}
    new_rows=[dict(e,compatible=True,association_source='grouped_new_family_prediction') for e in entries]
    new_ids=ownership(new_rows);rows=[];collisions=[]
    for r in extended['tracks']:
        row=dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids']))
        if not row['compatible']:continue
        if set(row['observation_ids'])&new_ids:
            collisions.append(dict(component=row['component'],norad=row['norad'],points=row['points']))
            continue
        rows.append(row)
    accepted=ownership(rows+new_rows);all_ids={o['observation_id'] for o in d['observations']}
    if not accepted<=all_ids:raise ValueError('association contains synthetic measurement ID')
    return dict(associated=len(accepted),percent=100*len(accepted)/len(all_ids),total_GLRT=len(all_ids),
        associated_tracks=len(rows)+len(new_rows),accepted_observation_ids=sorted(accepted),
        associations=dict(tracks=rows+new_rows),conflicting_postfit_only_extensions_omitted=collisions)


def evaluate_case(case,source):
    runner.configure();d=runner.engine.current_setup(case);root=Path(source)
    original=read(root/case/'inventory.json')['arms'];result=read(root/case/'result.json');rows=[];details={}
    for arm,saved in d['arms'].items():
        for method in ['incumbent','phase_only','physical_prior']:
            trial=result.get('trials',{}).get(method);accepted=bool(method!='incumbent' and trial and trial['paired_valid'])
            fit=trial['arms'][arm] if accepted else saved;entries=trial['entries'] if accepted else []
            cov=coverage(d,arm,fit,entries) if accepted else original[arm]
            if accepted:
                if abs(fit['audit']['direct_predictive_density_difference'])>2e-5 or fit['audit']['original_curved_calibration_coefficient_difference']>1e-12:raise ValueError('saved density or calibration audit failed')
                if fit['active_points']!=original[arm]['active_curved_points']:raise ValueError('original calibration point count changed')
            lost=set(original[arm]['accepted_observation_ids'])-set(cov['accepted_observation_ids'])
            details[arm+'_'+method]=cov
            rows.append(dict(case=case,arm=arm,method=method,accepted=accepted,
                status=result.get('status'),position_error_km=position_error(fit['endpoint_latlon']),
                east_km=fit['endpoint_east_north_km'][0],north_km=fit['endpoint_east_north_km'][1],
                frequency_RMS_hz=fit['RMS_hz'],associated_points=cov['associated'],total_GLRT=cov['total_GLRT'],
                associated_percent=cov['percent'],associated_fragments=cov['associated_tracks'],
                points_per_fragment=cov['associated']/cov['associated_tracks'],
                active_curved_points=original[arm]['active_curved_points'],
                predictive_points=original[arm]['predictive_points']+sum(e['points'] for e in entries),
                new_prediction_points=sum(e['points'] for e in entries),original_accepted_points_lost=len(lost),
                new_family_norads=sorted({e['norad'] for e in entries}),
                archived_phase_exception=(not accepted and max(abs(np.asarray(fit['state']['phases'])))>15.000001)))
    write(OUT/'cases'/(case+'.json'),dict(case=case,rows=rows,coverage=details))
    return rows


def summary(rows,bootstrap_count=10000):
    cases=sorted({r['case'] for r in rows});lookup={(r['case'],r['arm'],r['method']):r for r in rows}
    rng=np.random.default_rng(2026102207);samples=rng.integers(0,len(cases),size=(bootstrap_count,len(cases)))
    result=[]
    for arm in ['c0','fitted_c']:
        old=np.array([lookup[c,arm,'incumbent']['position_error_km'] for c in cases])
        for method in ['incumbent','phase_only','physical_prior']:
            group=[lookup[c,arm,method] for c in cases];error=np.array([r['position_error_km'] for r in group]);gain=old-error
            boot_mean=gain[samples].mean(axis=1);boot_median=np.median(old[samples],axis=1)-np.median(error[samples],axis=1)
            total=sum(r['total_GLRT'] for r in group);associated=sum(r['associated_points'] for r in group)
            result.append(dict(arm=arm,method=method,cases=len(cases),mean_error_km=float(error.mean()),median_error_km=float(np.median(error)),
                p90_error_km=float(np.quantile(error,.9)),p95_error_km=float(np.quantile(error,.95)),maximum_error_km=float(error.max()),
                mean_improvement_km=float(gain.mean()),mean_improvement_scan_bootstrap95_km=np.quantile(boot_mean,[.025,.975]),
                median_improvement_scan_bootstrap95_km=np.quantile(boot_median,[.025,.975]),
                improved_over1m=int(sum(gain>.001)),worsened_over1m=int(sum(gain<-.001)),unchanged_within1m=int(sum(abs(gain)<=.001)),
                regressions_over500m=int(sum(gain<-.5)),accepted_cases=sum(r['accepted'] for r in group),
                associated_points=associated,total_GLRT=total,associated_percent=100*associated/total,
                new_prediction_points=sum(r['new_prediction_points'] for r in group),
                original_accepted_points_lost=sum(r['original_accepted_points_lost'] for r in group),
                mean_frequency_RMS_hz=float(np.mean([r['frequency_RMS_hz'] for r in group]))))
    return result


def main():
    runner.configure();OUT.mkdir(exist_ok=True);(OUT/'cases').mkdir(exist_ok=True)
    execution=read(FULL/'execution.json');assert execution['all_terminal'] and len(execution['rows'])==410
    cases=read(FULL/'protocol.json')['cases'];rows=[]
    record=dict(cases=cases,source_sha256=sha(Path(__file__)),pipeline_execution_sha256=sha(FULL/'execution.json'),workers=16,
        evaluate_every_available_scan_including_failures_and_regressions=True,no_new_inference_or_GPS_selection=True,
        new_likelihood_IDs_take_precedence_over_conflicting_postfit_only_extensions=True,
        conflict_policy_removes_no_original_likelihood_measurement=True,
        scan_bootstrap_count=10000,scan_bootstrap_seed=2026102207,
        bootstrap_is_descriptive_not_new_location_or_temporal_independence_guarantee=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve full evaluation')
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=16) as pool:
        for future in as_completed([pool.submit(evaluate_case,c,str(FULL)) for c in cases]):
            group=future.result();rows.extend(group);print(group[0]['case'],'evaluated',flush=True)
    rows.sort(key=lambda r:(r['case'],r['arm'],r['method']));summaries=summary(rows)
    bench={(r['case'],r['arm']):float(r['policy_error_km']) for r in csv.DictReader(runner.engine.baseline.BENCHMARK.open()) if r['policy']=='equal_assignment_priors'}
    if any(abs(r['position_error_km']-bench[r['case'],r['arm']])>1e-8 for r in rows if r['method']=='incumbent'):raise ValueError('baseline selection differs from published benchmark')
    write(OUT/'evaluation.json',dict(rows=rows,summary=summaries,available=410,total_manifest=413,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        no_point_or_scan_removed_from_comparison=True,full_incumbent_error_reproduction_verified=True))
    print('FULL SUMMARY',summaries,flush=True)


if __name__=='__main__':main()
