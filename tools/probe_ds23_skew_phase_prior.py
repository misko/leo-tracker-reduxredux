"""Qualify asymmetric phase priors before any current-scan RF position fit."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

from ds23_skew_phase_prior import qualify
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_skew_phase_prior'


def run_case(case):
    path=OUT/(case+'.json')
    if path.exists():return dict(case=case,cached=True)
    history_path=SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path=history_path.with_name(case+'_forecast.json')
    history=read(history_path);forecast=read(forecast_path)
    assert forecast['strictly_pre_RF'] and forecast['GPS_or_radio_used'] is False
    assert forecast['history_sha256']==sha(history_path)
    cutoff=history['cutoff_utc_ns']
    assert all(v['epoch']<=cutoff and v['collected_utc_ns']<=cutoff for vv in history['past_versions'].values() for v in vv)
    assert all(r['validation_time_ns']<=cutoff for r in forecast['transitions'])
    validation=forecast['distribution_validation'];original=forecast['original_distribution_validation']
    model=(forecast['all_past_distribution'] if validation['count']>=30 and
           validation['negative_twice_log_density']<original['negative_twice_log_density'] else
           dict(shrinkage=0.,multiplier=1.,nu=None))
    selected=qualify(forecast['transitions'],forecast['temporal_split_boundary_ns'],forecast['prefix_distribution'],model)
    write(path,dict(case=case,selection=selected,base_model=model,
        history_sha256=sha(history_path),forecast_sha256=sha(forecast_path),
        cutoff_utc_ns=cutoff,GPS_current_RF_and_selected_satellites_used=False,
        position_not_estimated=True))
    result=dict(case=case,qualified=selected['qualified'],kappa=selected['kappa'])
    print(result,flush=True);return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=read(ROOT/'reports/2026_10_20_ds23_channel_calibration/protocol.json')['cases']
    protocol=dict(cases=cases,mode_is_original_phase_forecast=True,variance_is_original_phase_variance=True,
        one_asymmetry_parameter_learned_from_past_TLEs=True,
        qualification_requires_future_and_satellite_disjoint_gains_over_both_original_and_location_shift=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_skew_phase_prior.py'),
        method_reference='https://research.tilburguniversity.edu/en/publications/on-bayesian-modelling-of-fat-tails-and-skewness/',
        normalization_and_unit_variance_are_explicitly_tested=True,position_not_estimated=True)
    write(OUT/'protocol.json',protocol)
    results=[]
    with ProcessPoolExecutor(max_workers=8) as executor:
        futures={executor.submit(run_case,c):c for c in cases}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],error=repr(exc)))
    write(OUT/'execution.json',dict(results=results,all_terminal=True))


if __name__=='__main__':main()
