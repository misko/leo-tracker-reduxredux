"""Qualify orbital harmonics using only pre-RF catalogue histories."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

from ds23_orbital_phase_forecast import qualify,tle_argument_latitude
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_19_algo03_orbital_phase_forecast'


def run(case):
    raw_path=SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path=raw_path.with_name(case+'_forecast.json')
    history=read(raw_path);forecast=read(forecast_path)
    if forecast['history_sha256']!=sha(raw_path):
        raise ValueError('causal history digest changed')
    cutoff=history['cutoff_utc_ns'];lookup={}
    for number,versions in history['past_versions'].items():
        if any(v['epoch']>cutoff or v['collected_utc_ns']>cutoff for v in versions):
            raise ValueError('post-scan TLE in history')
        for k in range(2,len(versions)):
            a,b,c=versions[k-2:k+1]
            if a['epoch']<b['epoch']<c['epoch']<=c['collected_utc_ns'] and a['collected_utc_ns']<=b['collected_utc_ns']<=c['collected_utc_ns']:
                lookup[int(number),c['collected_utc_ns']]=b['lines']
    rows=[]
    for row in forecast['transitions']:
        key=row['norad'],row['validation_time_ns']
        angle=tle_argument_latitude(lookup[key],row['validation_time_ns'])
        rows.append(dict(row,argument_latitude_rad=angle))
    selection=qualify(rows,forecast['temporal_split_boundary_ns'],
                      forecast['prefix_distribution'],forecast['all_past_distribution'])
    write(OUT/(case+'.json'),dict(case=case,selection=selection,transitions=rows,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_orbital_phase_forecast.py'),
        raw_history_sha256=sha(raw_path),causal_forecast_sha256=sha(forecast_path),
        cutoff_utc_ns=cutoff,no_RF_GPS_or_post_scan_TLE_used=True,
        all_regional_candidates_not_RF_selected_satellites=True,
        later_causal_TLE_updates_are_proxies_not_orbit_truth=True))
    result=dict(case=case,qualified=selection['qualified'],
                future_gain=selection.get('future_density_gain'),
                disjoint_gain=selection.get('disjoint_future_density_gain'))
    print(result,flush=True);return result


def main():
    if OUT.exists():
        raise FileExistsError('preserve causal harmonic qualification')
    OUT.mkdir();cases=read(ROOT/'reports/2026_10_19_algo03_frame_predictive_v2/protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,workers=8,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_orbital_phase_forecast.py'),
        widths=[0,2,4],satellite_validation_fold='NORAD modulo 5 equals zero',
        correction_training='earliest 70 percent publication times, remaining satellite folds',
        validation='future publication times, plus future and held-satellite subset',
        complexity_penalty='width log(N) plus squared dimensionless mean coefficients',
        original_phase_scale_and_tail_families_unchanged=True,
        GPS_RF_position_and_current_satellite_selection_absent=True))
    started=time.monotonic();results=[]
    with ProcessPoolExecutor(max_workers=8) as executor:
        for future in as_completed([executor.submit(run,c) for c in cases]):
            results.append(future.result())
    write(OUT/'execution.json',dict(results=results,seconds=time.monotonic()-started,all_terminal=True))


if __name__=='__main__':
    main()
