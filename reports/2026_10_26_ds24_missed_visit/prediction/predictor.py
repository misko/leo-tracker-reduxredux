"""Bounded sparse histories; measured earlier candidates only, no truth API."""
import math
import numpy as np

VERSION = 'sparse-causal-prediction/v1'
HISTORY_VISITS = 12
HORIZON_S = 4.5
MAX_MODES = 8
MAX_PATHS_PER_LAST_DONOR = 2


def wrap(x, period):
    return (x + period / 2) % period - period / 2


def candidate_epoch(c):
    return c['integer_epoch_sample'] + c['fractional_epoch_offset_samples']


def measured_candidates(probe, header):
    accepted = []
    period = header['sample_rate_hz'] / 750
    for c in sorted(probe['candidates'], key=lambda c: c['candidate_rank']):
        if not 0 <= c['candidate_rank'] <= 8 or not c['passed_fractional_margin_gate'] or c['fractional_margin'] < .025:
            continue
        if any(abs(wrap(candidate_epoch(c) - a['epoch_samples'], period)) <= 2 and
               abs(c['fractional_tracking_cfo_hz'] - a['CFO_hz']) <= 200 for a in accepted):
            continue
        start = probe['valid_start_counter']
        accepted.append(dict(observation_id=f"{header['case']}/v{probe['visit_index']}/p{probe['probe_index']}/rx{header['receiver_id']}/r{c['candidate_rank']}",
            candidate_rank=c['candidate_rank'], visit_index=probe['visit_index'],
            epoch_samples=candidate_epoch(c), CFO_hz=c['fractional_tracking_cfo_hz'], margin=c['fractional_margin'],
            start_counter=start, stop_counter=start + header['window_samples'],
            reference_counter=start + header['window_samples'] // 2,
            generation=header['generation'], source_id=header['source_id'],
            measurement_contract='hashed public tracking export; original fullwindow fractional GLRT'))
    return accepted


def fit_scalar(times, values):
    if len(times) == 1:
        return dict(intercept=float(values[0]), rate_per_s=0., residual_rms=0., max_residual=0.,
                    time_design_inverse=None)
    x = np.column_stack((np.ones(len(times)), times))
    beta = np.linalg.lstsq(x, values, rcond=None)[0]
    residual = np.asarray(values) - x @ beta
    return dict(intercept=float(beta[0]), rate_per_s=float(beta[1]),
        residual_rms=float(np.sqrt(np.mean(residual ** 2))), max_residual=float(np.max(abs(residual))),
        time_design_inverse=np.linalg.inv(x.T @ x).tolist())


def fit_track(track, rate):
    last = track[-1]
    times = [(d['reference_counter'] - last['reference_counter']) / rate for d in track]
    timing_times = [(d['start_counter'] - last['start_counter']) / rate for d in track]
    phase = [wrap(d['epoch_samples'] + (d['start_counter'] - last['start_counter']) - last['epoch_samples'], rate / 750)
             for d in track]
    return dict(donors=track, reference_counter=last['reference_counter'],
        timing_reference_counter=last['start_counter'], epoch_reference_start_counter=last['start_counter'],
        epoch_reference_base_samples=last['epoch_samples'],
        CFO_fit=fit_scalar(times, [d['CFO_hz'] for d in track]), timing_fit=fit_scalar(timing_times, phase),
        one_donor=len(track) == 1)


def compatible(track, candidate, rate):
    last = track[-1]
    dt = (candidate['reference_counter'] - last['reference_counter']) / rate
    if dt <= 0:
        return False
    if abs(candidate['CFO_hz'] - last['CFO_hz']) > 500 + 6000 * dt:
        return False
    phase = wrap(candidate['epoch_samples'] + (candidate['start_counter'] - last['start_counter']) - last['epoch_samples'], rate / 750)
    if abs(phase) > 4 + 200 * dt:
        return False
    m = fit_track(track + [candidate], rate)
    return (abs(m['CFO_fit']['rate_per_s']) <= 6000 and abs(m['timing_fit']['rate_per_s']) <= 200 and
            m['CFO_fit']['max_residual'] <= 500 and m['timing_fit']['max_residual'] <= 4)


def priority(track):
    return (-track[-1]['reference_counter'], -len(track), tuple(d['candidate_rank'] for d in track),
            tuple(d['observation_id'] for d in track))


def prune(tracks):
    seen = set()
    per_last = {}
    kept = []
    pruned = 0
    for track in sorted(tracks, key=priority):
        key = tuple(d['observation_id'] for d in track)
        if key in seen:
            continue
        seen.add(key)
        last = key[-1]
        if len(kept) >= MAX_MODES or per_last.get(last, 0) >= MAX_PATHS_PER_LAST_DONOR:
            pruned += 1
            continue
        kept.append(track)
        per_last[last] = per_last.get(last, 0) + 1
    return kept, pruned


