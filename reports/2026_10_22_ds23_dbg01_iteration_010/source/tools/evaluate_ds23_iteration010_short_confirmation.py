"""Replay the sealed20-scan policy before report-only geographic evaluation."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import repair_ds23_iteration010_empty_prediction as repair
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from audit_ds23_algo01_coverage import retained_metrics
from report_ds23_dbg01_iteration_005 import result_row
from run_algo01_ds23_sample import read,write,sha

OUT=repair.confirmation.runner.RAW/'short_confirmation20_evaluation'


def reported_fit(problem,saved):
    if 'final_phase_change_s' in saved:return saved
    state=problem.state(np.asarray(saved['endpoint_east_north_km']))
    change=float(np.max(abs(np.asarray(state['phases'])[problem.labels]-np.asarray(saved['phase_reference']))))
    return dict(saved,final_phase_change_s=change,missing_phase_refresh_metadata_recovered_at_frozen_endpoint=True)


def one(case):
    repair.confirmation.configure();d,original,_,_=repair.confirmation.incumbent_parent(case)
    source=repair.OUT/'short_whole_curves'/(case+'.json');record=read(source);selected=record['selected'];checks=[];baseline_arms={}
    for a,saved in d['arms'].items():
        p=repair.confirmation.experiment.binding.paths.build(d,'default',a,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
        delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-5:raise ValueError('incumbent confirmation endpoint replay failed')
        baseline_arms[a]=reported_fit(p,saved)
        checks.append(dict(arm=a,method='incumbent',bound_difference=delta))
    original_problem=repair.confirmation.experiment.binding.paths.build(d,'default','c0',d['arms']['c0']['phase_reference'])
    if selected:
        dd,added=repair.confirmation.experiment.promote(d,original_problem,selected['offers']);dd['original_protected']=set(record['original_protected'])
        if not np.array_equal(dd['powers'][:len(d['powers'])],d['powers']):raise ValueError('confirmation changed incumbent powers')
        arms=selected['arms'];cov=selected['coverage']
        for a,s in arms.items():
            p=repair.confirmation.experiment.binding.paths.build(dd,'support',a,s['phase_reference']);x=np.asarray(s['endpoint_east_north_km'])
            delta=p.calculate(x)['negative_twice_elbo']-s['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('confirmation bound replay failed')
            assert_curved_gate_replay(s['gates'],retained_metrics(p,x))
            replay=repair.confirmation.experiment.binding.paths.coverage(dd,'support',a,s)
            if set(replay['accepted_observation_ids'])!=set(cov[a]['accepted_observation_ids']):raise ValueError('confirmation membership changed')
            if not set(original[a]['accepted_observation_ids'])<=set(replay['accepted_observation_ids']):raise ValueError('confirmation lost an incumbent ID')
            checks.append(dict(arm=a,bound_difference=delta,all_parent_IDs_preserved=True,exact_membership_replayed=True))
    else:arms=baseline_arms;cov=original
    rows=[]
    for method,pair,coverage in [('Incumbent',baseline_arms,original),('Short whole-curve policy',arms,cov)]:
        for a,s in pair.items():rows.append(dict(result_row(case,method,a,s,coverage[a],original[a]),
            selected_recovery=method!='Incumbent' and selected is not None,
            added_curved_points=selected['added_curved_points'] if method!='Incumbent' and selected else 0))
    return dict(case=case,rows=rows,checks=checks,selected=selected is not None,source_sha256=sha(source))


def summarize(rows):
    result=[]
    for arm in ['c0','fitted_c']:
        for method in ['Incumbent','Short whole-curve policy']:
            sample=[r for r in rows if r['arm']==arm and r['method']==method];errors=np.array([r['position_error_km'] for r in sample])
            control={r['case']:r['position_error_km'] for r in rows if r['arm']==arm and r['method']=='Incumbent'}
            delta=np.array([r['position_error_km']-control[r['case']] for r in sample]);total=sum(r['all_GLRT'] for r in sample);associated=sum(r['associated_points'] for r in sample)
            result.append(dict(arm=arm,method=method,cases=len(sample),selected_cases=sum(r['selected_recovery'] for r in sample),
                mean_error_km=float(errors.mean()),median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9)),maximum_error_km=float(errors.max()),
                associated_points=associated,total_GLRT=total,associated_percent=100*associated/total,
                mean_RMS_hz=float(np.mean([r['RMS_hz'] for r in sample])),new_curved_points=sum(r['added_curved_points'] for r in sample),
                regressions_over100m=int((delta>.1).sum()),regressions_over500m=int((delta>.5).sum()),
                unchanged_cases=int((abs(delta)<1e-6).sum())))
    return result


def main():
    assert read(repair.OUT/'execution.json')['all_passed']
    OUT.mkdir(exist_ok=True)
    if (OUT/'evaluation.json').exists():raise FileExistsError('preserve confirmation evaluation')
    cases=read(repair.OUT/'protocol.json')['cases']
    with ProcessPoolExecutor(max_workers=6) as pool:records=list(pool.map(one,cases))
    rows=[r for record in records for r in record['rows']];summary=summarize(rows)
    import report_ds23_dbg01_iteration_001 as figures
    figures.csv_write(OUT/'positions.csv',rows);figures.csv_write(OUT/'summary.csv',summary)
    write(OUT/'evaluation.json',dict(cases=cases,all20retained=True,records=records,summary=summary,
        all_selected_bounds_gates_and_memberships_replayed=True,no_full_DS23_or_new_location_claim=True,
        GPS_used_only_after_RF_selection=True,source_sha256=sha(Path(__file__))))
    print(summary,flush=True)


if __name__=='__main__':main()
