"""Pure RF-only inventory helpers. Candidate hypotheses are not observations."""
import hashlib
import json
import numpy as np

CFO_PERIOD = 1 / 4.4e-6


def wrap(x, period):
    return (np.asarray(x) + period / 2) % period - period / 2


def global_phase(start, origin, local_epoch, fs):
    if int(fs) != fs or fs <= 0 or start < origin:
        raise ValueError('integer sample rate and authoritative counter origin required')
    # Reduce the integer device counter BEFORE adding the fractional epoch.
    counter_phase = ((int(start) - int(origin)) * 750 % int(fs)) / 750
    return float((counter_phase + local_epoch) % (fs / 750))


def identity(parts):
    return 'sha256:' + hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def linear_path(rows, fs):
    """Deterministic paired linear consensus, preserving all input rows separately.

    Inputs are the prior pointwise nearby ALTERNATIVES, within one original
    graph owner. One candidate per receiver-window can contribute to a path.
    """
    if len(rows) < 5:
        return None
    rows = sorted(rows, key=lambda r: (r['time_s'], r['candidate_id']))
    t = np.asarray([r['time_s'] for r in rows]); t = t - t.min()
    f = np.asarray([r['cfo_hz'] for r in rows])
    e = np.asarray([r['global_epoch_samples'] for r in rows])
    margin = np.asarray([r['margin'] for r in rows])
    period = fs / 750
    best = None
    passing_sets = set()
    passing_runs = 0

    def choose(model):
        fc, fr, ec, er = model
        rf = wrap(f - fc - fr*t, CFO_PERIOD)
        re = wrap(e - ec - er*t, period)
        use = (abs(rf) <= 250) & (abs(re) <= 3)
        windows = {}
        for k in np.flatnonzero(use):
            score = ((rf[k]/250)**2 + (re[k]/3)**2, -margin[k], rows[k]['candidate_rank'], rows[k]['candidate_id'])
            key = rows[k]['window_id']
            if key not in windows or score < windows[key][0]:
                windows[key] = (score, int(k))
        return sorted((v[1] for v in windows.values()), key=lambda k: (t[k], rows[k]['candidate_id']))

    def refit(indices, model):
        q = np.asarray(indices, dtype=int)
        design = np.column_stack((np.ones(len(q)), t[q]))
        fp = model[0] + model[1]*t[q]
        ep = model[2] + model[3]*t[q]
        fm = np.linalg.lstsq(design, fp + wrap(f[q]-fp, CFO_PERIOD), rcond=None)[0]
        em = np.linalg.lstsq(design, ep + wrap(e[q]-ep, period), rcond=None)[0]
        return np.r_[fm, em]

    for a in range(len(rows)):
        for b in range(a+1, len(rows)):
            dt = t[b]-t[a]
            if not .25 <= dt <= 5:
                continue
            fr = float(wrap(f[b]-f[a], CFO_PERIOD)/dt)
            er = float(wrap(e[b]-e[a], period)/dt)
            if abs(fr) > 5000 or abs(er) > 300:
                continue
            model = np.array([f[a]-fr*t[a], fr, e[a]-er*t[a], er])
            for _ in range(2):
                indices = choose(model)
                if len(indices) < 5:
                    break
                model = refit(indices, model)
            indices = choose(model)
            if len(indices) < 5:
                continue
            # Gaps are measured between contributing original receiver windows.
            cuts = [0] + [i for i in range(1,len(indices)) if t[indices[i]]-t[indices[i-1]] > 2] + [len(indices)]
            for left, right in zip(cuts[:-1], cuts[1:]):
                q = np.asarray(indices[left:right], dtype=int)
                if len(q) < 5 or t[q[-1]]-t[q[0]] < 3:
                    continue
                m = refit(q, model)
                rf = wrap(f[q]-m[0]-m[1]*t[q], CFO_PERIOD)
                re = wrap(e[q]-m[2]-m[3]*t[q], period)
                if abs(m[1]) > 5000 or abs(m[3]) > 300 or np.max(abs(rf)) > 250 or np.max(abs(re)) > 3:
                    continue
                passing_runs += 1
                passing_sets.add(tuple(rows[k]['candidate_id'] for k in q))
                score = (-len(q), -float(t[q[-1]]-t[q[0]]), float(np.mean(rf**2)), float(np.mean(re**2)), tuple(rows[k]['candidate_id'] for k in q))
                result = dict(candidate_ids=[rows[k]['candidate_id'] for k in q], window_ids=[rows[k]['window_id'] for k in q],
                    points=len(q), span_s=float(t[q[-1]]-t[q[0]]), start_s=float(rows[q[0]]['time_s']),
                    end_s=float(rows[q[-1]]['time_s']), max_gap_s=float(np.max(np.diff(t[q]))),
                    CFO_rate_Hz_s=float(m[1]), epoch_rate_samples_s=float(m[3]),
                    CFO_RMS_Hz=float(np.sqrt(np.mean(rf**2))), epoch_RMS_samples=float(np.sqrt(np.mean(re**2))),
                    maximum_CFO_residual_Hz=float(np.max(abs(rf))), maximum_epoch_residual_samples=float(np.max(abs(re))),
                    reference_time_s=float(rows[0]['time_s']), CFO_intercept_Hz=float(m[0]), epoch_intercept_samples=float(m[2]))
                if best is None or score < best[0]:
                    best = (score, result)
    if best is None:
        return None
    return dict(best[1], distinct_passing_paths=len(passing_sets), passing_seed_runs=passing_runs)
