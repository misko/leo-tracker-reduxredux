"""RF candidate paths on a narrow numerical row port; no satellite or truth input."""
from fractions import Fraction
import numpy as np

SETTINGS = dict(cfo_period_hz=1/4.4e-6, margin_gate=.025, minimum_dt_s=.15,
    maximum_gap_s=10., maximum_slope_hz_s=8000., frequency_sigma_hz=150.,
    frequency_acceleration_hz_s2=20., epoch_sigma_samples=3.,
    epoch_acceleration_samples_s2=20., node_reward=9., start_penalty=18.,
    gap_cost_per_s=.05, minimum_points=8, minimum_span_s=6., maximum_paths=2)


def circular(x, period):
    return (np.asarray(x)+period/2) % period-period/2


def global_epoch(start, origin, local, sample_rate_hz):
    if not isinstance(start, int) or not isinstance(origin, int):
        raise ValueError('native integer counters required')
    if int(sample_rate_hz) != sample_rate_hz or sample_rate_hz <= 0:
        raise ValueError('positive integral sample rate required')
    p = Fraction(int(sample_rate_hz), 750)
    remainder = ((start-origin)*p.denominator) % p.numerator
    return float((remainder/p.denominator+local) % float(p))


def validate(windows, sample_rate_hz):
    ids = set(); windows_seen = set()
    lane = {(w['receiver_id'], w['channel'], w['actual_rf_hz']) for w in windows}
    if len(lane) > 1:
        raise ValueError('one receiver/channel/RF lane per call')
    previous = -np.inf
    for w in windows:
        if w['window_id'] in windows_seen or w['time_s'] <= previous:
            raise ValueError('unique strictly time-ordered receiver windows required')
        windows_seen.add(w['window_id']); previous = w['time_s']
        for c in w['candidates']:
            if c['candidate_id'] in ids:
                raise ValueError('candidate identity duplicated')
            ids.add(c['candidate_id'])
            if c['margin'] < SETTINGS['margin_gate'] or not np.isfinite(
                [c['cfo_hz'], c['global_epoch_samples'], c['local_epoch_samples'], c['margin']]).all():
                raise ValueError('only finite gate-passing candidate rows')
            expected = global_epoch(w['window_start_counter'], w['origin_counter'],
                                    c['local_epoch_samples'], sample_rate_hz)
            if abs(float(circular(expected-c['global_epoch_samples'], sample_rate_hz/750))) > 1e-8:
                raise ValueError('global frame phase does not match native counter')


def winner_rows(windows):
    return [max(w['candidates'], key=lambda c: (c['margin'], -c['candidate_rank']))
            for w in windows if w['candidates']]


