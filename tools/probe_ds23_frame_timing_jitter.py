"""Bounded saved-IQ test of per-frame timing jitter; no orbital inputs."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import json
import signal
import time
import numpy as np

from ds23_frame_timing_jitter import FrameJitterWorkspace, restrict_samples
from probe_ds23_same_probe_IQ import OUT as SOURCE, PANELS
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_frame_timing_jitter'
BULK = Path('/srv/bulk/leo/research/ds23-frame-timing-jitter-20261020')


def run(job):
    target = BULK/(job['case']+f"_probe{job['probe']:06d}.json")
    if target.exists():
        return read(target)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('60second saved-IQ jitter probe budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(60)
    try:
        with np.load(PANELS/(job['case']+'.npz'), allow_pickle=False) as archive:
            metadata = json.loads(str(archive['metadata_json']))
            point = next(p for p in metadata['points'] if p['probe'] == job['probe'])
            raw = archive[point['window_key']][:, point['receiver_offset']]
        y = raw[:, 0].astype(float)+1j*raw[:, 1].astype(float); components = {}
        for role in ['first', 'second']:
            peak = job[role]
            p = FrameJitterWorkspace(y, metadata['sample_rate_hz'], job['edge'], peak['epoch'])
            baseline = p.fast_joint_fit(peak['cfo_hz'])
            jitter = p.jitter_fit(baseline); folds = []
            for half in [0, 1]:
                train = restrict_samples(p, half)
                base_train = train.fast_joint_fit(peak['cfo_hz'])
                jitter_train = train.jitter_fit(base_train)
                base_prediction, jitter_prediction = p.prediction(base_train, half), p.prediction(jitter_train, half)
                gain = 2*base_prediction['sample_count']*np.log(base_prediction['squared_error']/jitter_prediction['squared_error'])
                folds.append(dict(training_half=half, baseline_fit=base_train, jitter_fit=jitter_train,
                    baseline_prediction=base_prediction, jitter_prediction=jitter_prediction,
                    heldout_jitter_improvement_profile_units=float(gain)))
            parameters = [baseline['CFO_hz'], baseline['offset_samples'], baseline['modulation_ppm']]
            stats = p.statistics(parameters); old_sse = stats['raw_energy']*(1-stats['score'])
            n = jitter['sample_count']
            bic_gain = 2*n*np.log(old_sse/jitter['residual_energy'])-len(p.frames)*np.log(2*n)
            checks = dict(both_heldout_halves_improve=all(f['heldout_jitter_improvement_profile_units']>10 for f in folds),
                conservative_full_BIC_gain_over10=bool(bic_gain>10),
                all_jitter_fits_interior=not any(f['boundary'] for f in [jitter]+[v['jitter_fit'] for v in folds]),
                CFO_training_halves_agree_within75Hz=abs(folds[0]['jitter_fit']['CFO_hz']-folds[1]['jitter_fit']['CFO_hz'])<75)
            components[role] = dict(baseline_fit=baseline, jitter_fit=jitter, folds=folds,
                full_extra_parameter_BIC_gain=float(bic_gain), checks=checks, qualified=all(checks.values()),
                jitter_minus_baseline_CFO_hz=jitter['CFO_hz']-baseline['CFO_hz'],
                lifted_jitter_CFO_hz=job[role+'_lifted_value']+jitter['CFO_hz']-peak['cfo_hz'])
        record = dict(case=job['case'], probe=job['probe'], time_s=job['time_s'], status='complete',
            components=components, all_training_and_test_sample_supports_fixed=True,
            no_GPS_or_orbit_input=True, no_new_RF_collection=True)
    except Exception as exc:
        record = dict(case=job['case'], probe=job['probe'], status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-started; write(target, record)
    print(job['case'], job['probe'], record['status'],
          {k: v['qualified'] for k, v in record.get('components', {}).items()}, record.get('error'), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true'); args = parser.parse_args()
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    old = read(SOURCE/'protocol.json'); jobs = old['jobs']; cases = sorted({j['case'] for j in jobs})
    pilot = []
    for case in cases:
        group = sorted([j for j in jobs if j['case'] == case], key=lambda j: j['time_s'])
        pilot.extend(group[k] for k in sorted(set(np.linspace(0, len(group)-1, 6).astype(int))))
    protocol = dict(jobs=jobs, pilot_jobs=pilot, sigma_jitter_samples=.15, jitter_bounds_samples=[-.6, .6],
        full_vs_no_jitter_same_20ms_saved_IQ=True, heldout='first/second temporal half in each guarded frame',
        all_timing_CFO_gain_and_DC_nuisances_fitted_on_training_only=True,
        global_CFO_epoch_rate_seeded_from_archived_RF_proposal_not_orbit=True,
        original20ms_archived_proposal_is_not_independent_of_heldout_data=True,
        complete_per_frame_jitter_not_a_new_frame_clock_or_fractional_template_test=True,
        no_orbit_GPS_frequency_seed_or_position_update=True, no_new_RF_collection=True,
        source_IQ_protocol_sha256=sha(SOURCE/'protocol.json'),
        panel_sha256={case: sha(PANELS/(case+'.npz')) for case in cases}, workers=8,
        per_probe_seconds=60, source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_frame_timing_jitter.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('saved-IQ jitter protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, j) for j in (jobs if args.full else pilot)])]
    complete = [r for r in rows if r['status'] == 'complete']; statistics = {}
    for case in cases:
        group = [v for r in complete if r['case'] == case for v in r['components'].values()]
        statistics[case] = dict(components=len(group), qualified=sum(v['qualified'] for v in group),
            median_CFO_shift_hz=float(np.median([v['jitter_minus_baseline_CFO_hz'] for v in group])),
            median_absolute_CFO_shift_hz=float(np.median([abs(v['jitter_minus_baseline_CFO_hz']) for v in group])),
            median_jitter_RMS_samples=float(np.median([np.sqrt(np.mean(np.array(v['jitter_fit']['frame_jitter_samples'])**2)) for v in group])),
            median_BIC_gain=float(np.median([v['full_extra_parameter_BIC_gain'] for v in group])),
            median_heldout_gain=float(np.median([f['heldout_jitter_improvement_profile_units'] for v in group for f in v['folds']])))
    write(OUT/('full_evaluation.json' if args.full else 'pilot_evaluation.json'), dict(rows=rows, statistics=statistics,
        all_terminal=True, protocol_sha256=sha(path), no_position_accuracy_claim=True,
        failures=[r for r in rows if r['status'] != 'complete']))
    print('FRAME_JITTER', statistics, flush=True)


if __name__ == '__main__':
    main()
