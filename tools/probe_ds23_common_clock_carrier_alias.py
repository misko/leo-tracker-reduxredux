"""RF-only within-frame evidence for native carrier alias alternatives."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from inventory_ds23_paired_component_cycles import PERIOD
from probe_ds23_common_receiver_clock import OUT as SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_common_clock_carrier_alias'
BULK = Path('/srv/bulk/leo/research/ds23-common-clock-carrier-alias-20261021')


def one(row):
    index, entry = row['index'], row['entry']
    path = BULK/f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    with np.load(entry['panel'], allow_pickle=False) as panel:
        values = panel[entry['window_key']]
    samples = [values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]]
    fs, edge, epochs = entry['sample_rate_hz'], entry['edge'], np.asarray(row['aligned_epochs'])
    initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
        offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
    geometries = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
        for rx, y in enumerate(samples) for k in [0, 1]]
    segments = common_segments(geometries)
    result = []
    for fold in row['folds']:
        train = np.arange(len(segments)) % 2 == fold['parity']
        support = [ix for k, ix in enumerate(segments) if train[k]]
        held = [ix for k, ix in enumerate(segments) if not train[k]]
        rx = 1
        baseline = np.array(fold['native_training_fits'][rx]['parameters'])
        for component in [0, 1]:
            for pilot_alias in [-1, 0, 1]:
                parameters = baseline.copy()
                parameters[3*component] += pilot_alias*PERIOD
                seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2])
                    for p in parameters.reshape(2, 3)]
                training = JointComponentWorkspace(samples[rx], fs, edge, epochs[:, rx], support)
                fitted = training.joint_fit(seeds)
                test = JointComponentWorkspace(samples[rx], fs, edge, epochs[:, rx], held)
                held_fit = test.statistics(fitted['parameters'], derivatives=False)
                result.append(dict(parity=fold['parity'], receiver=rx+1, component=component,
                    native_pilot_alias_added=pilot_alias, fit=fitted, held_profile_score=held_fit['score'],
                    held_profile_residual_energy=held_fit['residual_energy'], held_samples=held_fit['sample_count'],
                    held_complex_component_gains_and_DC_are_profiled=True))
    doc = dict(index=index, case=entry['case'], window_key=entry['window_key'],
        cohort=entry['cohort'], rows=result, native_carrier_shifts_hz=[-PERIOD, 0., PERIOD],
        no_GPS_TLE_or_position_used=True, no_CFO_alias_or_position_change_adopted=True)
    write(path, doc)
    print(index, entry['case'], entry['window_key'], 'complete', flush=True)
    return doc


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    source = SOURCE/'evaluation.json'
    protocol = dict(source_sha256=sha(source), workers=9,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,
            'ds23_joint_component_rf.py', 'ds23_training_channel_rf.py']},
        all9windows_no_selection_by_clock_results=True,
        each_RX2_component_tested_at_native_and_plus_minus_one_pilot_alias=True,
        native_and_shifted_RF_fits_use_identical_training_samples_and24step_budget=True,
        held_score_profiles_complex_gains_and_DC_but_not_carrier_epoch_or_rate=True,
        no_satellite_GPS_TLE_or_position_used=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen within-frame carrier-alias protocol changed')
    if not target.exists():
        write(target, protocol)
    rows = read(source)['rows']
    with ProcessPoolExecutor(max_workers=9) as pool:
        results = [f.result() for f in as_completed([pool.submit(one, row) for row in rows])]
    write(OUT/'evaluation.json', dict(rows=sorted(results, key=lambda r:r['index']),
        all_terminal=True, protocol_sha256=sha(target), no_position_improvement_established=True))


if __name__ == '__main__':
    main()
