"""Measure exact whole-source assignment support with a conservative tail bound."""
import json
import math
from pathlib import Path
import time
import numpy as np
from scipy.special import logsumexp
from position_run import load
from doppler_pilot import fast, read, digest

HERE = Path(__file__).resolve().parent


def components(support):
    pending = set(support)
    result = []
    while pending:
        first = min(pending)
        group = {first}
        pending.remove(first)
        candidates = set(support[first])
        while True:
            more = {t for t in pending if candidates.intersection(support[t])}
            if not more:
                break
            pending -= more
            group |= more
            for tid in more:
                candidates.update(support[tid])
        result.append(dict(tracks=sorted(group), candidates=len(candidates), assignments=math.prod(len(support[t]) for t in group)))
    return result


def audit(model, x):
    base = {}
    for tid, track in model.tracks.items():
        pred, visible = model.geometry.prediction(track, x)
        base[tid] = (track['y'][None, :] - pred, visible, model.receiver_probabilities(track, tid, x))
    results = []
    for lane in model.lanes:
        tids = lane['left'] + lane['right']
        for branch_index, branch in enumerate(lane['ownership_alternatives']):
            scores, keeps, best = {}, {}, {}
            groups = {}
            for tid in tids:
                track, meta = model.tracks[tid], model.meta[tid]
                keep = np.array([branch['assignment'].get(c, tid) == tid for c in meta['candidate_ids']])
                keeps[tid] = keep
                mask = track['mask'][keep]
                assert mask.sum() >= 2
                s, _, audits, _ = fast.profile(base[tid][0][:, keep], mask)
                assert all(a['converged'] for a in audits)
                scores[tid] = np.where(base[tid][1], s, -np.inf)
                best[tid] = int(np.argmax(scores[tid]))
                groups.setdefault(meta['candidate_norad'][best[tid]], []).append(tid)
            prior = sum(np.log(model.tracks[t]['catalogue_size']) for t in tids)
            upper = sum(logsumexp(scores[t]) for t in tids) - prior
            lower = sum(scores[t][best[t]] for t in tids) - prior
            receiver = 0.
            for group in groups.values():
                windows = {}
                for tid in sorted(group):
                    for i in np.flatnonzero(keeps[tid] & model.tracks[tid]['mask']):
                        windows.setdefault(model.meta[tid]['window_ids'][i], []).append((tid, i))
                for entries in windows.values():
                    state = sum(1 << r for r in {model.meta[t]['receiver'] for t, i in entries})
                    tid, i = entries[0]
                    receiver += base[tid][2][best[tid], i, state - 1]
            lower += receiver
            assert lower <= upper + 1e-8
            slots = sum(len(s) for s in scores.values())
            threshold = lower - upper + np.log(1e-10) - np.log(slots)
            support, removed = {}, []
            for tid in tids:
                logp = scores[tid] - logsumexp(scores[tid])
                keep = logp >= threshold
                assert keep.any()
                support[tid] = [n for n, yes in zip(model.meta[tid]['candidate_norad'], keep) if yes]
                removed.extend(logp[~keep].tolist())
            bound = float(upper + logsumexp(removed) - lower) if removed else -np.inf
            assert bound <= np.log(1e-10) + 1e-8
            parts = components(support)
            results.append(dict(rf_hz=lane['rf_hz'], ownership_branch=branch_index, doppler_log_upper=float(upper), assignment_log_lower=float(lower), receiver_score_at_map=float(receiver), threshold=float(threshold), original_slots=slots, retained_slots=sum(map(len, support.values())), log_relative_omitted_bound=bound if np.isfinite(bound) else None, zero_omitted_mass=not np.isfinite(bound), components=parts, total_component_assignments=sum(c['assignments'] for c in parts), maximum_component_assignments=max(c['assignments'] for c in parts)))
    return results


def main():
    start = time.monotonic()
    rows, sources = [], {}
    for index in (0, 4, 9, 16, 19, 20):
        model, x, bindings = load(index, 'signed')
        sources.update(bindings)
        result = audit(model, x)
        rows.append(dict(index=index, branches=result))
        print(json.dumps(dict(index=index, maximum_component_assignments=max(r['maximum_component_assignments'] for r in result), total_component_assignments=sum(r['total_component_assignments'] for r in result), branches=len(result))), flush=True)
    for p in (Path(__file__), HERE / 'SOURCE_SUPPORT_PROTOCOL.md'):
        sources[str(p)] = digest(p)
    with (HERE / 'source-support-audit.json').open('x') as f:
        json.dump(dict(rows=rows, sources=sources, elapsed_s=time.monotonic() - start, position_fits=0, bound_scope='within original candidate banks; conditional receiver factors <=1'), f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