def best_path(windows, sample_rate_hz, include_epoch, excluded):
    cfg = SETTINGS; period = cfg['cfo_period_hz']; epoch_period = sample_rate_hz/750
    nodes = []
    for wi, w in enumerate(windows):
        maximum = max((c['margin'] for c in w['candidates']), default=cfg['margin_gate'])
        for c in sorted(w['candidates'], key=lambda c: (-c['margin'], c['candidate_rank'])):
            if c['candidate_id'] not in excluded:
                nodes.append(dict(c, window_index=wi, window_id=w['window_id'], time_s=w['time_s'],
                    reward=cfg['node_reward']+float(np.log(c['margin']/maximum))))
    if not nodes:
        return None
    t = np.array([n['time_s'] for n in nodes]); f = np.array([n['cfo_hz'] for n in nodes])
    e = np.array([n['global_epoch_samples'] for n in nodes]); reward = np.array([n['reward'] for n in nodes])
    sources = []; targets = []; durations = []; vf = []; ve = []
    for j in range(len(nodes)):
        previous = np.flatnonzero((t[j]-t >= cfg['minimum_dt_s']) & (t[j]-t <= cfg['maximum_gap_s']))
        for i in previous:
            dt = t[j]-t[i]; velocity = float(circular(f[j]-f[i], period))/dt
            if abs(velocity) <= cfg['maximum_slope_hz_s']:
                sources.append(i); targets.append(j); durations.append(dt); vf.append(velocity)
                ve.append(float(circular(e[j]-e[i], epoch_period))/dt)
    source = np.asarray(sources, int); target = np.asarray(targets, int)
    dt = np.asarray(durations); vf = np.asarray(vf); ve = np.asarray(ve)
    incoming = [np.flatnonzero(target == j) for j in range(len(nodes))]
    outgoing = [np.flatnonzero(source == j) for j in range(len(nodes))]
    score = np.full(len(source), -np.inf); parent = np.full(len(source), -1, int)
    count = np.zeros(len(source), int); start = np.zeros(len(source), int)
    for j in range(len(nodes)):
        after = outgoing[j]
        if not len(after):
            continue
        gap = cfg['gap_cost_per_s']*dt[after]
        score[after] = reward[j]+reward[target[after]]-cfg['start_penalty']-gap
        count[after] = 2; start[after] = j
        before = incoming[j]
        if not len(before):
            continue
        a, b = dt[before, None], dt[None, after]
        variance = 2*cfg['frequency_sigma_hz']**2*(1/a**2+1/b**2+1/(a*b))
        variance += (cfg['frequency_acceleration_hz_s2']*(a+b)/2)**2
        cost = 2*(vf[before, None]-vf[None, after])**2/variance
        if include_epoch:
            variance_e = 2*cfg['epoch_sigma_samples']**2*(1/a**2+1/b**2+1/(a*b))
            variance_e += (cfg['epoch_acceleration_samples_s2']*(a+b)/2)**2
            cost += 2*(ve[before, None]-ve[None, after])**2/variance_e
        candidates = score[before, None]+reward[target[after]][None, :]-gap[None, :]-cost
        winner = np.argmax(candidates, axis=0); values = candidates[winner, np.arange(len(after))]
        changed = values > score[after]
        selected = after[changed]; prior = before[winner[changed]]
        score[selected] = values[changed]; parent[selected] = prior
        count[selected] = count[prior]+1; start[selected] = start[prior]
    usable = np.flatnonzero((count >= cfg['minimum_points']) & (score > 0) &
                           (t[target]-t[start] >= cfg['minimum_span_s']))
    if not len(usable):
        return None
    last = int(usable[np.argmax(score[usable])]); final_score = float(score[last])
    edges = []; indexes = [int(target[last])]
    while last >= 0:
        edges.append(last); indexes.append(int(source[last])); last = int(parent[last])
    indexes = indexes[::-1]; edges = edges[::-1]
    path = [nodes[i] for i in indexes]
    if len({n['window_id'] for n in path}) != len(path):
        raise ValueError('path uses two alternatives from one receiver-window')
    lifted_f = [path[0]['cfo_hz']]; lifted_e = [path[0]['global_epoch_samples']]
    intervals = []
    for k, edge in enumerate(edges):
        lifted_f.append(lifted_f[-1]+vf[edge]*dt[edge])
        lifted_e.append(lifted_e[-1]+ve[edge]*dt[edge])
        intervals.append(dict(from_candidate_id=path[k]['candidate_id'], to_candidate_id=path[k+1]['candidate_id'],
            elapsed_s=float(dt[edge]), cfo_slope_hz_s=float(vf[edge]), epoch_slope_samples_s=float(ve[edge]),
            epoch_additional_windings_excluded_by_model=True,
            epoch_winding_not_physically_identified=True,
            near_circular_epoch_boundary=abs(ve[edge]*dt[edge]) >= .45*epoch_period))
    for n, lf, le in zip(path, lifted_f, lifted_e):
        n['cfo_alias_lift'] = int(np.rint((lf-n['cfo_hz'])/period))
        n['epoch_winding_lift'] = int(np.rint((le-n['global_epoch_samples'])/epoch_period))
    top = usable[np.argsort(-score[usable], kind='stable')[:8]]
    return dict(nodes=path, score=final_score, intervals=intervals,
        skipped_window_ids=[w['window_id'] for w in windows[path[0]['window_index']:path[-1]['window_index']+1]
                            if w['window_id'] not in {n['window_id'] for n in path}],
        terminal_state_alternatives=[dict(score=float(score[k]), candidate_id=nodes[target[k]]['candidate_id'],
            points=int(count[k]), span_s=float(t[target[k]]-t[start[k]])) for k in top])


def select_paths(windows, sample_rate_hz, include_epoch):
    validate(windows, sample_rate_hz)
    paths = []; excluded = set()
    for _ in range(SETTINGS['maximum_paths']):
        p = best_path(windows, sample_rate_hz, include_epoch, excluded)
        if p is None:
            break
        paths.append(p); excluded.update(n['candidate_id'] for n in p['nodes'])
    used_windows = {n['window_id'] for p in paths for n in p['nodes']}
    all_candidates = {c['candidate_id'] for w in windows for c in w['candidates']}
    return dict(paths=paths, candidate_hypotheses_selected=len(excluded),
        unique_receiver_windows=len(used_windows), total_receiver_windows=len(windows),
        windows_without_selected_path=[w['window_id'] for w in windows if w['window_id'] not in used_windows],
        unselected_candidate_ids=sorted(all_candidates-excluded),
        shared_window_counts={w['window_id']:sum(w['window_id'] in {n['window_id'] for n in p['nodes']} for p in paths)
                             for w in windows},
        limitations=['max2 alternative path capacity is not a physical source count',
            'shared-window candidate hypotheses are correlated, not new measurements',
            'greedy candidate-exclusive path packing, not globally optimal flow',
            'nearest circular winding is a model restriction, not clock/source identification',
            'costs and terminal-state alternatives are not calibrated probabilities'])
