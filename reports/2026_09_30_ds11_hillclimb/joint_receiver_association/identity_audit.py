"""Recover physical identity marginals from the exact evaluated factor trace."""
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
import joint_position
from matching import evidence
from position_run import load
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent


def identities(model, x):
    trace = []
    original = joint_position.mixture
    def capture(values, derivatives, size):
        out = original(values, derivatives, size)
        trace.append((values.copy(), out[0]))
        return out
    joint_position.mixture = capture
    try:
        evaluated = model.evaluate(x, gradient=False)
    finally:
        joint_position.mixture = original
    stream = iter(trace)
    marginal = {tid: {n: 0. for n in m['candidate_norad']} for tid, m in model.meta.items()}
    for lane in model.lanes:
        ls, rs = lane['left'], lane['right']
        allowed = {(e['left'], e['right']) for e in lane['edges']}
        prior = np.array([[0. if (a, b) in allowed else -np.inf for b in rs] for a in ls]).reshape(len(ls), len(rs))
        branches = []
        for branch in lane['ownership_alternatives']:
            def factor(tids):
                ids = sorted(set.intersection(*(set(model.meta[t]['candidate_norad']) for t in tids)))
                values, score = next(stream)
                assert len(values) == len(ids)
                return ids, np.exp(values - logsumexp(values)), score
            singles = {t: factor((t,)) for t in ls + rs}
            pairs = {}
            scores = np.full((len(ls), len(rs)), -np.inf)
            for i, a in enumerate(ls):
                for j, b in enumerate(rs):
                    if (a, b) in allowed:
                        pairs[i, j] = factor((a, b))
                        scores[i, j] = pairs[i, j][2]
            out = evidence([singles[t][2] for t in ls], [singles[t][2] for t in rs], scores, prior)
            branches.append((branch['log_prior'] + out['log_evidence'], out, singles, pairs))
        normal = logsumexp([b[0] for b in branches])
        for score, out, singles, pairs in branches:
            branch_weight = np.exp(score - normal)
            def add(tid, factor, weight):
                for norad, probability in zip(factor[0], factor[1]):
                    marginal[tid][norad] += float(branch_weight * weight * probability)
            for i, t in enumerate(ls):
                add(t, singles[t], out['left_unmatched'][i])
            for j, t in enumerate(rs):
                add(t, singles[t], out['right_unmatched'][j])
            for (i, j), factor in pairs.items():
                add(ls[i], factor, out['pair_posterior'][i, j])
                add(rs[j], factor, out['pair_posterior'][i, j])
    assert next(stream, None) is None
    summaries = {}
    for tid, probabilities in marginal.items():
        total = sum(probabilities.values())
        assert abs(total - 1.) < 1e-8
        probabilities = {n: p / total for n, p in probabilities.items()}
        best = max(probabilities, key=probabilities.get)
        summaries[tid] = dict(map_norad=best, probability=probabilities[best], entropy=float(-sum(p * np.log(p) for p in probabilities.values() if p > 0)), probabilities=probabilities)
    return evaluated['score'], summaries


def main():
    sources = {str(Path(__file__)): digest(Path(__file__))}
    results = []
    for index in (0, 4, 9, 16, 19, 20):
        arms = {}
        for arm in ('doppler', 'signed'):
            path = HERE / f'position-{index:02d}-{arm}.json'
            fit = read(path)
            assert fit['qualified']
            model, initial, bound_sources = load(index, arm)
            score, posterior = identities(model, fit['x'])
            assert abs(score - fit['score']) < 1e-7
            sources.update(bound_sources)
            sources[str(path)] = digest(path)
            arms[arm] = posterior
        changes = [tid for tid in arms['doppler'] if arms['doppler'][tid]['map_norad'] != arms['signed'][tid]['map_norad']]
        row = dict(index=index, arms=arms, map_identity_changes=changes, uncertain_tracks={a: sum(p['probability'] < .9 for p in v.values()) for a, v in arms.items()})
        results.append(row)
        print(json.dumps(dict(index=index, map_identity_changes=len(changes), uncertain_tracks=row['uncertain_tracks'])), flush=True)
    with (HERE / 'identity-audit.json').open('x') as f:
        json.dump(dict(rows=results, sources=sources, limitation='posterior under retained candidate banks and conditional model; no verified identity truth'), f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
