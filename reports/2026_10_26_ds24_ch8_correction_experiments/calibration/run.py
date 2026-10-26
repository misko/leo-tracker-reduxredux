"""Conditional CH8 prediction from CH1-7: RF-scaled vs native-Hz RX drift."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import algo02_scan as algo
from ds23_frozen_precision import conditional_gaussian
from investigate_dsx01_localization_failures import fit
from probe_ds23_graph_seeded_paths import build

OUT = Path(__file__).resolve().parent
ROOT = Path('/srv/bulk/leo/research/ds25-20261024')


def encode(x):
    if isinstance(x, np.ndarray): return x.tolist()
    if isinstance(x, np.generic): return x.item()
    raise TypeError(type(x).__name__)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=encode, allow_nan=False)+'\n')


def native_scan(scan):
    """Change the common smooth design, including all existing prediction ports."""
    out = copy.copy(scan)
    out.rx_basis = [b/(t['rf_hz']/11.5e9)
                    for b, t in zip(scan.rx_basis, scan.tracks, strict=True)]
    return out


def prediction(raw, features, gram, sigma):
    root = np.linalg.cholesky(gram)
    uncertainty = np.linalg.solve(root, features.T).T
    n = len(raw)
    result = conditional_gaussian(raw, uncertainty, sigma, np.ones(n), np.ones(n),
                                  np.ones(uncertainty.shape[1]), 1.)
    variance = sigma**2 + np.sum(uncertainty**2, axis=1)
    return dict(negative_twice_log_density=result['objective'],
                quadratic=result['quadratic'], logvolume=result['logvolume'],
                normalization_constant=result['normalization_constant'],
                RMS_hz=float(np.sqrt(np.mean(raw**2))), mean_hz=float(np.mean(raw)),
                median_predictive_SD_hz=float(np.median(np.sqrt(variance))))


def one(job):
    case, arm = job
    began = time.monotonic()
    source = ROOT/'family_cavity/position'/f'{case}.json'
    saved = json.loads(source.read_text())
    selected = saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(ROOT)
    scan = algo.load_scan(ROOT, case)
    original = dict(scan=scan, node=selected['node'] if selected else saved['baseline_node'],
        keep=np.asarray(saved['original_mask'], bool), powers=np.asarray(saved['powers']),
        model=saved['model'], means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'])
    parent = saved['policy_arms'][arm]
    replay = build(original, 'default', arm, parent['phase_reference'])
    parent_x = np.asarray(parent['endpoint_east_north_km'])
    replay_delta = float(replay.calculate(parent_x)['negative_twice_elbo']-parent['negative_twice_elbo'])
    assert abs(replay_delta) < 1e-3
    channels = np.concatenate([np.full(sl.stop-sl.start, scan.tracks[i]['channel'])
                               for i, sl in zip(replay.members, replay.slices, strict=True)])
    receivers = np.concatenate([np.full(sl.stop-sl.start, scan.tracks[i]['receiver'])
                                for i, sl in zip(replay.members, replay.slices, strict=True)])
    all_ids = np.array([oid for i in replay.members for oid in scan.tracks[i]['observation_ids']])
    held = original['keep'] & (channels == 8)
    train = original['keep'] & (channels != 8)
    assert held.any() and train.any() and not (held & train).any()
    entries = [e for e in original['entries'] if scan.tracks[e['track_index']]['channel'] != 8]
    records = {}
    for variant in ('RF_scaled', 'native_Hz'):
        d = dict(original, keep=train, entries=entries,
                 scan=scan if variant=='RF_scaled' else native_scan(scan))
        x = np.zeros(2); reference = np.zeros(len(original['means'])); history = []
        for epoch in range(5):
            p = build(d, 'default', arm, reference)
            # Both calibration and predictive rows use the same transformed scan basis.
            assert p.smooth.shape == replay.smooth.shape
            if variant == 'native_Hz':
                assert np.max(abs(p.smooth*p.q[:, None]-replay.smooth)) < 1e-12
            result = fit(p, x, iterations=48)
            x = np.asarray(result['parameters'])
            phases = p.state(x)['phases'][p.labels]
            history.append(dict(epoch=epoch, phase_change_s=float(np.max(abs(phases-reference))),
                                max_absolute_phase_s=float(np.max(abs(phases))), fit=result))
            reference = np.clip(phases, -15, 15)
        full = p.calculate(x)
        c = p.curved_calculate(x) if entries else full
        assert np.max(abs(full['coefficient']-c['coefficient'])) < 1e-12
        g = p.noise_groups[train]
        weights = d['powers'][g]*c['noise_precision'][g]/p.point_noise[train]**2
        u = c['features'][train]
        gram = np.diag(c['coefficient_prior_precision']) + u.T@(weights[:, None]*u)
        residual = p.values-p.q*c['intercept']-c['features']@c['coefficient']
        assert np.max(abs(residual-c['conditional_residual_hz'])) < 1e-6
        assert np.all(c['noise_precision'][np.unique(p.noise_groups[held])] == 0)
        # Whole held fragments have no fitted noise precision or fitted constant.
        groups = {}
        for label, mask in [('all', held), ('RX1', held & (receivers==1)), ('RX2', held & (receivers==2))]:
            if mask.any():
                groups[label] = dict(points=int(mask.sum()), **prediction(residual[mask],
                    c['features'][mask], gram, p.point_noise[mask]*np.sqrt(2)))
        by_track = []
        for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
            mask = held[sl]
            if not mask.any(): continue
            positions = np.arange(sl.start, sl.stop)[mask]
            label = row['candidate_index']
            train_family = train & (np.asarray(p.labels)[p.flat_labels] == label)
            by_track.append(dict(component=scan.tracks[i]['key'], receiver=scan.tracks[i]['receiver'],
                norad=int(scan.norads[label]), other_channel_training_points=int(train_family.sum()),
                times_s=p.flat_times[positions], residual_hz=residual[positions],
                **prediction(residual[positions], c['features'][positions], gram,
                             p.point_noise[positions]*np.sqrt(2))))
        records[variant] = dict(endpoint_east_north_km=x, phase_reference=p.reference,
            history=history, training_objective=full['negative_twice_elbo'],
            training_curved_RMS_hz=float(np.sqrt(np.mean(residual[train]**2))),
            final_phase_change_s=history[-1]['phase_change_s'],
            final_precision_change=c['final_log_precision_change'],
            training_checks_pass=bool(history[-1]['phase_change_s']<=.01 and
                c['final_log_precision_change']<1e-5 and history[-1]['max_absolute_phase_s']<=15),
            held=groups, held_tracks=by_track,
            linear_calibration_max_change=float(np.max(abs(full['coefficient']-c['coefficient']))))
        write(OUT/f'{case}_{arm}_partial.json', records)
        print(case, arm, variant, groups['all'], flush=True)
    inputs = {str(source):hashlib.sha256(source.read_bytes()).hexdigest()}
    for filename in ('tracks.json','observations.json','bank.npz','nominal_elements.json','receipt.json','radio_noise.json'):
        path = ROOT/case/filename
        if path.exists(): inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    code = {}
    repo = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).suffix=='.py' and Path(path).is_relative_to(repo):
            code[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    write(OUT/f'{case}_{arm}.json', dict(case=case, arm=arm, results=records,
        baseline_objective_delta=replay_delta, train_curved_IDs=all_ids[train], held_CH8_IDs=all_ids[held],
        train_predictive_IDs=[oid for e in entries for oid in e['observation_ids']],
        full_parent_labels_support_powers_conditioning=True, independent_identity_validation=False,
        start_east_north_km=[0,0], initial_phases_zero=True, GPS_used=False,
        source_sha256=inputs, code_sha256=code, elapsed_s=time.monotonic()-began))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    jobs = [(case, arm) for case in ('DS24-0010','DS24-0011') for arm in ('c0','fitted_c')]
    write(OUT/'execution_protocol.json', dict(jobs=jobs, variants=['RF_scaled','native_Hz'],
        rounds=5, steps=48, initialization='regional center, zero phase references',
        objective='conditional CH8 predictive density with shared nuisance covariance',
        excluded_all_CH8_training_rows=True, matched_c_arms=True,
        screen='Both cases/both arms improve held density; summed gain>=10; pooled held RMS not worse; training checks pass',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        no_GPS=True, no_new_TLE=True, no_IQ=True))
    with ProcessPoolExecutor(max_workers=args.workers) as pool: list(pool.map(one, jobs))
