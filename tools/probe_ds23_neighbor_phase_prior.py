"""TLE-only neighbor-innovation prior qualification, independent of RF policy."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from ds23_neighbor_phase_forecast import attach_orbits, qualify
from ds23_causal_phase_location import qualify as qualify_location
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_ds23_combined_recovery_full import OUT as COMBINED

OUT = ROOT/'reports/2026_10_20_ds23_neighbor_phase_prior'
CASES = ['DS23-0202', 'DS23-0274', 'DS23-0293', 'DS23-0240', 'DS23-0112', 'DS23-0114']


def inputs(case):
    root = Path(read(COMBINED/'protocol.json')['input_roots'][case])/'causal_phase_history'
    hp, fp = root/(case+'.json'), root/(case+'_forecast.json')
    history, forecast = read(hp), read(fp)
    if sha(hp) != forecast['history_sha256'] or not forecast['strictly_pre_RF'] or forecast['GPS_or_radio_used']:
        raise ValueError('causal history binding failed')
    if any(max(v['epoch'], v['collected_utc_ns']) > history['cutoff_utc_ns']
           for versions in history['past_versions'].values() for v in versions):
        raise ValueError('post-cutoff elements')
    validation, original = forecast['distribution_validation'], forecast['original_distribution_validation']
    effective = validation['count'] >= 30 and validation['negative_twice_log_density'] < original['negative_twice_log_density']
    fallback = dict(shrinkage=0., multiplier=1., nu=None)
    prefix = forecast['prefix_distribution'] if effective else fallback
    full = forecast['all_past_distribution'] if effective else fallback
    location = qualify_location(forecast['transitions'], forecast['temporal_split_boundary_ns'], prefix, full)
    return hp, fp, history, forecast, prefix, full, location


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        return read(path)
    hp, fp, history, forecast, prefix, full, location = inputs(case)
    rows = attach_orbits(forecast['transitions'], history['past_versions'])
    selection = qualify(rows, forecast['temporal_split_boundary_ns'], prefix, full, location if location['qualified'] else {})
    record = dict(case=case, selection=selection, transitions=len(rows),
        prefix_model=prefix, full_model=full, full_location=location,
        history_sha256=sha(hp), forecast_sha256=sha(fp), all_TLE_versions_pre_scan=True,
        no_RF_or_GPS_or_position_input=True, all_causal_candidates_used=True)
    write(path, record)
    print(case, 'neighbor prior qualified', selection['qualified'], selection['validation'], flush=True)
    return record


def main():
    OUT.mkdir(exist_ok=True)
    protocol = dict(cases=CASES, history_inputs='original pre-scan TLE histories only; no scan or RF incumbent loaded',
        same_frozen_neighbor_kernels=True, no_GPS_or_RF_input=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_neighbor_phase_forecast.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('TLE-only neighbor qualification changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in CASES])]
    write(OUT/'evaluation.json', dict(rows=rows, all_terminal=True, qualified=sum(r['selection']['qualified'] for r in rows)))


if __name__ == '__main__':
    main()
