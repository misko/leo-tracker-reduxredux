"""Qualify neighbor TLE forecasts before any regional position experiment."""

import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from ds23_neighbor_phase_forecast import attach_orbits, qualify
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_ds23_combined_recovery_full import OUT as COMBINED

OUT = ROOT/'reports/2026_10_20_ds23_neighbor_phase_forecast'
CASES = ['DS23-0202', 'DS23-0274', 'DS23-0293', 'DS23-0240', 'DS23-0112', 'DS23-0114']


def run(case):
    target = OUT/(case+'.json')
    if target.exists():
        return read(target)
    *_, signed, _ = context_signed(case)
    root = Path(read(COMBINED/'protocol.json')['input_roots'][case])/'causal_phase_history'
    hp, fp = root/(case+'.json'), root/(case+'_forecast.json')
    history, forecast = read(hp), read(fp)
    if sha(hp) != forecast['history_sha256']:
        raise ValueError('causal TLE forecast history changed')
    rows = attach_orbits(forecast['transitions'], history['past_versions'])
    selection = qualify(rows, forecast['temporal_split_boundary_ns'], forecast['prefix_distribution'],
        forecast['all_past_distribution'], signed['selection'] if signed['accepted'] else {})
    record = dict(case=case, selection=selection, transitions=len(rows), history_sha256=sha(hp), forecast_sha256=sha(fp),
        all_TLE_versions_pre_scan=True, no_RF_or_GPS_or_position_input_to_predictor=True,
        all_causal_candidates_used_not_only_associated_satellites=True,
        no_position_or_prior_mean_modified_yet=True)
    write(target, record)
    print(case, selection, flush=True)
    return record


def main():
    OUT.mkdir(exist_ok=True)
    protocol = dict(cases=CASES, neighbor_models=['global', 'orbital_plane'],
        fixed_kernel=dict(age_decay_seconds=21600, maximum_age_seconds=43200, minimum_lag_seconds=300,
            inclination_width_deg=1, RAAN_width_deg=10, mean_motion_width_rev_per_day=.1),
        strict_chronological_and_target_satellite_disjoint_validation=True,
        TLE_innovations_are_imperfect_orbit_error_proxies=True,
        pre_RF_only=True, no_GPS_or_RF_targets=True, no_position_rerun_until_prior_qualification=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_neighbor_phase_forecast.py']})
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('neighbor TLE predictor experiment changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in CASES])]
    write(OUT/'evaluation.json', dict(rows=rows, qualified=sum(r['selection']['qualified'] for r in rows),
        all_terminal=True, no_position_accuracy_claim=True))


if __name__ == '__main__':
    main()
