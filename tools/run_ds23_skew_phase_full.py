"""Full DS23 confirmation of the unchanged asymmetric phase-prior candidate."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

from run_algo01_ds23_sample import ROOT,read,write,sha
from probe_algo03_frame_peak_recovery import SOURCE

OUT=ROOT/'reports/2026_10_20_ds23_skew_phase_full'


def initialize():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    (OUT/'qualification').mkdir(parents=True,exist_ok=True)
    (OUT/'position').mkdir(parents=True,exist_ok=True)
    previous=read(ROOT/'reports/2026_10_20_ds23_causal_phase_location_full/protocol.json')
    cache={}
    for position,qualification in [
        (ROOT/'reports/2026_10_20_ds23_skew_phase_position',ROOT/'reports/2026_10_20_ds23_skew_phase_prior'),
        (ROOT/'reports/2026_10_20_ds23_skew_phase_validation/position',ROOT/'reports/2026_10_20_ds23_skew_phase_validation/qualification')]:
        for case in previous['cases']:
            p,q=position/(case+'.json'),qualification/(case+'.json')
            if p.exists():
                if case in cache:raise ValueError('development and confirmation recordings overlap')
                cache[case]=dict(position=str(p.relative_to(ROOT)),qualification=str(q.relative_to(ROOT)),
                    position_sha256=sha(p),qualification_sha256=sha(q))
    sources=[ROOT/'tools'/name for name in ('ds23_skew_phase_prior.py','ds23_skew_bound.py',
        'ds23_skew_phase_problem.py','probe_ds23_skew_phase_prior.py','probe_ds23_skew_phase_position.py')]
    protocol=dict(cases=previous['cases'],population=previous['population'],unavailable=previous['unavailable'],
        prior_cases=sorted(cache),additional_confirmation=sorted(set(previous['cases'])-set(cache)),cache=cache,
        same_rule_as_44_development_and_20_confirmation_recordings=True,
        adaptive_regressions_preserved_not_excluded=True,
        unchanged_original_ALGO02_observations_masks_assignments_aliases_and_weights=True,
        c0_and_fitted_c_share_priors_masks_and_5x48_budgets=True,
        matched_scalar_symmetric_control_included_for_every_qualified_trial=True,
        no_point_trimming_or_gate_relaxation=True,no_current_RF_GPS_in_prior_learning=True,
        failed_new_trials_keep_original_ALGO02_and_denominator=True,
        goal_requires_full_DS23_mean_and_median_half_km_not_just_subset_improvement=True,
        publication_requires_mean_and_median_improve_in_both_c_arms_on_full_and_remaining340=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        driver_sha256=sha(Path(__file__)),workers=20,
        reads_only_saved_GLRT_tracks_causal_TLE_banks_and_history=True,new_RF_or_IQ_remeasurement=False)
    write(path,protocol);return protocol


def job(case,cache):
    if case in cache:
        record=cache[case]
        for key in ('position','qualification'):
            if sha(ROOT/record[key])!=record[key+'_sha256']:raise ValueError('frozen cached evidence changed')
        return dict(case=case,cached=True,**record)
    import probe_ds23_skew_phase_prior as prior
    import probe_ds23_skew_phase_position as position
    prior.OUT=OUT/'qualification';position.OUT=OUT/'position';position.QUALIFICATION=prior.OUT
    prior.run_case(case)
    result=position.run_case(case)
    result.update(position=str((position.OUT/(case+'.json')).relative_to(ROOT)),
                  qualification=str((prior.OUT/(case+'.json')).relative_to(ROOT)))
    return result


def main():
    protocol=initialize();results=[]
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures={executor.submit(job,case,protocol['cache']):case for case in protocol['cases']}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(completed=len(results),total=len(futures),results=results))
    write(OUT/'execution.json',dict(results=results,all_terminal=True))


if __name__=='__main__':main()
