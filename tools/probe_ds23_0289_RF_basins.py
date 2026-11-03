"""Check that the weak-endpoint conclusion survives multiple RF search basins."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import json
import numpy as np

from fast_local_pilot_refinement import FastPilotWorkspace
from probe_ds23_0289_weak_RF import BULK, restricted_frames
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_0289_RF_basins'


def sweep(workspace, center):
    fits = [workspace.fast_joint_fit(center+delta, starts=1) for delta in np.arange(-4000., 4001., 500.)]
    return max(fits, key=lambda f: f['score']), fits


def run(job):
    with np.load(BULK/'panels/DS23-0289.npz', allow_pickle=False) as archive:
        metadata = json.loads(str(archive['metadata_json']))
        point = next(p for p in metadata['points'] if p['probe'] == job['probe'])
        raw = archive[point['window_key']][:, point['receiver_offset']]
    p = FastPilotWorkspace(raw[:, 0].astype(float)+1j*raw[:, 1].astype(float), metadata['sample_rate_hz'], job['edge'], job['epoch'])
    full, basins = sweep(p, job['archived_CFO_hz']); folds = []
    for parity, test in [(0, 'odd'), (1, 'even')]:
        train = restricted_frames(p, parity)
        best, _ = sweep(train, job['archived_CFO_hz'])
        old = train.fast_joint_fit(job['archived_CFO_hz'], starts=3)
        scores = []
        for fit in (old, best):
            d = p.evaluate([fit['CFO_hz']], fit['offset_samples'], fit['modulation_ppm'], test, details=True)
            scores.append(float(d['scores'][0]))
        n = sum(len(p.frames[k]) for k in d['frames'])
        loss = 2*n*np.log(max(1-scores[1], 1e-15)/max(1-scores[0], 1e-15))
        folds.append(dict(test=test, native_basin_fit=old, multi_basin_fit=best,
                          heldout_multi_minus_native_loss=float(loss)))
    record = dict(job, full_fit=full, basins=basins, folds=folds,
                  delta_from_archived_hz=full['CFO_hz']-job['archived_CFO_hz'],
                  actual_search_support_hz=[-4800, 4800], frequency_centers_derived_only_from_archived_winner=True,
                  no_GPS_or_orbit_frequency_input=True, no_position_refit=True)
    write(OUT/(f"probe{job['probe']:06d}.json"), record)
    return record


def main():
    OUT.mkdir(exist_ok=True)
    protocol = dict(source_IQ_protocol_sha256=sha(BULK/'IQ/protocol.json'), IQ_panel_sha256=sha(BULK/'panels/DS23-0289.npz'),
                    frequency_centers_relative_hz=[-4000, 4000, 500], per_basin_radius_hz=800,
                    nominal_epoch_radius_samples=.75, modulation_range_ppm=[-40, 40], workers=3,
                    no_GPS_or_TLE_frequency_seed=True, source_sha256=sha(Path(__file__)))
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('RF basin search changed')
    if not path.exists():
        write(path, protocol)
    jobs = read(BULK/'IQ/protocol.json')['jobs']
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, job) for job in jobs])]
    write(OUT/'evaluation.json', dict(rows=rows, no_position_accuracy_claim=True))
    print('RF_BASINS_COMPLETE', [(r['time_s'], r['delta_from_archived_hz']) for r in rows], flush=True)


if __name__ == '__main__':
    main()
