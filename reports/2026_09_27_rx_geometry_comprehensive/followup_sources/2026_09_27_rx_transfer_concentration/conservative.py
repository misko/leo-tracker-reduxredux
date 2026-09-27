"""Fixed posterior blending development replay; does not fit a reliability weight."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / '2026_09_27_roof_balanced_confirmation/association-transfer-summary.json'
LAMBDAS = (0., .25, .5, .75, 1.)  # .5 primary; endpoints and fixed sensitivities.


def lse(values):
    high = max(values)
    return high + math.log(math.fsum(math.exp(v-high) for v in values))


def blend(log_p, log_q, fraction):
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError('invalid fraction')
    if not log_p or len(log_p) != len(log_q):
        raise ValueError('unaligned probabilities')
    if not all(math.isfinite(x) for x in list(log_p)+list(log_q)):
        raise ValueError('nonfinite probability')
    if abs(lse(log_p)) > 1e-9 or abs(lse(log_q)) > 1e-9:
        raise ValueError('unnormalized probability')
    if fraction == 0: return list(log_p)
    if fraction == 1: return list(log_q)
    return [lse([math.log1p(-fraction)+p, math.log(fraction)+q]) for p,q in zip(log_p,log_q)]


def score(log_p, log_q, held, count, fraction):
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError('invalid count')
    if len(held) != len(log_p) or not all(math.isfinite(x) for x in held):
        raise ValueError('invalid held vector')
    mixed = blend(log_p, log_q, fraction)
    baseline = -lse([p+f for p,f in zip(log_p, held)])/count
    nll = -lse([p+f for p,f in zip(mixed, held)])/count
    bound = -math.log1p(-fraction)/count if fraction < 1 else None
    if bound is not None and nll-baseline > bound+1e-10:
        raise ValueError('safety bound violated')
    return {'baseline_nll': baseline, 'nll': nll, 'gain': baseline-nll,
            'maximum_loss_bound': bound}


def main():
    raw = SOURCE.read_bytes(); source = json.loads(raw)
    records = source['records']
    if not source['complete'] or len(records) != 688: raise ValueError('incomplete source')
    output = {'source_sha256': hashlib.sha256(raw).hexdigest(),
              'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Development replay of previously examined temporal outcomes. No fitting; lambda 0.5 primary, 0.25/0.75 sensitivities. Not geographic or independent validation.',
              'results': {}}
    for fraction in LAMBDAS:
        arms = {}
        for direction in ('A_to_B', 'B_to_A'):
            selected = [r for r in records if r['direction'] == direction]
            if len(selected) != 344: raise ValueError('missing tracks')
            modes = {}
            for mode in ('normal','reversed','null'):
                scored = []
                for r in selected:
                    v = r[mode]
                    p = v['baseline_conditioning_posterior']; q = v['reception_conditioning_posterior']
                    if p['candidate_ids'] != r['candidate_ids'] or q['candidate_ids'] != r['candidate_ids']:
                        raise ValueError('candidate alignment')
                    s = score(p['log_weights'], q['log_weights'], r['held_frequency_log_likelihood'], r['held_count'], fraction)
                    if abs(s['baseline_nll']-v['baseline_mean_nll']) > 1e-10: raise ValueError('baseline parity')
                    if fraction == 1 and abs(s['nll']-v['reception_mean_nll']) > 1e-10: raise ValueError('RX parity')
                    if mode == 'null' and abs(s['gain']) > 1e-10: raise ValueError('null failed')
                    scored.append({**s, 'session_id': r['session_id'], 'track_id': r['track_id'], 'weight': r['weight_seconds']})
                def mean(rows):
                    return math.fsum(r['weight']*r['gain'] for r in rows)/sum(r['weight'] for r in rows)
                by_session = {sid: mean([r for r in scored if r['session_id']==sid]) for sid in source['sessions']}
                modes[mode] = {'weighted_gain': mean(scored), 'per_recording': by_session,
                    'recordings_improving': sum(v > 1e-10 for v in by_session.values()),
                    'equal_track_gain': math.fsum(r['gain'] for r in scored)/len(scored),
                    'worst_track_gain': min(r['gain'] for r in scored), 'records': scored}
            arms[direction] = modes
        output['results'][str(fraction)] = arms
    with (HERE/'conservative-results.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False); stream.write('\n')
    for fraction, arms in output['results'].items():
        print(fraction, {d: {m: (v['weighted_gain'], v['recordings_improving']) for m,v in a.items()} for d,a in arms.items()})


if __name__ == '__main__': main()
