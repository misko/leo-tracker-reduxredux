"""RF-only wide carrier search on one weak endpoint and two preceding controls."""

from collections import OrderedDict
import argparse
import copy
import json
from pathlib import Path
import numpy as np

from fast_local_pilot_refinement import FastPilotWorkspace
from probe_ds23_secondary_curves import probe_authority
from run_algo01_ds23_sample import ROOT, DATASET, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_0289_weak_RF'
BULK = Path('/srv/bulk/leo/research/ds23-0289-weak-RF-20261020')


def restricted_frames(workspace, parity):
    if parity not in (0, 1):
        raise ValueError('even or odd frame parity required')
    changed = copy.copy(workspace)
    changed.frames = workspace.frames[parity::2]
    changed.raw_sum = workspace.raw_sum[parity::2]
    changed.raw_energy = workspace.raw_energy[parity::2]
    changed._rotation_cache = OrderedDict(); changed._rotation_cached_bytes = 0
    return changed


def prepare():
    OUT.mkdir(exist_ok=True); (BULK/'IQ').mkdir(parents=True, exist_ok=True); (BULK/'panels').mkdir(exist_ok=True)
    case = 'DS23-0289'
    tail = read(ROOT/'reports/2026_10_20_ds23_joint_probe_position_v2/DS23-0289_tail_native_peaks.json')
    # Fixed local controls immediately before the diagnosed endpoint, never a
    # prediction-derived frequency seed or a GPS-selected observation.
    chosen = tail['rows'][-3:]
    document_path = ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'tracking.json'
    source, authority = probe_authority(read(document_path)); jobs = []
    for selected in chosen:
        pi = selected['probe']; probe = source['probes'][pi]
        winner = max([c for c in probe['candidates'] if c['passed_fractional_margin_gate']],
                     key=lambda c: (c['fractional_margin'], -c['candidate_rank']))
        jobs.append(dict(case=case, probe=pi, observation_id=selected['observation_id'], time_s=authority[pi]['time_s'],
            visit_index=probe['visit_index'], sample_counter=probe['valid_start_counter'], native_receiver_id=probe['receiver_id'],
            edge=probe['edge'], epoch=winner['integer_epoch_sample']+winner['fractional_epoch_offset_samples'],
            archived_CFO_hz=winner['fractional_tracking_cfo_hz'], archived_margin=winner['fractional_margin']))
    protocol = dict(jobs=jobs, dataset_manifest_sha256=sha(DATASET/'manifest.json'), tracking_sha256=sha(document_path),
        frequency_seed='public native winning CFO only; no orbit frequency seed',
        wide_radius_hz=4000, wide_scout_radius_hz=4000, native_radius_hz=800, native_scout_radius_hz=600,
        epoch_radius_samples=.75, maximum_modulation_ppm=40, optimization_iterations=16, starts=3,
        both_heldout_frame_fold_minimum_gain=2*np.log(81), maximum_training_fold_CFO_difference_hz=50,
        maximum_raw_export_seconds=120, maximum_raw_windows=8192, no_new_RF_collection=True, no_GPS_or_TLE_input_to_RF_fit=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/fast_local_pilot_refinement.py']})
    path = BULK/'IQ/protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('weak endpoint RF protocol changed')
    if not path.exists():
        write(path, protocol)
    print('WEAK_ENDPOINT_RF_PROBES', len(jobs), flush=True)


def export():
    import probe_ds23_shared_probe_cohort as adapter
    adapter.BULK = BULK
    from ds23_confirmation_IQ_export import export as reader_export
    reader_export('DS23-0289')


def run(job):
    with np.load(BULK/'panels/DS23-0289.npz', allow_pickle=False) as archive:
        meta = json.loads(str(archive['metadata_json']))
        point = next(p for p in meta['points'] if p['probe'] == job['probe'])
        raw = archive[point['window_key']][:, point['receiver_offset']]
    y = raw[:, 0].astype(float)+1j*raw[:, 1].astype(float)
    workspace = FastPilotWorkspace(y, meta['sample_rate_hz'], job['edge'], job['epoch'])
    base = workspace.fast_joint_fit(job['archived_CFO_hz'], starts=3)
    wide = workspace.fast_joint_fit(job['archived_CFO_hz'], starts=3, radius=4000, scout_radius=4000)
    folds, trained = [], []
    for parity, test in [(0, 'odd'), (1, 'even')]:
        train = restricted_frames(workspace, parity)
        local = train.fast_joint_fit(job['archived_CFO_hz'], starts=3)
        broad = train.fast_joint_fit(job['archived_CFO_hz'], starts=3, radius=4000, scout_radius=4000)
        scores = []
        for fit in (local, broad):
            d = workspace.evaluate([fit['CFO_hz']], fit['offset_samples'], fit['modulation_ppm'], test, details=True)
            scores.append(float(d['scores'][0]))
        samples = sum(len(workspace.frames[k]) for k in d['frames'])
        loss = float(2*samples*np.log(max(1-scores[1], 1e-15)/max(1-scores[0], 1e-15)))
        folds.append(dict(training_parity=parity, test=test, local_fit=local, wide_fit=broad,
                          heldout_wide_minus_local_loss=loss, heldout_samples=samples))
        trained.append(broad)
    flags = ('frequency_search_boundary', 'epoch_search_boundary', 'code_rate_search_boundary')
    checks = dict(full_wide_interior=not any(wide[k] for k in flags),
        both_training_wide_interior=not any(f[k] for f in trained for k in flags),
        training_fold_CFO_agreement=abs(trained[0]['CFO_hz']-trained[1]['CFO_hz']) <= 50,
        both_heldout_folds_prefer_wide_with_search_penalty=all(f['heldout_wide_minus_local_loss'] <= -2*np.log(81) for f in folds),
        positive_true_vs_control_RF_margin=wide['margin'] > 0)
    grid = job['archived_CFO_hz']+np.arange(-4000, 4001, 25.)
    spectrum = workspace.evaluate(grid, wide['offset_samples'], wide['modulation_ppm'])
    record = dict(job, base_fit=base, wide_fit=wide, folds=folds, checks=checks, RF_qualified_change=all(checks.values()),
        grid_CFO_hz=grid, conditional_RF_scores=spectrum, CFO_delta_hz=wide['CFO_hz']-job['archived_CFO_hz'],
        no_GPS_or_orbit_frequency_used=True, no_position_refit_yet=True,
        scores_are_profile_diagnostics_not_calibrated_probabilities=True)
    write(BULK/(f"probe{job['probe']:06d}.json"), record)
    return record


def analyze():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    protocol = read(BULK/'IQ/protocol.json')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('weak RF source changed')
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, job) for job in protocol['jobs']])]
    write(OUT/'evaluation.json', dict(rows=rows, protocol_sha256=sha(BULK/'IQ/protocol.json'),
        IQ_panel_sha256=sha(BULK/'panels/DS23-0289.npz'), no_position_refit_yet=True))
    print('WEAK_RF_COMPLETE', [(r['time_s'], r['CFO_delta_hz'], r['RF_qualified_change'], r['checks']) for r in rows], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'export', 'analyze'])
    args = parser.parse_args()
    {'prepare': prepare, 'export': export, 'analyze': analyze}[args.stage]()
