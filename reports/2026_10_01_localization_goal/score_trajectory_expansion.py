"""Score sealed training modes against full checking candidate sets; no GPS."""
# ruff: noqa: I001
import copy
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from run_trajectory_hypothesis import prepare
from acquire import LIGHT_KM_S, enu_state_ecef_km
from physics import _noise_covariance
from regression_batch import digest, verify_sources

from leo.analysis.localization_candidate_set import candidate_set_log_ratio

HERE = Path(__file__).resolve().parent


def mode_predictions(scan, height, ports, state, groups):
    predictions = [[] for _ in groups]
    receiver = enu_state_ecef_km(state[0], state[1], height(state[0], state[1]),
                               scan.config.prior_center_lat_deg, scan.config.prior_center_lon_deg)
    parity, background_tracks = 0., 0
    for (_track_id, track), port in zip(scan.tracks, ports, strict=True):
        index = int(np.argmax(port.score_all(state)))
        if index == port.candidate_count:
            background_tracks += 1
            continue
        rx = int(track.receiver_indices[0])
        selected = [track.observation_ids.index(v) for v in port.observation_ids]
        times = track.times_s[selected]
        channel = int(track.observation_ids[0].split(':channel')[1].split(':')[0])
        eligible = [i for i, g in enumerate(groups)
                    if g['receiver'] == rx and g['channel'] == channel
                    and g['rf_hz'] == track.rf_hz
                    and track.times_s[0] <= g['time_s'] <= track.times_s[-1]]
        query = copy.copy(port.likelihood)
        query.bank = port._row_bank(index)
        query.times = np.r_[times, [groups[i]['time_s'] for i in eligible]]
        positions, velocities = query._orbit_states_per_satellite([state[2]+state[5+index]])
        line = positions[0]-receiver
        line /= np.linalg.norm(line, axis=1, keepdims=True)
        mean = (scan.config.doppler_sign*scan.config.reference_frequency_hz/LIGHT_KM_S
                *np.sum(velocities[0]*line, axis=1)
                + state[3+rx]*port.likelihood.drift_scale*(query.times-times.mean()))
        original_prediction = port.predict_selected(state, index)
        parity = max(parity, float(np.max(np.abs(
            port.likelihood.contrasts@mean[:len(times)]-original_prediction.mean))))
        covariance = _noise_covariance(times, scan.config)
        weights = np.linalg.solve(covariance, np.ones(len(times)))
        offset = float(weights@(track.frequencies_hz[selected]-mean[:len(times)])/weights.sum())
        for j, group_index in enumerate(eligible):
            predictions[group_index].append(float(mean[len(times)+j]+offset))
    assert parity < 1e-6
    return predictions, parity, background_tracks


def main():
    start = time.monotonic()
    directory = HERE/'trajectory-expansion-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(freeze.read_text())['source_sha256'])
    audit_path = HERE/'trajectory-expansion-v1-audit.json'
    assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
    audited = {r['unit']: r for r in json.loads(audit_path.read_text())['rows']}
    rows = []
    for unit in json.loads(freeze.read_text())['units']:
        unit_start = time.monotonic()
        if not audited[unit]['accepted']:
            rows.append(dict(unit=unit, accepted=False, groups=0, modes=[],
                             training_winner_seed=None, checking_winner_seed=None,
                             failures=audited[unit]['failures']))
            continue
        path = directory/(unit+'.json')
        seal = json.loads(path.with_suffix('.seal.json').read_text())
        assert digest(path) == seal['prediction_sha256']
        receipt = json.loads(path.read_text())
        verify_sources(receipt['source_sha256'])
        verify_sources(receipt['inputs'])
        source_path = HERE/'source-split-expansion-v1'/(unit+'.json')
        assert digest(source_path) == source_path.with_suffix('.sha256').read_text().strip()
        source = json.loads(source_path.read_text())
        by_group = defaultdict(list)
        for p in source['checking_points']:
            by_group[p['source_group_id']].append(p)
        groups = []
        for key, points in sorted(by_group.items()):
            first = points[0]
            assert len({(p['receiver_id'], p['channel'], p['actual_rf_hz']) for p in points}) == 1
            scale = 11.2e9/first['actual_rf_hz']
            times = [(p['support_center_utc_ns']-source['start_utc_ns'])/1e9 for p in points]
            groups.append(dict(source_group_id=key, receiver=first['receiver_id'],
                               channel=first['channel'], rf_hz=first['actual_rf_hz'],
                               time_s=float(np.median(times)), time_spread_s=float(np.ptp(times)),
                               candidates=[p['measured_cfo_hz']*scale for p in points],
                               period=(1/4.4e-6)*scale))
        scan, height, ports = prepare(unit)
        modes = []
        for fit in receipt['fits']:
            if not fit['converged']:
                continue
            predictions, parity, background = mode_predictions(
                scan, height, ports, np.asarray(fit['mean']), groups)
            scores = [candidate_set_log_ratio(g['candidates'], means, period=g['period'],
                                              scale=200., signal_probability=.5)
                      for g, means in zip(groups, predictions, strict=True)]
            modes.append(dict(seed_index=fit['seed_index'],
                              training_objective=fit['objectives'][-1],
                              total_log_ratio=float(np.sum(scores)), per_group_log_ratios=scores,
                              groups_with_prediction=sum(bool(v) for v in predictions),
                              background_tracks=background, training_mean_parity_hz=parity))
        rows.append(dict(unit=unit, accepted=True, groups=len(groups), modes=modes,
                         training_winner_seed=receipt['best']['seed_index'],
                         checking_winner_seed=max(modes, key=lambda m: m['total_log_ratio'])[
                             'seed_index'] if modes else None,
                         maximum_candidate_time_spread_s=max(g['time_spread_s'] for g in groups),
                         source_group_order=[g['source_group_id'] for g in groups],
                         fit_sha256=digest(path), source_sha256=digest(source_path),
                         scoring_seconds=time.monotonic()-unit_start))
    result = dict(rows=rows, seconds=time.monotonic()-start,
                  config=dict(cauchy_scale_hz=200., signal_probability=.5),
                  sources={str(Path(__file__)): digest(__file__),
                      str(HERE.parents[1]/'src/leo/analysis/localization_candidate_set.py'):
                      digest(HERE.parents[1]/'src/leo/analysis/localization_candidate_set.py')},
                  qualification='Prespecified engineering scale/prior, not calibrated. Conditional '
                  'on nonempty detector candidate count: at most one signal candidate, remaining '
                  'uniform clutter, equal training-track mixture weights within active support. '
                  'Wrapped Cauchy is a new checking model, not original Student-t likelihood. '
                  'Frequency offsets GLS-trained only; state/identity plug-in. Candidate times '
                  'represented by source-group median. Sum is composite across dependent probes; '
                  'not a posterior probability or validated acceptance criterion. No GPS/refit.')
    output = HERE/'trajectory-expansion-checking-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps([dict(unit=r['unit'], groups=r['groups'],
        training_winner=r['training_winner_seed'], checking_winner=r['checking_winner_seed'],
        modes=[{k: v for k, v in m.items() if k != 'per_group_log_ratios'} for m in r['modes']])
        for r in rows], indent=2))


if __name__ == '__main__':
    main()
