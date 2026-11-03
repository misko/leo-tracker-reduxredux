"""Frame-resampled joint carrier/clock covariance on existing saved paired IQ."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from ds23_joint_receiver_iq import JointReceiverIQ
from ds23_joint_iq_frame_bootstrap import FrameResampledJointIQ
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import JointComponentWorkspace, common_segments
from probe_ds23_joint_receiver_iq import OUT as RAW
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT/'reports/2026_10_21_ds23_common_clock_alias_refit/evaluation.json'
OUT = ROOT/'reports/2026_10_21_ds23_joint_iq_frame_bootstrap'
BULK = Path('/srv/bulk/leo/research/ds23-joint-iq-frame-bootstrap-20261021')
REPLICATES = 63


def one(row):
    index, entry = row['index'], row['entry']
    path = BULK/f'probe{index:03d}.json'
    if path.exists():
        return read(path)
    began = time.monotonic()
    def timeout(*_):
        raise TimeoutError('360second paired-frame RF uncertainty cap')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(360)
    try:
        with np.load(entry['panel'], allow_pickle=False) as panel:
            values = panel[entry['window_key']]
        assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest() == entry['raw_window_sha256']
        samples = np.array([values[:, rx, 0].astype(float)+1j*values[:, rx, 1] for rx in [0, 1]])
        fs, edge, epochs = entry['sample_rate_hz'], entry['edge'], np.asarray(row['aligned_epochs'])
        initial = [[dict(CFO_hz=entry['components'][k]['peaks'][rx]['fractional_tracking_cfo_hz'],
            offset_samples=0., modulation_ppm=0.) for k in [0, 1]] for rx in [0, 1]]
        geometry = [fractional_geometry(y, fs, edge, epochs[k, rx], initial[rx][k])
            for rx, y in enumerate(samples) for k in [0, 1]]
        segments = common_segments(geometry)
        raw = next(r for r in read(RAW/'evaluation.json')['rows'] if r['index'] == index)
        full_noise = []
        for rx in [0, 1]:
            parameters = np.mean([np.asarray(f['native_training_fits'][rx]['parameters']) for f in row['folds']], axis=0)
            seeds = [dict(CFO_hz=p[0], offset_samples=p[1], modulation_ppm=p[2]) for p in parameters.reshape(2, 3)]
            ws = JointComponentWorkspace(samples[rx], fs, edge, epochs[:, rx], segments)
            fitted = ws.joint_fit(seeds)
            statistics = ws.statistics(fitted['parameters'], derivatives=False)
            full_noise.append(statistics['residual_energy']/max(1, statistics['sample_count']-3*len(segments)-3))
        problem = JointReceiverIQ(samples, fs, edge, epochs.T, segments, full_noise)
        full_trials = [problem.fit(np.asarray(f['models']['common']['fit']['parameters']), iterations=30) for f in raw['folds']]
        full = min(full_trials, key=lambda r:r['quadratic'])
        rng = np.random.default_rng(2026102190+index)
        replicates = []
        for k in range(REPLICATES):
            while True:
                draw = rng.integers(0, len(segments), len(segments))
                if len(np.unique(draw)) >= 4:
                    break
            resampled = FrameResampledJointIQ(samples, fs, edge, epochs.T, segments, full_noise, draw)
            fitted = resampled.fit(np.asarray(full['parameters']), iterations=16)
            statistics = resampled.statistics(fitted['parameters'])
            projected_score = float(np.max(abs(statistics['rhs'])/np.sqrt(np.maximum(np.diag(statistics['normal']), 1e-20))))
            replicates.append(dict(index=k, draws=draw, parameters=fitted['parameters'],
                score=fitted['score'], quadratic=fitted['quadratic'], calls=fitted['calls'],
                boundary=fitted['boundary'], covariance_full_rank=fitted['covariance_full_rank'],
                maximum_standardized_score=projected_score))
        frequencies = np.array([r['parameters'][:3] for r in replicates])
        covariance = np.cov(frequencies, rowvar=False)
        full_cov = np.asarray(full['frequency_covariance']) if full['frequency_covariance'] is not None else None
        sigma = np.sqrt(np.diag(covariance))
        result = dict(index=index, case=entry['case'], entry=entry, cohort=entry['cohort'], status='complete',
            frames=len(segments), full_fit=full, full_start_trials=full_trials, noise_variance=full_noise,
            bootstrap_replicates=replicates, bootstrap_frequency_covariance=covariance,
            bootstrap_frequency_sigma_hz=sigma,
            Gaussian_frequency_sigma_hz=None if full_cov is None else np.sqrt(np.diag(full_cov)),
            bootstrap_clock_quantiles_hz=np.quantile(frequencies[:, 2], [.025, .16, .5, .84, .975]),
            fold_clock_difference_hz=float(abs(raw['folds'][0]['models']['common']['fit']['receiver_clock_hz'][0]
                - raw['folds'][1]['models']['common']['fit']['receiver_clock_hz'][0])),
            bounded_replicates=sum(r['boundary'] for r in replicates),
            rank_deficient_replicates=sum(not r['covariance_full_rank'] for r in replicates),
            no_other_frames_or_receivers_broken_apart_by_bootstrap=True,
            fixed_native_carrier_branch_and_RF_acquisition_conditioned=True,
            not_an_absolute_frequency_truth_or_covariance_coverage_validation=True,
            no_position_estimate_changed=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(index=index, case=entry['case'], cohort=entry['cohort'], entry=entry,
            status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-began
    write(path, result)
    print(index, entry['case'], entry['window_key'], result['status'],
        result.get('bootstrap_frequency_sigma_hz'), result.get('error'), flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    source = read(SOURCE)
    protocol = dict(source_sha256=sha(SOURCE), joint_IQ_source_sha256=sha(RAW/'evaluation.json'),
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,
            'ds23_joint_iq_frame_bootstrap.py', 'ds23_joint_receiver_iq.py']},
        workers=6, per_window_seconds=360, bootstrap_replicates=REPLICATES,
        full_fit='two frame-fold RF starts,30joint steps each, lowest common-data Q',
        bootstrap='resample whole paired physical frames with replacement;63refits of all15parameters;16warm steps each',
        native_CFO_branch_and_acquisition_conditioned=True,
        same9windows_including_held_prediction_failures=True,
        no_GPS_TLE_satellite_ID_new_RF_or_position_used=True,
        bootstrap_uncertainty_not_proof_of_absolute_covariance_coverage=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen paired-frame bootstrap protocol changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, r) for r in source['rows']])]
    write(OUT/'evaluation.json', dict(rows=sorted(rows, key=lambda r:r['index']), all_terminal=True,
        protocol_sha256=sha(target), no_position_method_promoted=True))


if __name__ == '__main__':
    main()
