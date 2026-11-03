"""Bounded, paired-c calibration test of repeatedly frame-linked curve biases."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import bind_run_directory, load_scan, pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_epoch_linked_bias import linked_covariance
from ds23_frame_registration import circular_line
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT/'reports/2026_10_19_algo02_ds23_full'
REGISTRATION = ROOT/'reports/2026_10_19_algo03_frame_registration_v2'
OUT = ROOT/'reports/2026_10_19_algo03_epoch_linked_bias'


def verified_edges(p, rows):
    active = {r['component']:set(np.round(p.scan.tracks[i]['times'][p.keep[sl]],6))
              for r,i,sl in zip(p.rows,p.members,p.slices,strict=True)}
    labels = {r['component']:r['candidate_index'] for r in p.rows}
    groups = {}
    for r in rows:
        owners = r['curved_anchor_components']
        if len(owners)!=2 or any(owner not in active for owner in owners):
            continue
        if labels[owners[0]]!=labels[owners[1]]:
            continue
        if any(round(r['time_s'],6) not in active[owner] for owner in owners):
            continue
        edge = tuple(sorted(owners))
        groups.setdefault(edge,[]).append(r)
    qualified=[]
    for edge, group in groups.items():
        visits={r['visit_index'] for r in group}
        times=np.array([r['time_s'] for r in group])
        if len(visits)<6 or np.ptp(times)<5:
            continue
        line=circular_line(times,[r['differential_cfo_hz'] for r in group],tolerance_hz=500.)
        if line is None or np.mean(line['inliers'])<.8:
            continue
        qualified.append(dict(edge=edge,visits=len(visits),span_s=float(np.ptp(times)),
            native_frame_match_rows=group,relative_carrier_line=line))
    return qualified


def refit(scan,node,keep,arm,powers,means,model,edges):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
        covariance=linked_covariance([r['component'] for r in p.rows],edges)
        p.constants=p.constants@np.linalg.cholesky(covariance)/300.
        result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phases=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(max(abs(phases-reference)))))
        reference=phases
    c=p.calculate(x)
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,
        phase_reference=p.reference,state=p.state(x),gates=retained_metrics(p,x),
        active_points=int(keep.sum()),negative_twice_elbo=c['negative_twice_elbo'],
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        final_phase_change_s=history[-1]['phase_change_s'],bias_covariance_hz2=covariance)


def run(case):
    bind_run_directory(SOURCE);scan=load_scan(SOURCE,case)
    original=read(SOURCE/case/'result.json');old=read(SOURCE/case/'algo02_result.json')
    node=original['final_node'];keep=np.asarray(old['mask'],bool);powers=np.asarray(old['weights'])
    base=problem(scan,node,'c0',keep);model=old['hyperparameters_from_pre_RF_TLE_only']
    _,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    evidence=read(REGISTRATION/(case+'.json'));receipts=verified_edges(base,evidence['pairs'])
    edges=[r['edge'] for r in receipts]
    if not edges:
        write(OUT/(case+'.json'),dict(case=case,qualified_edges=[],no_change=True))
        return dict(case=case,edges=0)
    started=time.monotonic()
    pair={arm:refit(scan,node,keep,arm,powers,means,model,edges) for arm in ('c0','fitted_c')}
    result=dict(case=case,qualified_edges=receipts,trial_curved_arms=pair,
        baseline_curved_arms=old['curved_arms'],paired_gates_valid=pair_passes(pair),
        same_observations_mask_aliases_satellite_labels_noise_and_search_budget=True,
        marginal_bias_sigma_hz=300.,within_connected_common_carrier_sigma_hz=30.,
        linear_points_not_used_for_calibration=True,no_new_measurements_or_double_counting=True,
        no_GPS_used=True,no_position_prior_from_other_scans=True,
        registration_sha256=sha(REGISTRATION/(case+'.json')),
        baseline_sha256=sha(SOURCE/case/'algo02_result.json'),seconds=time.monotonic()-started)
    write(OUT/(case+'.json'),result)
    return dict(case=case,edges=len(edges),paired_valid=result['paired_gates_valid'],seconds=result['seconds'])


def main():
    if OUT.exists():
        raise FileExistsError('preserve paired hypothesis test')
    OUT.mkdir()
    cases=['DS23-0202','DS23-0274']
    write(OUT/'protocol.json',dict(cases=cases,workers=2,development_only=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_epoch_linked_bias.py'),
        eligibility='six same-native-frame matches over at least five seconds, both active curved originals, same RF and nomination; 80% within 500 Hz of small-drift line',
        no_new_GPS_position_TLE_or_satellite_prior=True,
        fixed_engineering_bias_scales_hz=[300.,30.],no_GPS_hyperparameter_selection=True,
        paired_c0_fitted_c_same_data_labels_noise_and_cold_search_budget=True))
    results=[]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for future in as_completed([executor.submit(run,c) for c in cases]):
            result=future.result();results.append(result);print(result,flush=True)
    write(OUT/'execution.json',dict(results=results))


if __name__=='__main__':
    main()