def scalar_prediction(fit, dt, one_donor, floor, rate_sigma, acceleration):
    value = fit['intercept'] + fit['rate_per_s'] * dt
    if one_donor:
        sigma = math.hypot(floor, rate_sigma * dt) + .5 * acceleration * dt * dt
        leverage = None
    else:
        design = np.array([1., dt])
        leverage = float(design @ np.asarray(fit['time_design_inverse']) @ design)
        sigma = max(floor, fit['residual_rms']) * math.sqrt(1 + leverage) + .5 * acceleration * dt * dt
    return dict(value=float(value), rate_per_s=fit['rate_per_s'], heuristic_sigma=float(sigma),
                heuristic_half_width_3sigma=float(3 * sigma), leverage=leverage)


def propagate(model, sample_rate_hz, start_counter, stop_counter, reference_counter=None):
    if reference_counter is None:
        reference_counter = (start_counter + stop_counter) / 2
    dt = (reference_counter - model['reference_counter']) / sample_rate_hz
    if dt < 0:
        raise ValueError('prediction reference precedes latest donor')
    cfo = scalar_prediction(model['CFO_fit'], dt, model['one_donor'], 75., 4000., 500.)
    timing_dt = (start_counter - model['timing_reference_counter']) / sample_rate_hz
    timing = scalar_prediction(model['timing_fit'], timing_dt, model['one_donor'], .75, 150., 10.)
    epoch = (model['epoch_reference_base_samples'] - (start_counter - model['epoch_reference_start_counter']) +
             timing['value']) % (sample_rate_hz / 750)
    return dict(start_counter=start_counter, stop_counter=stop_counter, reference_counter=reference_counter,
        elapsed_s=dt, timing_elapsed_s=timing_dt, timing_reference_counter=start_counter,
        epoch_samples=float(epoch), CFO_hz=cfo['value'],
        CFO_rate_hz_per_s=cfo['rate_per_s'], timing_rate_samples_per_s=timing['rate_per_s'],
        CFO_sigma_hz=cfo['heuristic_sigma'], timing_sigma_samples=timing['heuristic_sigma'],
        CFO_half_width_hz=cfo['heuristic_half_width_3sigma'], timing_half_width_samples=timing['heuristic_half_width_3sigma'],
        uncertainty_calibrated=False)


def predict(header, history):
    rate = header['sample_rate_hz']
    if any(p['valid_start_counter'] + header['window_samples'] > header['start_counter'] or
           p['receiver_id'] != header['receiver_id'] or p['channel'] != header['channel'] or
           p['edge'] != header['edge'] for p in history):
        raise ValueError('earlier donor support/cell ownership violation')
    earlier = sorted([p for p in history if 0 < (header['start_counter'] - p['valid_start_counter']) / rate <= HORIZON_S],
                     key=lambda p: p['valid_start_counter'])[-HISTORY_VISITS:]
    if len({p['valid_start_counter'] for p in earlier}) != len(earlier):
        raise ValueError('duplicate history visit')
    tracks = []
    pruned = 0
    ambiguous_extensions = 0
    visit_counts = []
    for probe in earlier:
        candidates = measured_candidates(probe, header)
        proposed = list(tracks) + [[c] for c in candidates]
        for c in candidates:
            matches = [track for track in tracks if compatible(track, c, rate)]
            ambiguous_extensions += max(0, len(matches) - 1)
            proposed.extend(track + [c] for track in matches)
        tracks, dropped = prune(proposed)
        pruned += dropped
        visit_counts.append(len(candidates))
    modes = []
    for index, track in enumerate(tracks):
        model = fit_track(track, rate)
        last_position = next(i for i, p in enumerate(earlier) if p['valid_start_counter'] == track[-1]['start_counter'])
        first_position = next(i for i, p in enumerate(earlier) if p['valid_start_counter'] == track[0]['start_counter'])
        start = header['start_counter']
        size = header['window_samples']
        modes.append(dict(hypothesis_id=f"{header['prediction_id']}/m{index}",
            status='one_donor_fallback' if len(track) == 1 else 'multi_donor', donors=track, model=model,
            donor_count=len(track), missed_visits_after_latest=len(earlier) - last_position - 1,
            missed_visits_between_donors=(last_position - first_position + 1) - len(track),
            full=propagate(model, rate, start, start + size),
            halves=[propagate(model, rate, start + offset, start + offset + size // 2) for offset in [0, size // 2]]))
    return dict(schema=VERSION, prediction_id=header['prediction_id'], status='available' if modes else 'no_donor',
        primary_mode=0 if modes else None, modes=modes, history_visits=len(earlier),
        visits_with_gatepassing_candidates=sum(n > 0 for n in visit_counts),
        latest_visit_gatepassing=bool(visit_counts and visit_counts[-1]), history_candidate_counts=visit_counts,
        ambiguous_extensions=ambiguous_extensions, modes_pruned=pruned,
        no_target_response_inputs=True, uncertainty_calibrated=False,
        alternatives_share_target_support=True, new_independent_observations=0)
